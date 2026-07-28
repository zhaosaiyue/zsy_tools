"""
sharing_reset.py

用法：
  python sharing_reset.py --contract_no BJ123456 --query-only
  python sharing_reset.py --contract_no BJ123456 --do-delete
  python sharing_reset.py --contract_no BJ123456,SH654321 --query-only
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
    _SCRIPT_DIR / "sharing_reset.local.toml",
    Path.home() / ".zsy_tools" / "sharing_reset.toml",
]


def load_config():
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    print("[错误] 未找到配置文件，请创建以下任意一个：")
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
        autocommit=False,
    )


def fetch_rows(conn, sql: str, params=None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def fetch_ids(conn, sql: str, params=None) -> list:
    rows = fetch_rows(conn, sql, params)
    if not rows:
        return []
    key = list(rows[0].keys())[0]
    return [row[key] for row in rows]


def table_exists(conn, table: str) -> bool:
    row = fetch_first(
        conn,
        """
        SELECT COUNT(*) cnt
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table,),
    )
    return bool(row and row["cnt"])


def fetch_ids_optional(conn, table: str, sql: str, params=None) -> list:
    if not table_exists(conn, table):
        return []
    return fetch_ids(conn, sql, params)


def fetch_first(conn, sql: str, params=None):
    rows = fetch_rows(conn, sql, params)
    return rows[0] if rows else None


def fetch_count(conn, table: str, where_sql: str, params=None) -> int:
    row = fetch_first(conn, f"SELECT COUNT(*) cnt FROM {table} WHERE {where_sql}", params)
    return int(row["cnt"]) if row else 0


def count_by_ids(ids: list) -> int:
    return len(ids or [])


def fmt_ids(ids: list) -> str:
    if not ids:
        return "跳过（无数据）"
    preview = ids[:10]
    suffix = f"...共 {len(ids)} 条" if len(ids) > 10 else f"共 {len(ids)} 条"
    return f"{preview}  {suffix}"


def in_clause(ids: list) -> tuple:
    return ",".join(["%s"] * len(ids)), tuple(ids)


