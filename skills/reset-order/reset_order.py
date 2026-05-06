"""
reset_order.py

用法：
  python reset_order.py --order_no 6574192984971878400 --query-only
  python reset_order.py --order_no 6574192984971878400 --do-delete
  python reset_order.py --order_no 111,222,333 --query-only
"""

import argparse
import json
import sys
from pathlib import Path

import pymysql
import pymysql.cursors

try:
    import tomllib
except ImportError:
    import tomli as tomllib


_SCRIPT_DIR = Path(__file__).parent
_CONFIG_CANDIDATES = [
    _SCRIPT_DIR / "reset_order.local.toml",       # 项目本地配置（已 gitignore）
    Path.home() / ".zsy_tools" / "reset_order.toml",  # 全局配置
]


def load_config():
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    print(f"[错误] 未找到配置文件，请创建以下任意一个：")
    for p in _CONFIG_CANDIDATES:
        print(f"  {p}")
    print("参考 config.example.toml 填写内容")
    sys.exit(1)


def get_conn(cfg: dict):
    return pymysql.connect(
        host=cfg["host"],
        port=cfg.get("port", 3306),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


def fetch_ids(conn, sql: str, params=None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
    if not rows:
        return []
    key = list(rows[0].keys())[0]
    return [row[key] for row in rows]


def fmt_ids(ids: list) -> str:
    if not ids:
        return "跳过（无数据）"
    preview = ids[:10]
    suffix = f"...共 {len(ids)} 条" if len(ids) > 10 else f"共 {len(ids)} 条"
    return f"{preview}  {suffix}"


def query_all(order_no: str, conn_betula, conn_contribute) -> dict:
    result = {"order_no": order_no}

    # ── cashcow_betula ──────────────────────────────────────────
    betula_order_ids = fetch_ids(
        conn_betula,
        "SELECT id FROM orders WHERE order_id = %s",
        (order_no,),
    )
    result["betula_order_id"] = betula_order_ids[0] if betula_order_ids else None

    if result["betula_order_id"]:
        pd_ids = fetch_ids(
            conn_betula,
            "SELECT id FROM performance_detail WHERE order_id = %s",
            (result["betula_order_id"],),
        )
    else:
        pd_ids = []
    result["performance_detail_ids"] = pd_ids

    if pd_ids:
        fmt = ",".join(["%s"] * len(pd_ids))
        ext_ids = fetch_ids(
            conn_betula,
            f"SELECT id FROM performance_detail_ext WHERE performance_detail_id IN ({fmt})",
            tuple(pd_ids),
        )
    else:
        ext_ids = []
    result["performance_detail_ext_ids"] = ext_ids

    # ── sign_contribute ─────────────────────────────────────────
    assign_ids = fetch_ids(
        conn_contribute,
        "SELECT id FROM assign_order WHERE order_no = %s",
        (order_no,),
    )
    result["assign_id"] = assign_ids[0] if assign_ids else None

    rc_ids = fetch_ids(
        conn_contribute,
        "SELECT id FROM rec_contribute WHERE order_no = %s",
        (order_no,),
    )
    result["rec_contribute_ids"] = rc_ids

    if rc_ids:
        fmt = ",".join(["%s"] * len(rc_ids))
        rcn_ids = fetch_ids(
            conn_contribute,
            f"SELECT id FROM rec_contribute_node WHERE contribute_id IN ({fmt})",
            tuple(rc_ids),
        )
    else:
        rcn_ids = []
    result["rec_contribute_node_ids"] = rcn_ids

    rr_ids = fetch_ids(
        conn_contribute,
        "SELECT id FROM rec_receipt WHERE order_no = %s",
        (order_no,),
    )
    result["rec_receipt_ids"] = rr_ids

    if result["assign_id"]:
        asv_ids = fetch_ids(
            conn_contribute,
            "SELECT id FROM assign_step_version WHERE assign_id = %s",
            (result["assign_id"],),
        )
    else:
        asv_ids = []
    result["assign_step_version_ids"] = asv_ids

    if asv_ids:
        fmt = ",".join(["%s"] * len(asv_ids))
        an_ids = fetch_ids(
            conn_contribute,
            f"SELECT id FROM assign_node WHERE assign_step_version_id IN ({fmt})",
            tuple(asv_ids),
        )
    else:
        an_ids = []
    result["assign_node_ids"] = an_ids

    if result["assign_id"]:
        rv_ids = fetch_ids(
            conn_contribute,
            "SELECT id FROM role_version WHERE assign_id = %s",
            (result["assign_id"],),
        )
    else:
        rv_ids = []
    result["role_version_ids"] = rv_ids

    if rv_ids:
        fmt = ",".join(["%s"] * len(rv_ids))
        rd_ids = fetch_ids(
            conn_contribute,
            f"SELECT id FROM role_detail WHERE role_version_id IN ({fmt})",
            tuple(rv_ids),
        )
    else:
        rd_ids = []
    result["role_detail_ids"] = rd_ids

    return result


def print_query_result(r: dict):
    order_no = r["order_no"]
    print(f"\n=== order_no: {order_no} ===")
    print("--- 查询结果 ---")
    print(f"[cashcow_betula]")
    print(f"  performance_detail_ext  : {fmt_ids(r['performance_detail_ext_ids'])}")
    print(f"  performance_detail      : {fmt_ids(r['performance_detail_ids'])}")
    print(f"[sign_contribute]")
    print(f"  rec_contribute_node     : {fmt_ids(r['rec_contribute_node_ids'])}")
    print(f"  rec_contribute          : {fmt_ids(r['rec_contribute_ids'])}")
    print(f"  rec_receipt             : {fmt_ids(r['rec_receipt_ids'])}")
    print(f"  assign_node             : {fmt_ids(r['assign_node_ids'])}")
    print(f"  assign_step_version     : {fmt_ids(r['assign_step_version_ids'])}")
    print(f"  role_detail             : {fmt_ids(r['role_detail_ids'])}")
    print(f"  role_version            : {fmt_ids(r['role_version_ids'])}")


def delete_by_ids(conn, table: str, ids: list) -> int:
    if not ids:
        return 0
    fmt = ",".join(["%s"] * len(ids))
    with conn.cursor() as cur:
        affected = cur.execute(f"DELETE FROM {table} WHERE id IN ({fmt})", tuple(ids))
    conn.commit()
    return affected


def delete_single(conn, table: str, id_val) -> int:
    if not id_val:
        return 0
    with conn.cursor() as cur:
        affected = cur.execute(f"DELETE FROM {table} WHERE id = %s", (id_val,))
    conn.commit()
    return affected


def do_delete(r: dict, conn_betula, conn_contribute, cfg: dict):
    order_no = r["order_no"]
    print(f"\n=== order_no: {order_no} ===")
    print("--- 删除阶段 ---")

    def log(label, affected, ids):
        if not ids:
            print(f"  [跳过] {label}（无数据）")
        else:
            print(f"  [删除] {label:<30}: {affected} 行")

    # 一、业绩中台
    print("[一-业绩中台]")
    n = delete_by_ids(conn_betula, "performance_detail_ext", r["performance_detail_ext_ids"])
    log("performance_detail_ext", n, r["performance_detail_ext_ids"])
    n = delete_by_ids(conn_betula, "performance_detail", r["performance_detail_ids"])
    log("performance_detail", n, r["performance_detail_ids"])

    # 二、业绩计算
    print("[二-业绩计算]")
    n = delete_by_ids(conn_contribute, "rec_contribute_node", r["rec_contribute_node_ids"])
    log("rec_contribute_node", n, r["rec_contribute_node_ids"])
    n = delete_by_ids(conn_contribute, "rec_contribute", r["rec_contribute_ids"])
    log("rec_contribute", n, r["rec_contribute_ids"])
    n = delete_by_ids(conn_contribute, "rec_receipt", r["rec_receipt_ids"])
    log("rec_receipt", n, r["rec_receipt_ids"])

    # 三、初始化
    print("[三-初始化]")
    n = delete_by_ids(conn_contribute, "assign_node", r["assign_node_ids"])
    log("assign_node", n, r["assign_node_ids"])
    n = delete_by_ids(conn_contribute, "assign_step_version", r["assign_step_version_ids"])
    log("assign_step_version", n, r["assign_step_version_ids"])

    # 四、角色认定
    print("[四-角色认定]")
    n = delete_by_ids(conn_contribute, "role_detail", r["role_detail_ids"])
    log("role_detail", n, r["role_detail_ids"])
    n = delete_by_ids(conn_contribute, "role_version", r["role_version_ids"])
    log("role_version", n, r["role_version_ids"])



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--order_no", required=True, help="订单号，多个用逗号分隔")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query-only", action="store_true", help="只查询，输出 JSON")
    group.add_argument("--do-delete", action="store_true", help="执行删除")
    args = parser.parse_args()

    order_nos = [o.strip() for o in args.order_no.split(",") if o.strip()]
    cfg = load_config()

    conn_betula = get_conn(cfg["db_betula"])
    conn_contribute = get_conn(cfg["db_contribute"])

    try:
        results = []
        for order_no in order_nos:
            r = query_all(order_no, conn_betula, conn_contribute)
            results.append(r)
            if args.query_only:
                print_query_result(r)

        if args.query_only:
            # 输出 JSON 供 skill 读取
            print("\n__QUERY_RESULT_JSON__")
            print(json.dumps(results, ensure_ascii=False))
            return

        # --do-delete
        for r in results:
            print_query_result(r)
            do_delete(r, conn_betula, conn_contribute, cfg)

        order_nos_str = ", ".join(order_nos)
        print(f"\n✅ 业绩数据清理完成！")
        print(f"订单号：{order_nos_str}")
        
    finally:
        conn_betula.close()
        conn_contribute.close()


if __name__ == "__main__":
    main()
