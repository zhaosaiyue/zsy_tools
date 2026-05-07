"""
ke-pinus 分表路由工具

算法：
    res = order_no % first_num
    if res >= shard_num:
        res = order_no % shard_num
    table = base_name + "_" + str(res)
"""

# 各表分片配置：base_name -> (first_num, shard_num)
SHARD_CONFIG = {
    "order_base":          (11,  8),
    "order_amount":        (37,  32),
    "order_contract":      (17,  16),
    "order_fee":           (67,  64),
    "order_user_role":     (67,  64),
    "order_process_flow":  (131, 128),
    "order_status_ext":    (17,  16),
    "order_time_ext":      (17,  16),
    "order_role_detail":   (521, 512),
    "order_role_version":  (67,  64),
    "order_role":          (11,  8),
    "order_remark_ext":    (17,  16),
}


def shard_index(order_no: int, first_num: int, shard_num: int) -> int:
    res = order_no % first_num
    if res >= shard_num:
        res = order_no % shard_num
    return res


def get_table_name(base_name: str, order_no: int) -> str:
    first_num, shard_num = SHARD_CONFIG[base_name]
    idx = shard_index(order_no, first_num, shard_num)
    return f"{base_name}_{idx}"


def get_all_tables(order_no: int) -> dict:
    return {base: get_table_name(base, order_no) for base in SHARD_CONFIG}


DEFAULT_ORDER_NO = 6585951162319339521

if __name__ == "__main__":
    import sys
    from collections import defaultdict

    order_no = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ORDER_NO
    print(f"order_no: {order_no}\n")

    # 按 (first_num, shard_num) 配置分组，同组路由结果一致
    groups: dict[tuple, list[str]] = defaultdict(list)
    for base, cfg in SHARD_CONFIG.items():
        groups[cfg].append(base)

    all_tables = get_all_tables(order_no)
    for cfg in sorted(groups, key=lambda c: c[1]):
        for base in groups[cfg]:
            print(all_tables[base])