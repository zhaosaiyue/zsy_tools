"""
bsu_amount.py

用法：
  python bsu_amount.py --order_no 6576945096935940096 --scene place --sign 10 --place 8 --query-only
  python bsu_amount.py --order_no 6576945096935940096 --scene place --sign 10 --place 8 --do-write

--scene 取值：
  sign    正签（status=1200，时间：signTime，金额：1061/1066）
  place   下单（status=3100，时间：+confirmPlaceOrderTime，金额：+1062/1067）
  finish  履约完成（status=3250，时间：+agreementFinishTime，金额：+1063~1068）
  cancel  退单（status=3300，时间：+subOrderCancelTime，金额：1066=0）

--place-type / --finish-type：normal（默认）/ cancel（冲销）
"""

import argparse
import json
import urllib.request
from datetime import datetime, timedelta
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
    _SCRIPT_DIR / "bsu_amount.local.toml",
    Path.home() / ".zsy_tools" / "bsu_amount.toml",
]

# ---------------------------------------------------------------------------
# 费用项常量
# ---------------------------------------------------------------------------
C_SIGN               = 1061
C_PLACE              = 1062
C_FINISH             = 1063
C_FINISH_DEDUCT_SIGN = 1064
C_FINISH_DEDUCT_PLACE= 1065
C_CONTRACT           = 1066
C_PLACE_ROLE         = 1067
C_FINISH_ROLE        = 1068

BSU_CODE_NAMES = {
    1061: "BSU_SOFT_SIGN_AMOUNT",
    1062: "BSU_SOFT_PLACE_ORDER_AMOUNT",
    1063: "BSU_SOFT_AGREEMENT_FINISH_AMOUNT",
    1064: "BSU_SOFT_AGREEMENT_FINISH_DEDUCT_SIGN_AMOUNT",
    1065: "BSU_SOFT_AGREEMENT_FINISH_DEDUCT_PLACE_ORDER_AMOUNT",
    1066: "BSU_SOFT_CONTRACT_AMOUNT",
    1067: "BSU_SOFT_PLACE_ORDER_AMOUNT_FOR_PLACE_ORDER_ROLE",
    1068: "BSU_SOFT_AGREEMENT_FINISH_AMOUNT_FOR_PLACE_ORDER_ROLE",
}

# ---------------------------------------------------------------------------
# 场景常量
# ---------------------------------------------------------------------------
SCENE_STATUS = {
    "sign":   1200,
    "place":  3100,
    "finish": 3250,
    "cancel": 3300,
}

# 各场景需要存在的 time_type（按节点顺序）
SCENE_TIME_TYPES = {
    "sign":   ["signTime"],
    "place":  ["signTime", "confirmPlaceOrderTime"],
    "finish": ["signTime", "confirmPlaceOrderTime", "agreementFinishTime"],
    "cancel": ["signTime", "subOrderCancelTime"],
}

# 各 time_type 相对 signTime 的偏移分钟数（signTime 本身为 0，作为基准）
TIME_OFFSETS = {
    "signTime":               0,
    "confirmPlaceOrderTime":  10,
    "agreementFinishTime":    20,
    "subOrderCancelTime":     30,
}

# ---------------------------------------------------------------------------
# 分表查询
# ---------------------------------------------------------------------------
_TABLE_NAME_API = "http://ke-pinus.test-sign.ttb.test.ke.com/inner/admin/tableNameByOrderNo"
_TABLE_NAME_API_HEADERS = {"appId": "test", "ucId": "1000000031012030"}
_table_cache: dict[int, dict[str, str]] = {}


def get_shard_table(order_no: int, table_name: str) -> str:
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
    return _table_cache[order_no][table_name]


# ---------------------------------------------------------------------------
# 金额计算
# ---------------------------------------------------------------------------

