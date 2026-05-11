"""
update_order.py  —  BSU 定软电订单更新工具

用法：
  python update_order.py --order_no 6585951162319339521 --scene sign --amount 100
  python update_order.py --order_no 6585951162319339521 --scene place --amount 200
  python update_order.py --order_no 6585951162319339521 --scene finish --amount 300
  python update_order.py --order_no 6585951162319339521 --scene cancel --amount -50

场景对应 outOrderStatus：
  sign   → 1200（正签）
  place  → 3100（确品下单）
  finish → 3250（履约完成）
  cancel → 3300（定软电退单）

金额计算对照 BsuSoftDecorateOrderAdapterProcess.updateOrderAmountExtList：
  正签:   1061=amount, 1066=amount
  下单:   1062=amount-1061, 1067=amount, 1066=amount  (冲销: 1062=amount, 1067=1061+amount)
  履约完成: 1063/1064/1065/1068 按差值逻辑
  退单:   仅更新 1066=amount

强制覆盖字段（无论 DB 里是什么值，都强制写为以下值）：
  decorationPerfFlag=true
  firstPerformanceCategoryId=035002
  firstPerformanceCategoryName=软装
  secondPerformanceCategoryId=035002001
  secondPerformanceCategoryName=灯具
  softBsuFlag=true
  compositeOrderSplitRule=performance_first_category_id
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
import pymysql.cursors

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_CONFIG_CANDIDATES = [
    _SCRIPT_DIR / "bsu_order.local.toml",
    Path.home() / ".zsy_tools" / "bsu_order.toml",
]

_UPDATE_ORDER_API = "http://test-pinus.ke.com/api/write/updateOrder"

_DEFAULT_COOKIE = (
    "lianjia_uuid=1b1d96b4-9a47-4beb-9546-5fb753bd68d0; "
    "lianjia_ssid=35c8fc75-f0d1-43b8-b253-191ab5092c42"
)

_TABLE_NAME_API = "http://ke-pinus.test-sign.ttb.test.ke.com/inner/admin/tableNameByOrderNo"
_TABLE_NAME_API_HEADERS = {"appId": "test", "ucId": "1000000031012030"}
_table_cache: dict = {}

# ---------------------------------------------------------------------------
# 场景映射
# ---------------------------------------------------------------------------
SCENE_STATUS = {
    "sign":   "1200",
    "place":  "3100",
    "finish": "3250",
    "cancel": "3300",
}

SCENE_TIME_KEY = {
    "sign":   "signTime",
    "place":  "confirmPlaceOrderTime",
    "finish": "agreementFinishTime",
    "cancel": "subOrderCancelTime",
}

# amount type 常量
C_SIGN               = "1061"
C_PLACE              = "1062"
C_FINISH             = "1063"
C_FINISH_DEDUCT_SIGN = "1064"
C_FINISH_DEDUCT_PLACE= "1065"
C_CONTRACT           = "1066"
C_PLACE_ROLE         = "1067"
C_FINISH_ROLE        = "1068"

# ---------------------------------------------------------------------------
# 强制覆盖的 remark 字段（无论 DB 里已有什么值，都用这些值）
# ---------------------------------------------------------------------------
FORCE_OVERRIDE_REMARKS = {
    "decorationPerfFlag":           "true",
    "firstPerformanceCategoryId":   "035002",
    "firstPerformanceCategoryName": "软装",
    "secondPerformanceCategoryId":  "035002001",
    "secondPerformanceCategoryName":"灯具",
    "softBsuFlag":                  "true",
    "compositeOrderSplitRule":      "performance_first_category_id",
}

# 兜底值：DB 查不到时补充的默认值（仅非业务数据的通用配置字段）
FALLBACK_REMARKS = {
    "bizTag":                       "30",
    "geoCity":                      "310000",
    "hardCompanyName":              "北京贝壳家居科技有限公司",
    "homeObjectVersion":            "2.5",
    "houseArea":                    "100.0",
    "isGuoBuType":                  "0",
    "isManualProcess":              "false",
    "isMutualReferral":             "0",
    "maintainModel":                "1",
    "oneLevelChannelType":          "1001",
    "oneLevelChannelTypeName":      "自拓渠道",
    "retailOrderDimension":         "2",
    "retailOrderType":              "18",
    "threeLevelChannelType":        "915",
    "threeLevelChannelTypeName":    "设计端口碑回单",
    "twoLevelChannelType":          "1008",
    "twoLevelChannelTypeName":      "口碑回单",
}

# 业务系统写入的字段（check-remarks 时展示，脚本不补写）
SYSTEM_REMARK_KEYS = {
    "commissionCode", "subOrderNo", "homeOrderNo",
    "brandId", "brandName", "skuName",
    "relatedDeProjectId",
    "firstIncludeProjectProgress", "newPerfTagCategory",
    "mutualReferralCommissionId", "guoBuStatus", "nonNewPerfReason",
    # 订单真实业务数据，由业务系统写入
    "consumption", "quantity", "itemType",
    "firstInternalCategoryId", "firstInternalCategoryName",
    "secondInternalCategoryId", "secondInternalCategoryName",
    "thirdInternalCategoryId", "thirdInternalCategoryName",
}

# 缺失时提示用户是否补写的字段，key -> 默认值生成函数
def _gen_related_de_commission_code() -> str:
    import random
    return f"DE{datetime.now().strftime('%y%m%d')}{random.randint(10000, 99999)}test"

PROMPTED_REMARKS = {
    "relatedDeCommissionCode": _gen_related_de_commission_code,
}

# ---------------------------------------------------------------------------
# DB / HTTP 工具
# ---------------------------------------------------------------------------

def load_config() -> dict:
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    raise FileNotFoundError(
        f"未找到配置文件，请复制 config.example.toml\n"
        f"搜索路径：{[str(p) for p in _CONFIG_CANDIDATES]}"
    )


def get_conn(cfg: dict):
    db = cfg["db_pinus"]
    return pymysql.connect(
        host=db["host"],
        port=int(db.get("port", 3306)),
        user=db["user"],
        password=db["password"],
        database=db["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_shard_table(order_no: int, table_base: str) -> str:
    if order_no not in _table_cache:
        url = f"{_TABLE_NAME_API}?orderNo={order_no}"
        req = urllib.request.Request(url, headers=_TABLE_NAME_API_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("errorcode") != 0:
            raise RuntimeError(f"tableNameByOrderNo 接口异常: {data}")
        _table_cache[order_no] = {
            item["tableName"].rsplit("_", 1)[0]: item["tableName"]
            for item in data["data"]["tableNameList"]
        }
    return _table_cache[order_no][table_base]


def fetch_existing_base(conn, order_no: int) -> dict:
    table = get_shard_table(order_no, "order_base")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT out_order_status, address FROM ke_pinus.{table} WHERE order_no = %s",
            (order_no,),
        )
        row = cur.fetchone()
        return {
            "out_order_status": str(row["out_order_status"]) if row else None,
            "address": row["address"] if row else None,
        }


def fetch_existing_remarks(conn, order_no: int) -> dict:
    # 通过 order_time_ext 获取分片后缀
    time_table = get_shard_table(order_no, "order_time_ext")
    suffix = time_table.rsplit("_", 1)[1]
    table = f"order_remark_ext_{suffix}"
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT remark_key, remark_value FROM ke_pinus.{table} WHERE order_no = %s",
            (order_no,),
        )
        return {row["remark_key"]: row["remark_value"] for row in cur.fetchall()}


def fetch_existing_times(conn, order_no: int) -> dict:
    table = get_shard_table(order_no, "order_time_ext")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT time_type, time_value FROM ke_pinus.{table} WHERE order_no = %s",
            (order_no,),
        )
        return {row["time_type"]: str(row["time_value"]) for row in cur.fetchall()}


def fetch_existing_amounts(conn, order_no: int) -> dict:
    table = get_shard_table(order_no, "order_amount")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT amount_type, amount FROM ke_pinus.{table} WHERE order_no = %s",
            (order_no,),
        )
        return {row["amount_type"]: Decimal(str(row["amount"])) for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# 金额计算（对照 updateOrderAmountExtList，更新场景）
# ---------------------------------------------------------------------------

def calc_amounts_for_update(scene: str, amount: float, existing: dict) -> dict:
    """
    existing: DB 中已有的 amount_type -> Decimal
    返回: 完整的 amount_type -> float 字典（含原有字段 + 新增/更新字段）
    """
    cur = Decimal(str(amount))
    result = dict(existing)  # 先复制所有已有字段

    if scene == "sign":
        result[C_SIGN]     = cur
        result[C_CONTRACT] = cur

    elif scene == "place":
        sign_amt = result.get(C_SIGN, Decimal("0"))
        place_amt = cur - sign_amt
        result[C_PLACE]      = place_amt
        result[C_PLACE_ROLE] = cur
        result[C_CONTRACT]   = cur

    elif scene == "finish":
        sign_amt  = result.get(C_SIGN, Decimal("0"))
        place_amt = result.get(C_PLACE, Decimal("0"))
        finish_amt = cur - place_amt - sign_amt
        contract_amt = cur

        result[C_FINISH]   = finish_amt
        result[C_CONTRACT] = contract_amt
        # 履约完成扣减逻辑
        if finish_amt >= 0:
            result[C_FINISH_DEDUCT_SIGN]  = Decimal("0")
            result[C_FINISH_DEDUCT_PLACE] = Decimal("0")
        else:
            sum_finish_place = place_amt + finish_amt
            if sum_finish_place >= 0:
                result[C_FINISH_DEDUCT_SIGN]  = Decimal("0")
                result[C_FINISH_DEDUCT_PLACE] = finish_amt
            elif place_amt < 0:
                result[C_FINISH_DEDUCT_SIGN]  = finish_amt
                result[C_FINISH_DEDUCT_PLACE] = Decimal("0")
            else:
                result[C_FINISH_DEDUCT_SIGN]  = sum_finish_place
                result[C_FINISH_DEDUCT_PLACE] = -place_amt
        # 1068 = 1066 - 1067
        place_role = result.get(C_PLACE_ROLE, sign_amt)
        result[C_FINISH_ROLE] = contract_amt - place_role

    elif scene == "cancel":
        result[C_CONTRACT] = Decimal("0")

    return result


# ---------------------------------------------------------------------------
# 构建请求字段
# ---------------------------------------------------------------------------

def build_remarks(existing_db: dict, scene: str) -> tuple:
    """
    合并三层：DB已有 → 强制覆盖 → 兜底
    返回 (最终remarks字典, force覆盖列表, fallback使用列表)
    """
    remarks = dict(existing_db)

    # 强制覆盖
    force_applied = []
    for k, v in FORCE_OVERRIDE_REMARKS.items():
        old = remarks.get(k)
        remarks[k] = v
        if old != v:
            force_applied.append((k, old, v))

    # 兜底补充
    fallback_used = []
    for k, v in FALLBACK_REMARKS.items():
        if k not in remarks:
            remarks[k] = v
            fallback_used.append((k, v))

    return remarks, force_applied, fallback_used


def build_time_exts(scene: str, existing_times: dict) -> list:
    now = datetime.now().replace(microsecond=0)
    result = []
    # 先把 DB 里已有的全部带上
    for tt, tv in existing_times.items():
        result.append({"timeType": tt, "timeValue": str(tv)})

    # 当前场景对应的时间节点
    scene_time_key = SCENE_TIME_KEY[scene]
    existing_keys = {item["timeType"] for item in result}

    if scene_time_key not in existing_keys:
        # 没有则生成当前时间
        result.append({"timeType": scene_time_key, "timeValue": now.strftime("%Y-%m-%d %H:%M:%S")})

    return result


# ---------------------------------------------------------------------------
# HTTP 调用
# ---------------------------------------------------------------------------

def call_update_order(order_no: int, out_order_status: str,
                      amounts: dict, time_exts: list, remarks: dict, cookie: str) -> dict:
    order_amounts = [
        {"amountType": k, "amount": float(v)}
        for k, v in sorted(amounts.items())
    ]
    order_remark_exts = [{"remarkKey": k, "remarkValue": v} for k, v in remarks.items()]

    payload = {
        "orderNo": order_no,
        "outOrderStatus": out_order_status,
        "orderAmounts": order_amounts,
        "orderTimeExts": time_exts,
        "orderRemarkExts": order_remark_exts,
        # 其余字段置 null
        "outOrderGroupNo": None, "orderAmount": None, "address": None,
        "productNo": None, "productType": None, "productName": None,
        "customerNo": None, "customerName": None, "customerPhone": None,
        "subBizType": None, "orderStatus": None, "outOrderStatusName": None,
        "orderRemark": None, "orderPreEffectTime": None, "orderEffectTime": None,
        "orderCancelTime": None, "orderAbortTime": None, "orderCompleteTime": None,
        "cityCode": None, "companyOrgCode": None, "ucid": None,
        "teamCode": None, "allianceCode": None, "areaRegionCode": None,
        "orderContracts": None, "orderFees": None, "orderStatusExts": None,
        "orderUserRoles": None,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _UPDATE_ORDER_API,
        data=body,
        headers={
            "appId": "test",
            "Cookie": cookie,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def check_remarks_mode(order_no: int, conn, cookie: str = _DEFAULT_COOKIE):
    existing = fetch_existing_remarks(conn, order_no)
    all_expected = {**FORCE_OVERRIDE_REMARKS, **FALLBACK_REMARKS}

    consistent = {}
    diff = {}
    missing = {}

    for k, expected_v in all_expected.items():
        if k not in existing:
            missing[k] = expected_v
        elif existing[k] == expected_v:
            consistent[k] = expected_v
        else:
            diff[k] = (existing[k], expected_v)

    # 业务系统字段：DB 里有的展示值，没有的标注"业务系统写入"
    system_present = {k: existing[k] for k in SYSTEM_REMARK_KEYS if k in existing}
    system_absent  = [k for k in SYSTEM_REMARK_KEYS if k not in existing]

    # 可选补写字段：缺失时生成默认值，提示用户确认
    prompted_to_write = {}
    for k, gen_fn in PROMPTED_REMARKS.items():
        if k not in existing:
            prompted_to_write[k] = gen_fn()

    print(f"\norder_no: {order_no}")
    print(f"\n[order_remark_ext] DB共 {len(existing)} 个字段")

    if consistent:
        print(f"\n  ✅ 一致（{len(consistent)} 个）")
        for k, v in sorted(consistent.items()):
            print(f"    {k} = {v}")

    if diff:
        print(f"\n  ⚠️  值不同（{len(diff)} 个）")
        for k, (cur_v, exp_v) in sorted(diff.items()):
            print(f"    {k}: DB='{cur_v}'  期望='{exp_v}'")

    if missing:
        print(f"\n  ❌ 脚本兜底字段缺失（{len(missing)} 个）")
        for k, v in sorted(missing.items()):
            print(f"    {k} = {v}")

    if prompted_to_write:
        print(f"\n  ❓ 可选补写字段缺失（{len(prompted_to_write)} 个）")
        for k, v in sorted(prompted_to_write.items()):
            print(f"    {k} = {v}  （生成值，可修改）")

    if system_present:
        print(f"\n  📋 业务系统字段（{len(system_present)} 个，脚本不补写）")
        for k, v in sorted(system_present.items()):
            print(f"    {k} = {v}")

    if system_absent:
        print(f"\n  ➖ 业务系统字段未写入（{len(system_absent)} 个，正常）")
        for k in sorted(system_absent):
            print(f"    {k}")

    to_write = {**{k: exp_v for k, (_, exp_v) in diff.items()}, **missing}

    # 可选补写字段单独询问
    if prompted_to_write:
        print(f"\n__PROMPTED_REMARKS_JSON__")
        print(json.dumps(prompted_to_write, ensure_ascii=False))
        confirm_prompted = input(f"\n是否将以上可选字段写入？(y/n): ").strip().lower()
        if confirm_prompted == "y":
            to_write.update(prompted_to_write)

    if not to_write:
        print("\n脚本管控字段全部一致，无需写入。")
        return

    print(f"\n__CHECK_REMARKS_RESULT_JSON__")
    print(json.dumps({
        "order_no": order_no,
        "diff": {k: {"db": v[0], "expected": v[1]} for k, v in diff.items()},
        "missing": missing,
    }, ensure_ascii=False))

    confirm = input(f"\n是否通过接口将以上 {len(to_write)} 个字段写入？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消。")
        return

    # 查当前状态、地址、金额、时间，原样带上
    base_info        = fetch_existing_base(conn, order_no)
    existing_amounts = fetch_existing_amounts(conn, order_no)
    existing_times   = fetch_existing_times(conn, order_no)

    all_remarks = {**existing, **to_write}
    order_amounts     = [{"amountType": k, "amount": float(v)} for k, v in sorted(existing_amounts.items())]
    order_time_exts   = [{"timeType": k, "timeValue": str(v)} for k, v in existing_times.items()]
    order_remark_exts = [{"remarkKey": k, "remarkValue": v} for k, v in all_remarks.items()]

    payload = {
        "orderNo": order_no,
        "address": base_info["address"],
        "outOrderStatus": base_info["out_order_status"],
        "orderAmounts": order_amounts,
        "orderTimeExts": order_time_exts,
        "orderRemarkExts": order_remark_exts,
        "outOrderGroupNo": None, "orderAmount": None,
        "productNo": None, "productType": None, "productName": None,
        "customerNo": None, "customerName": None, "customerPhone": None,
        "subBizType": None, "orderStatus": None, "outOrderStatusName": None,
        "orderRemark": None, "orderPreEffectTime": None, "orderEffectTime": None,
        "orderCancelTime": None, "orderAbortTime": None, "orderCompleteTime": None,
        "cityCode": None, "companyOrgCode": None, "ucid": None,
        "teamCode": None, "allianceCode": None, "areaRegionCode": None,
        "orderContracts": None, "orderFees": None, "orderStatusExts": None,
        "orderUserRoles": None,
    }

    print(f"\n发送中（outOrderStatus={base_info['out_order_status']}，amounts={len(order_amounts)}个，remarks={len(all_remarks)}个）...")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _UPDATE_ORDER_API,
        data=body,
        headers={"appId": "test", "Cookie": cookie, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    print(f"\n接口响应：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errorcode") == 0:
        print(f"\n✅ 成功，{len(to_write)} 个字段已写入")
        for k, v in to_write.items():
            print(f"  {k} = {v}")
    else:
        print(f"\n❌ 失败：{result.get('errmsg')}")


def main():
    parser = argparse.ArgumentParser(description="BSU 定软电订单更新")
    parser.add_argument("--order_no", type=int, required=True, help="子单 orderNo（数字）")
    parser.add_argument("--check-remarks", action="store_true", help="核查 order_remark_ext 字段（只读对比，可选写入）")
    parser.add_argument("--scene", choices=["sign", "place", "finish", "cancel"],
                        help="场景: sign正签 / place下单 / finish履约完成 / cancel退单")
    parser.add_argument("--amount", type=float,
                        help="当前节点的合同额（contractAmount），退单传负数或冲销金额")
    parser.add_argument("--cookie", default=_DEFAULT_COOKIE, help="Cookie（可选）")
    args = parser.parse_args()

    if args.check_remarks:
        cfg = load_config()
        conn = get_conn(cfg)
        check_remarks_mode(args.order_no, conn, args.cookie)
        conn.close()
        return

    if not args.scene or args.amount is None:
        parser.error("更新订单模式需要 --scene 和 --amount")

    out_order_status = SCENE_STATUS[args.scene]

    cfg = load_config()
    conn = get_conn(cfg)

    # 1. 从 DB 读已有数据
    print("正在从 DB 读取已有字段...")
    existing_remarks = fetch_existing_remarks(conn, args.order_no)
    existing_times   = fetch_existing_times(conn, args.order_no)
    existing_amounts = fetch_existing_amounts(conn, args.order_no)
    conn.close()
    print(f"  DB remarks: {len(existing_remarks)} 个，times: {len(existing_times)} 个，amounts: {len(existing_amounts)} 个")

    # 2. 计算金额
    amounts = calc_amounts_for_update(args.scene, args.amount, existing_amounts)

    # 3. 构建 remark（DB + 强制覆盖 + 兜底）
    remarks, force_applied, fallback_used = build_remarks(existing_remarks, args.scene)

    # 4. 构建时间
    time_exts = build_time_exts(args.scene, existing_times)

    # 5. 展示摘要
    print(f"\n{'='*60}")
    print(f"即将调用 updateOrder：")
    print(f"  orderNo        : {args.order_no}")
    print(f"  scene          : {args.scene}")
    print(f"  outOrderStatus : {out_order_status}")
    print(f"  contractAmount : {args.amount}")

    print(f"\n  [orderAmounts] 共 {len(amounts)} 个")
    for code, val in sorted(amounts.items()):
        print(f"    {code} = {val}")

    print(f"\n  [orderTimeExts] 共 {len(time_exts)} 个")
    for t in time_exts:
        src = "(DB)" if t["timeType"] in existing_times else "(生成)"
        print(f"    {t['timeType']} = {t['timeValue']}  {src}")

    print(f"\n  [orderRemarkExts] 共 {len(remarks)} 个"
          f"（DB:{len(existing_remarks)} 强制覆盖:{len(force_applied)} 兜底:{len(fallback_used)}）")
    if force_applied:
        print(f"  强制覆盖字段：")
        for k, old, new in force_applied:
            old_str = f"'{old}'" if old is not None else "不存在"
            print(f"    {k}: {old_str} → '{new}'")
    if fallback_used:
        print(f"  兜底字段（DB 无此键）：")
        for k, v in fallback_used:
            print(f"    {k} = {v}")
    print(f"{'='*60}")

    confirm = input("\n确认发送？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消。")
        sys.exit(0)

    # 6. 发送
    print("\n发送中...")
    result = call_update_order(args.order_no, out_order_status, amounts, time_exts, remarks, args.cookie)
    print(f"\n接口响应：")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("errorcode") == 0:
        print(f"\n✅ 成功")
    else:
        print(f"\n❌ 失败：{result.get('errmsg')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