def get_order_info(conn_main, contract_no: str) -> dict:
    row = fetch_first(
        conn_main,
        """
        SELECT id, contract_no, business_id, finance_order_id, money_type
        FROM order_info
        WHERE contract_no = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (contract_no,),
    )
    return row or {}


def get_base_ids(conn_main, order_info_id) -> tuple:
    if not order_info_id:
        return [], []
    receivable_ids = fetch_ids(
        conn_main,
        "SELECT id FROM receivable WHERE contract_id = %s",
        (order_info_id,),
    )
    paidup_ids = fetch_ids(
        conn_main,
        "SELECT id FROM paidup WHERE contract_id = %s",
        (order_info_id,),
    )
    return receivable_ids, paidup_ids


def query_ids(conn, order_info_id, contract_no: str) -> dict:
    ids = {}
    if not order_info_id:
        ids["plan_uuids"] = fetch_ids(
            conn,
            "SELECT uuid FROM sharing_fulfill_plan WHERE contract_no = %s",
            (contract_no,),
        )
        ids["re_sharing_record"] = fetch_ids_optional(
            conn,
            "re_sharing_record",
            "SELECT id FROM re_sharing_record WHERE contract_no = %s",
            (contract_no,),
        )
        return ids

    # 应分
    ids["receivable_item_charge"] = fetch_ids(conn, "SELECT id FROM receivable_item_charge WHERE contract_id = %s", (order_info_id,))
    ids["receivable_item_charge_detail"] = fetch_ids(conn, "SELECT id FROM receivable_item_charge_detail WHERE contract_id = %s", (order_info_id,))
    ids["receivable_item_charge_plat"] = fetch_ids(conn, "SELECT id FROM receivable_item_charge_plat WHERE contract_id = %s", (order_info_id,))
    ids["receivable_sub_account_detail"] = fetch_ids(conn, "SELECT id FROM receivable_sub_account_detail WHERE contract_id = %s", (order_info_id,))
    ids["receivable_item_charge_extend"] = fetch_ids(conn, "SELECT id FROM receivable_item_charge_extend WHERE contract_id = %s", (order_info_id,))
    ids["receivable_charge_version"] = fetch_ids(conn, "SELECT id FROM receivable_charge_version WHERE order_info_id = %s", (order_info_id,))
    if ids["receivable_item_charge_detail"]:
        fmt, params = in_clause(ids["receivable_item_charge_detail"])
        ids["receivable_charge_rate_detail"] = fetch_ids(conn, f"SELECT id FROM receivable_charge_rate_detail WHERE receivable_charge_detail_id IN ({fmt})", params)
    else:
        ids["receivable_charge_rate_detail"] = []
    if ids["receivable_item_charge_plat"]:
        fmt, params = in_clause(ids["receivable_item_charge_plat"])
        ids["receivable_charge_rate_plat"] = fetch_ids(conn, f"SELECT id FROM receivable_charge_rate_plat WHERE receivable_charge_plat_id IN ({fmt})", params)
    else:
        ids["receivable_charge_rate_plat"] = []
    if ids["receivable_sub_account_detail"]:
        fmt, params = in_clause(ids["receivable_sub_account_detail"])
        ids["receivable_sub_account_rate"] = fetch_ids(conn, f"SELECT id FROM receivable_sub_account_rate WHERE detail_id IN ({fmt})", params)
    else:
        ids["receivable_sub_account_rate"] = []
    if ids["receivable_charge_version"]:
        fmt, params = in_clause(ids["receivable_charge_version"])
        ids["receivable_charge_version_item"] = fetch_ids(conn, f"SELECT id FROM receivable_charge_version_item WHERE receivable_charge_version_id IN ({fmt})", params)
    else:
        ids["receivable_charge_version_item"] = []
    if ids["receivable_charge_version_item"]:
        fmt, params = in_clause(ids["receivable_charge_version_item"])
        ids["receivable_charge_version_scenario"] = fetch_ids(conn, f"SELECT id FROM receivable_charge_version_scenario WHERE receivable_charge_item_version_id IN ({fmt})", params)
    else:
        ids["receivable_charge_version_scenario"] = []

    # 实分
    ids["paidup_item_charge"] = fetch_ids(conn, "SELECT id FROM paidup_item_charge WHERE contract_id = %s", (order_info_id,))
    ids["paidup_item_charge_detail"] = fetch_ids(conn, "SELECT id FROM paidup_item_charge_detail WHERE contract_id = %s", (order_info_id,))
    ids["paidup_item_charge_plat"] = fetch_ids(conn, "SELECT id FROM paidup_item_charge_plat WHERE contract_id = %s", (order_info_id,))
    ids["paidup_sub_account_detail"] = fetch_ids(conn, "SELECT id FROM paidup_sub_account_detail WHERE contract_id = %s", (order_info_id,))
    ids["paidup_item_charge_extend"] = fetch_ids(conn, "SELECT id FROM paidup_item_charge_extend WHERE contract_id = %s", (order_info_id,))
    ids["paidup_item_charge_freeze_extend"] = fetch_ids(conn, "SELECT id FROM paidup_item_charge_freeze_extend WHERE contract_id = %s", (order_info_id,))
    ids["paidup_charge_version"] = fetch_ids(conn, "SELECT id FROM paidup_charge_version WHERE order_info_id = %s", (order_info_id,))
    if ids["paidup_item_charge_detail"]:
        fmt, params = in_clause(ids["paidup_item_charge_detail"])
        ids["paidup_charge_rate_detail"] = fetch_ids(conn, f"SELECT id FROM paidup_charge_rate_detail WHERE paidup_charge_detail_id IN ({fmt})", params)
    else:
        ids["paidup_charge_rate_detail"] = []
    if ids["paidup_item_charge_plat"]:
        fmt, params = in_clause(ids["paidup_item_charge_plat"])
        ids["paidup_charge_rate_plat"] = fetch_ids(conn, f"SELECT id FROM paidup_charge_rate_plat WHERE paidup_charge_plat_id IN ({fmt})", params)
    else:
        ids["paidup_charge_rate_plat"] = []
    if ids["paidup_sub_account_detail"]:
        fmt, params = in_clause(ids["paidup_sub_account_detail"])
        ids["paidup_sub_account_rate"] = fetch_ids(conn, f"SELECT id FROM paidup_sub_account_rate WHERE detail_id IN ({fmt})", params)
    else:
        ids["paidup_sub_account_rate"] = []
    if ids["paidup_charge_version"]:
        fmt, params = in_clause(ids["paidup_charge_version"])
        ids["paidup_charge_version_item"] = fetch_ids(conn, f"SELECT id FROM paidup_charge_version_item WHERE paidup_charge_version_id IN ({fmt})", params)
    else:
        ids["paidup_charge_version_item"] = []
    if ids["paidup_charge_version_item"]:
        fmt, params = in_clause(ids["paidup_charge_version_item"])
        ids["paidup_charge_version_scenario"] = fetch_ids(conn, f"SELECT id FROM paidup_charge_version_scenario WHERE paidup_charge_item_version_id IN ({fmt})", params)
    else:
        ids["paidup_charge_version_scenario"] = []

    # 履约计划/结算
    ids["plan_uuids"] = fetch_ids(
        conn,
        "SELECT uuid FROM sharing_fulfill_plan WHERE order_info_id = %s OR contract_no = %s",
        (order_info_id, contract_no),
    )
    if ids["plan_uuids"]:
        fmt, params = in_clause(ids["plan_uuids"])
        ids["sharing_fulfill_plan_detail"] = fetch_ids(conn, f"SELECT id FROM sharing_fulfill_plan_detail WHERE plan_uuid IN ({fmt})", params)
        ids["sharing_settle_detail"] = fetch_ids(conn, f"SELECT id FROM sharing_settle_detail WHERE plan_uuid IN ({fmt})", params)
    else:
        ids["sharing_fulfill_plan_detail"] = []
        ids["sharing_settle_detail"] = []
    if ids["sharing_settle_detail"]:
        fmt, params = in_clause(ids["sharing_settle_detail"])
        ids["sharing_settle_detail_ref"] = fetch_ids(conn, f"SELECT id FROM sharing_settle_detail_ref WHERE settle_detail_id IN ({fmt})", params)
    else:
        ids["sharing_settle_detail_ref"] = []
    ids["sharing_fulfill_plan"] = fetch_ids(
        conn,
        "SELECT id FROM sharing_fulfill_plan WHERE order_info_id = %s OR contract_no = %s",
        (order_info_id, contract_no),
    )

    # 流程辅助
    ids["re_sharing_record"] = fetch_ids_optional(conn, "re_sharing_record", "SELECT id FROM re_sharing_record WHERE contract_no = %s", (contract_no,))
    ids["op_sharing_log"] = fetch_ids_optional(conn, "op_sharing_log", "SELECT id FROM op_sharing_log WHERE order_id = %s OR contract_no = %s", (order_info_id, contract_no))
    ids["biz_execute_record"] = fetch_ids_optional(conn, "biz_execute_record", "SELECT id FROM biz_execute_record WHERE execute_no = %s", (str(order_info_id),))
    if ids["biz_execute_record"]:
        fmt, params = in_clause(ids["biz_execute_record"])
        ids["biz_execute_record_param"] = fetch_ids_optional(conn, "biz_execute_record_param", f"SELECT id FROM biz_execute_record_param WHERE record_id IN ({fmt})", params)
    else:
        ids["biz_execute_record_param"] = []
    ids["sharing_exception_log"] = fetch_ids_optional(conn, "sharing_exception_log", "SELECT id FROM sharing_exception_log WHERE contract_id = %s", (str(order_info_id),))
    ids["sync_lft_item_charge"] = fetch_ids_optional(conn, "sync_lft_item_charge", "SELECT id FROM sync_lft_item_charge WHERE contract_id = %s", (order_info_id,))
    if ids["sync_lft_item_charge"]:
        fmt, params = in_clause(ids["sync_lft_item_charge"])
        ids["charge_sync_lft_related"] = fetch_ids_optional(conn, "charge_sync_lft_related", f"SELECT id FROM charge_sync_lft_related WHERE sync_lft_id IN ({fmt})", params)
    else:
        ids["charge_sync_lft_related"] = []
    return ids


def query_all(contract_no: str, conn_main, conn_sharing) -> dict:
    order_info = get_order_info(conn_main, contract_no)
    order_info_id = order_info.get("id")
    receivable_ids, paidup_ids = get_base_ids(conn_main, order_info_id)
    ids = query_ids(conn_sharing, order_info_id, contract_no)
    counts = {key: count_by_ids(value) for key, value in ids.items()}
    counts["receivable_ids"] = len(receivable_ids)
    counts["paidup_ids"] = len(paidup_ids)
    return {
        "contract_no": contract_no,
        "order_info": order_info,
        "receivable_ids": receivable_ids,
        "paidup_ids": paidup_ids,
        "ids": ids,
        "counts": counts,
    }


def print_line(label: str, count: int):
    print(f"  {label:<38}: {count} 条")


def print_query_result(r: dict):
    order_info = r["order_info"] or {}
    counts = r["counts"]
    print(f"\n=== contract_no: {r['contract_no']} ===")
    print("--- 查询结果 ---")
    print(f"order_info_id: {order_info.get('id')}")
    print(f"business_id: {order_info.get('business_id')}")
    print(f"receivable_ids: {fmt_ids(r['receivable_ids'])}")
    print(f"paidup_ids: {fmt_ids(r['paidup_ids'])}")
    print("[应分]")
    for table in [
        "receivable_sub_account_rate",
        "receivable_sub_account_detail",
        "receivable_charge_rate_plat",
        "receivable_item_charge_plat",
        "receivable_charge_rate_detail",
        "receivable_item_charge_detail",
        "receivable_item_charge_extend",
        "receivable_item_charge",
        "receivable_charge_version_scenario",
        "receivable_charge_version_item",
        "receivable_charge_version",
    ]:
        print_line(table, counts.get(table, 0))
    print("[实分]")
    for table in [
        "paidup_sub_account_rate",
        "paidup_sub_account_detail",
        "paidup_charge_rate_plat",
        "paidup_item_charge_plat",
        "paidup_charge_rate_detail",
        "paidup_item_charge_detail",
        "paidup_item_charge_freeze_extend",
        "paidup_item_charge_extend",
        "paidup_item_charge",
        "paidup_charge_version_scenario",
        "paidup_charge_version_item",
        "paidup_charge_version",
    ]:
        print_line(table, counts.get(table, 0))
    print("[履约计划/结算]")
    for table in [
        "sharing_settle_detail_ref",
        "sharing_settle_detail",
        "sharing_fulfill_plan_detail",
        "sharing_fulfill_plan",
    ]:
        print_line(table, counts.get(table, 0))
    print("[流程辅助]")
    for table in [
        "charge_sync_lft_related",
        "sync_lft_item_charge",
        "biz_execute_record_param",
        "biz_execute_record",
        "sharing_exception_log",
        "op_sharing_log",
        "re_sharing_record",
    ]:
        print_line(table, counts.get(table, 0))


def delete_by_ids(conn, table: str, ids: list) -> int:
    if not ids:
        return 0
    fmt, params = in_clause(ids)
    with conn.cursor() as cur:
        affected = cur.execute(f"DELETE FROM {table} WHERE id IN ({fmt})", params)
    conn.commit()
    return affected


def delete_by_uuids(conn, table: str, uuid_col: str, uuids: list) -> int:
    if not uuids:
        return 0
    fmt, params = in_clause(uuids)
    with conn.cursor() as cur:
        affected = cur.execute(f"DELETE FROM {table} WHERE {uuid_col} IN ({fmt})", params)
    conn.commit()
    return affected


def do_delete(r: dict, conn_sharing):
    ids = r["ids"]
    print(f"\n=== contract_no: {r['contract_no']} ===")
    print("--- 删除阶段 ---")

    def log(label, affected, id_list):
        if not id_list:
            print(f"  [跳过] {label}（无数据）")
        else:
            print(f"  [删除] {label:<38}: {affected} 行")

    delete_order = [
        "receivable_sub_account_rate",
        "receivable_sub_account_detail",
        "receivable_charge_rate_plat",
        "receivable_item_charge_plat",
        "receivable_charge_rate_detail",
        "receivable_item_charge_detail",
        "receivable_item_charge_extend",
        "receivable_item_charge",
        "receivable_charge_version_scenario",
        "receivable_charge_version_item",
        "receivable_charge_version",
        "paidup_sub_account_rate",
        "paidup_sub_account_detail",
        "paidup_charge_rate_plat",
        "paidup_item_charge_plat",
        "paidup_charge_rate_detail",
        "paidup_item_charge_detail",
        "paidup_item_charge_freeze_extend",
        "paidup_item_charge_extend",
        "paidup_item_charge",
        "paidup_charge_version_scenario",
        "paidup_charge_version_item",
        "paidup_charge_version",
        "sharing_settle_detail_ref",
        "sharing_settle_detail",
        "sharing_fulfill_plan_detail",
        "sharing_fulfill_plan",
        "charge_sync_lft_related",
        "sync_lft_item_charge",
        "biz_execute_record_param",
        "biz_execute_record",
        "sharing_exception_log",
        "op_sharing_log",
        "re_sharing_record",
    ]

    for table in delete_order:
        n = delete_by_ids(conn_sharing, table, ids.get(table, []))
        log(table, n, ids.get(table, []))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract_no", required=True, help="合同编号，多个用逗号分隔")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query-only", action="store_true", help="只查询，输出 JSON")
    group.add_argument("--do-delete", action="store_true", help="执行删除")
    args = parser.parse_args()

    contract_nos = [o.strip() for o in args.contract_no.split(",") if o.strip()]
    cfg = load_config()

    conn_main = get_conn(cfg["db_main"])
    conn_sharing = get_conn(cfg["db_sharing"])
    try:
        results = []
        for contract_no in contract_nos:
            r = query_all(contract_no, conn_main, conn_sharing)
            results.append(r)
            print_query_result(r)

        if args.query_only:
            print("\n__QUERY_RESULT_JSON__")
            print(json.dumps(results, ensure_ascii=False, default=str))
            return

        for r in results:
            do_delete(r, conn_sharing)

        contract_nos_str = ", ".join(contract_nos)
        print("\n分账数据清理完成！")
        print(f"合同编号：{contract_nos_str}")
    finally:
        conn_main.close()
        conn_sharing.close()


if __name__ == "__main__":
    main()