def calc_amounts(
    scene: str,
    sign: float,
    place: float | None = None,
    finish: float | None = None,
    place_type: str = "normal",
    finish_type: str = "normal",
) -> dict[int, float]:
    amounts: dict[int, float] = {}
    amounts[C_SIGN]     = sign
    amounts[C_CONTRACT] = sign

    if scene == "cancel":
        amounts[C_CONTRACT] = 0.0
        # place 传入说明经历过下单，finish 传入说明经历过履约完成
        if finish is not None and place is not None:
            amounts["_keep"] = {C_SIGN, C_PLACE, C_FINISH, C_FINISH_DEDUCT_SIGN, C_FINISH_DEDUCT_PLACE, C_CONTRACT, C_PLACE_ROLE, C_FINISH_ROLE}
        elif place is not None:
            amounts["_keep"] = {C_SIGN, C_PLACE, C_CONTRACT, C_PLACE_ROLE}
        else:
            amounts["_keep"] = {C_SIGN, C_CONTRACT}
        return amounts

    if scene in ("place", "finish") and place is not None:
        if place_type == "cancel":
            amounts[C_PLACE]      = place
            amounts[C_CONTRACT]   = sign + place
            amounts[C_PLACE_ROLE] = sign + place
        else:
            amounts[C_PLACE]      = place - sign
            amounts[C_CONTRACT]   = place
            amounts[C_PLACE_ROLE] = place

    if scene == "finish" and finish is not None:
        c1061 = amounts[C_SIGN]
        c1062 = amounts[C_PLACE]
        c1067 = amounts[C_PLACE_ROLE]

        if finish_type == "cancel":
            c1063 = finish
            c1066 = c1061 + c1062 + finish
        else:
            c1063 = finish - c1062 - c1061
            c1066 = finish

        c1068 = c1066 - c1067

        if c1063 >= 0:
            c1064, c1065 = 0.0, 0.0
        else:
            total = c1062 + c1063
            if total >= 0:
                c1064, c1065 = 0.0, c1063
            elif c1062 < 0:
                c1064, c1065 = c1063, 0.0
            else:
                c1064, c1065 = total, -c1062

        amounts[C_FINISH]              = c1063
        amounts[C_FINISH_DEDUCT_SIGN]  = c1064
        amounts[C_FINISH_DEDUCT_PLACE] = c1065
        amounts[C_CONTRACT]            = c1066
        amounts[C_FINISH_ROLE]         = c1068

    return amounts


# ---------------------------------------------------------------------------
# 时间计算
# ---------------------------------------------------------------------------

def calc_missing_times(scene: str, existing_types: set[str]) -> dict[str, datetime]:
    """返回需要 INSERT 的 {time_type: datetime}，已有的跳过。"""
    now = datetime.now().replace(microsecond=0)
    sign_base = now  # signTime 作为基准
    needed = SCENE_TIME_TYPES[scene]
    result = {}
    for tt in needed:
        if tt not in existing_types:
            offset = TIME_OFFSETS.get(tt, 0)
            result[tt] = sign_base + timedelta(minutes=offset)
    return result


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------

def load_config() -> dict:
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    raise FileNotFoundError(
        f"未找到配置文件，请复制 config.example.toml 为 bsu_amount.local.toml\n"
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


def fetch_existing_status(conn, order_no: int) -> dict | None:
    table = get_shard_table(order_no, "order_base")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT out_order_status FROM ke_pinus.{table} WHERE order_no = %s",
            (order_no,),
        )
        return cur.fetchone()


def fetch_existing_times(conn, order_no: int) -> list[dict]:
    table = get_shard_table(order_no, "order_time_ext")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM ke_pinus.{table} WHERE order_no = %s ORDER BY time_type",
            (order_no,),
        )
        return cur.fetchall()


CATEGORY_ITEMS = [
    ("firstPerformanceCategoryId",   "035002"),
    ("firstPerformanceCategoryName",  "软装"),
    ("secondPerformanceCategoryId",  "035002001"),
    ("secondPerformanceCategoryName", "灯具"),
]


def ensure_category_remarks(conn, order_no: int):
    suffix = get_shard_table(order_no, "order_time_ext").rsplit("_", 1)[1]
    table = f"order_remark_ext_{suffix}"
    keys = [k for k, _ in CATEGORY_ITEMS]
    with conn.cursor() as cur:
        placeholders = ",".join(["%s"] * len(keys))
        cur.execute(
            f"SELECT remark_key FROM ke_pinus.{table} "
            f"WHERE order_no = %s AND remark_key IN ({placeholders})",
            (order_no, *keys),
        )
        existing_keys = {row["remark_key"] for row in cur.fetchall()}
        inserted = []
        for key, value in CATEGORY_ITEMS:
            if key not in existing_keys:
                cur.execute(
                    f"INSERT INTO ke_pinus.{table} (order_no, remark_key, remark_value) VALUES (%s, %s, %s)",
                    (order_no, key, value),
                )
                inserted.append((key, value))
    conn.commit()
    if inserted:
        print(f"\n[order_remark_ext] 类目字段补充")
        for key, value in inserted:
            print(f"  INSERT {key} = {value}")


def fetch_existing_amounts(conn, order_no: int) -> list[dict]:
    table = get_shard_table(order_no, "order_amount")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM ke_pinus.{table} WHERE order_no = %s ORDER BY amount_type",
            (order_no,),
        )
        return cur.fetchall()


def update_order_status(conn, order_no: int, status: int):
    table = get_shard_table(order_no, "order_base")
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE ke_pinus.{table} SET out_order_status = %s WHERE order_no = %s",
            (status, order_no),
        )
    conn.commit()
    print(f"  UPDATE out_order_status={status}")


def insert_missing_times(conn, order_no: int, to_insert: dict[str, datetime]):
    table = get_shard_table(order_no, "order_time_ext")
    with conn.cursor() as cur:
        for tt, tv in to_insert.items():
            cur.execute(
                f"INSERT INTO ke_pinus.{table} (order_no, time_type, time_value) VALUES (%s, %s, %s)",
                (order_no, tt, tv.strftime("%Y-%m-%d %H:%M:%S")),
            )
            print(f"  INSERT time_type={tt}  time_value={tv}")
    conn.commit()


def upsert_amounts(conn, order_no: int, amounts: dict[int, float], existing: list[dict], scene: str,
                   keep_codes: set[int] | None = None):
    table = get_shard_table(order_no, "order_amount")
    existing_types = {row["amount_type"] for row in existing}
    with conn.cursor() as cur:
        # 退单场景：删除不在保留集合里的字段
        if scene == "cancel" and keep_codes is not None:
            keep_types = {str(c) for c in keep_codes}
            for amount_type in sorted(existing_types - keep_types):
                cur.execute(
                    f"DELETE FROM ke_pinus.{table} WHERE order_no = %s AND amount_type = %s",
                    (order_no, amount_type),
                )
                print(f"  DELETE amount_type={amount_type}")
        for code, amount in sorted(amounts.items()):
            amount_type = str(code)
            if amount_type in existing_types:
                cur.execute(
                    f"UPDATE ke_pinus.{table} SET amount = %s WHERE order_no = %s AND amount_type = %s",
                    (amount, order_no, amount_type),
                )
                print(f"  UPDATE amount_type={amount_type}  amount={amount}")
            else:
                cur.execute(
                    f"INSERT INTO ke_pinus.{table} (order_no, amount_type, amount) VALUES (%s, %s, %s)",
                    (order_no, amount_type, amount),
                )
                print(f"  INSERT amount_type={amount_type}  amount={amount}")
    conn.commit()


# ---------------------------------------------------------------------------
# 展示
# ---------------------------------------------------------------------------

def print_status_diff(current: int | None, expected: int):
    action = "UPDATE" if current != expected else "一致"
    print(f"\n[order_base] out_order_status")
    print(f"  现有值: {current}  期望值: {expected}  → {action}")


def print_times_diff(existing: list[dict], to_insert: dict[str, datetime], scene: str):
    needed = SCENE_TIME_TYPES[scene]
    existing_map = {row["time_type"]: row["time_value"] for row in existing}
    print(f"\n[order_time_ext]")
    for tt in needed:
        if tt in existing_map:
            print(f"  {tt:<35} 现有: {existing_map[tt]}  → 一致（不覆盖）")
        else:
            print(f"  {tt:<35} 现有: -  期望: {to_insert[tt]}  → INSERT")


def print_amounts_diff(existing: list[dict], expected: dict[int, float], scene: str = "",
                       keep_codes: set[int] | None = None):
    existing_map = {int(row["amount_type"]): row["amount"] for row in existing}
    all_codes = sorted(set(existing_map) | set(expected))
    print(f"\n[order_amount]")
    print(f"  {'code':<6}  {'字段名':<52}  {'现有值':>10}  {'期望值':>10}  操作")
    print(f"  {'-'*95}")
    for code in all_codes:
        name = BSU_CODE_NAMES.get(code, "")
        cur_val = existing_map.get(code, "-")
        exp_val = expected.get(code, "-")
        if cur_val == "-":
            action = "INSERT"
        elif exp_val == "-":
            if scene == "cancel" and keep_codes is not None and code not in keep_codes:
                action = "DELETE"
            else:
                action = "不涉及"
        elif float(cur_val) != float(exp_val):
            action = "UPDATE"
        else:
            action = "一致"
        print(f"  {code:<6}  {name:<52}  {str(cur_val):>10}  {str(exp_val):>10}  {action}")


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--order_no", required=True, type=int)
    p.add_argument("--scene",   required=True, choices=["sign", "place", "finish", "cancel"])
    p.add_argument("--sign",    required=True, type=float, help="正签 contractAmount")
    p.add_argument("--place",   type=float, default=None,  help="下单 contractAmount")
    p.add_argument("--finish",  type=float, default=None,  help="履约完成 contractAmount")
    p.add_argument("--place-type",  choices=["normal", "cancel"], default="normal")
    p.add_argument("--finish-type", choices=["normal", "cancel"], default="normal")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--query-only", action="store_true")
    group.add_argument("--do-write",   action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    scene = args.scene

    expected_amounts = calc_amounts(
        scene=scene,
        sign=args.sign,
        place=args.place,
        finish=args.finish,
        place_type=args.place_type,
        finish_type=args.finish_type,
    )
    keep_codes: set[int] | None = expected_amounts.pop("_keep", None)
    expected_status = SCENE_STATUS[scene]

    cfg = load_config()
    conn = get_conn(cfg)

    existing_status_row = fetch_existing_status(conn, args.order_no)
    current_status = int(existing_status_row["out_order_status"]) if existing_status_row else None
    existing_times  = fetch_existing_times(conn, args.order_no)
    existing_amounts= fetch_existing_amounts(conn, args.order_no)

    existing_time_types = {row["time_type"] for row in existing_times}
    to_insert_times = calc_missing_times(scene, existing_time_types)

    print(f"\norder_no: {args.order_no}  scene: {scene}")
    print_status_diff(current_status, expected_status)
    print_times_diff(existing_times, to_insert_times, scene)
    print_amounts_diff(existing_amounts, expected_amounts, scene, keep_codes)

    if args.query_only:
        result = {
            "order_no": args.order_no,
            "scene": scene,
            "order_status": {
                "table": get_shard_table(args.order_no, "order_base"),
                "current": current_status,
                "expected": expected_status,
                "action": "UPDATE" if current_status != expected_status else "一致",
            },
            "times": {
                "table": get_shard_table(args.order_no, "order_time_ext"),
                "existing": existing_times,
                "to_insert": list(to_insert_times.keys()),
            },
            "amounts": {
                "table": get_shard_table(args.order_no, "order_amount"),
                "existing": existing_amounts,
                "expected": {str(k): v for k, v in expected_amounts.items()},
            },
        }
        print(f"\n__QUERY_RESULT_JSON__\n{json.dumps(result, ensure_ascii=False, default=str)}")
        return

    # --do-write
    print("\n写入中...")
    ensure_category_remarks(conn, args.order_no)
    update_order_status(conn, args.order_no, expected_status)
    if to_insert_times:
        insert_missing_times(conn, args.order_no, to_insert_times)
    upsert_amounts(conn, args.order_no, expected_amounts, existing_amounts, scene, keep_codes)
    print("\n写入完成。")


if __name__ == "__main__":
    main()
