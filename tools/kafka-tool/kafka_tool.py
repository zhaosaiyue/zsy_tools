"""
kafka_tool.py  —  Kafka 消息发送工具

用法：
  python kafka_tool.py --topic finance_performance_perf_change --message '{"orderNo":"123"}'
  python kafka_tool.py --topic xxx --file /tmp/msg.json
  python kafka_tool.py --topic xxx --key "orderNo" --message '{"orderNo":"123"}'
  python kafka_tool.py --topic xxx --header traceId=abc --header source=test --message '{...}'
  python kafka_tool.py --config ~/other_cluster.toml --topic xxx --message '{...}'
  python kafka_tool.py --message '{"orderNo":"123"}'   # 使用配置里的 default_topic
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    from kafka import KafkaProducer, KafkaAdminClient, KafkaConsumer, TopicPartition
    from kafka.errors import KafkaError
except ImportError:
    print("[错误] 缺少依赖：pip install kafka-python")
    sys.exit(1)


_SCRIPT_DIR = Path(__file__).parent
_CONFIG_CANDIDATES = [
    _SCRIPT_DIR / "kafka_tool.local.toml",
    Path.home() / ".zsy_tools" / "kafka_tool.toml",
]


def load_config(config_path: str | None) -> dict:
    if config_path:
        p = Path(config_path).expanduser()
        if not p.exists():
            print(f"[错误] 指定的配置文件不存在：{p}")
            sys.exit(1)
        with open(p, "rb") as f:
            return tomllib.load(f)

    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)

    print("[错误] 未找到配置文件，请创建以下任意一个：")
    for p in _CONFIG_CANDIDATES:
        print(f"  {p}")
    print(f"参考 {_SCRIPT_DIR / 'config.example.toml'} 填写内容")
    sys.exit(1)


def build_producer(cfg: dict) -> KafkaProducer:
    servers = [s.strip() for s in cfg["bootstrap_servers"].split(",")]
    protocol = cfg.get("security_protocol", "PLAINTEXT").upper()
    timeout = cfg.get("request_timeout_ms", 10000)

    kwargs = {
        "bootstrap_servers": servers,
        "security_protocol": protocol,
        "request_timeout_ms": timeout,
        "value_serializer": lambda v: v.encode("utf-8") if isinstance(v, str) else v,
        "key_serializer": lambda k: k.encode("utf-8") if isinstance(k, str) else k,
    }

    mechanism = cfg.get("sasl_mechanism", "").strip()
    if mechanism:
        kwargs["sasl_mechanism"] = mechanism
        kwargs["sasl_plain_username"] = cfg.get("sasl_username", "")
        kwargs["sasl_plain_password"] = cfg.get("sasl_password", "")

    return KafkaProducer(**kwargs)


_DATA_FILE = _SCRIPT_DIR / "kafka_data"


def parse_message(args) -> str:
    if args.message and args.file:
        print("[错误] --message 和 --file 不能同时使用")
        sys.exit(1)

    if args.file:
        p = Path(args.file).expanduser()
        if not p.exists():
            print(f"[错误] 文件不存在：{p}")
            sys.exit(1)
        raw = p.read_text(encoding="utf-8").strip()
    elif args.message:
        raw = args.message.strip()
    else:
        if not _DATA_FILE.exists() or not _DATA_FILE.read_text(encoding="utf-8").strip():
            print(f"[提示] 请将消息体粘贴到 {_DATA_FILE}，或使用 --message / --file 参数")
            sys.exit(1)
        raw = _DATA_FILE.read_text(encoding="utf-8").strip()
        print(f"[kafka-tool] 读取消息体来自 kafka_data")

    try:
        json.loads(raw)
    except json.JSONDecodeError:
        print("[警告] 消息内容不是合法 JSON，将原样发送")

    return raw


def parse_headers(header_args: list[str]) -> list[tuple[str, bytes]]:
    """解析 key=value 格式的 header 列表"""
    headers = []
    for h in (header_args or []):
        if "=" not in h:
            print(f"[警告] header 格式错误（应为 key=value）：{h}，已跳过")
            continue
        k, v = h.split("=", 1)
        headers.append((k.strip(), v.strip().encode("utf-8")))
    return headers


def check_members(cfg: dict, group: str):
    """查询当前 consumer group 里有哪些消费者实例在线（显示 IP/host）"""
    servers = [s.strip() for s in cfg["bootstrap_servers"].split(",")]
    admin = KafkaAdminClient(bootstrap_servers=servers)

    try:
        described = admin.describe_consumer_groups([group])
    finally:
        admin.close()

    if not described:
        print(f"[错误] 找不到 group：{group}")
        return

    group_info = described[0]
    members = group_info.members

    print(f"\n── consumer group 成员 ───────────────────────────")
    print(f"  消费者组：{group}")
    print(f"  状态    ：{group_info.state}")
    print(f"  成员数  ：{len(members)} 个")
    print(f"──────────────────────────────────────────────────")

    if not members:
        print("  （当前没有在线的消费者）")
    else:
        for i, m in enumerate(members, 1):
            # client_id 通常包含服务名+host，host 是连接来源 IP
            print(f"  [{i}] host      : {m.client_host}")
            print(f"      client_id : {m.client_id}")
            print(f"      member_id : {m.member_id[:40]}...")
            print()
    print()


def check_offset(cfg: dict, topic: str, group: str):
    """
    查询消费者进度。
    Kafka 每个 topic 分成若干个"分区（partition）"存消息，每条消息有一个编号（offset）。
    消费者每次读完一批消息后，会记录自己读到哪了（committed offset）。
    LAG = 队列最新编号 - 消费者读到的编号，LAG=0 表示没有积压，消息都被消费了。
    """
    servers = [s.strip() for s in cfg["bootstrap_servers"].split(",")]

    consumer = KafkaConsumer(
        bootstrap_servers=servers,
        group_id=group,
        enable_auto_commit=False,
    )

    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        print(f"[错误] topic 不存在或无法访问：{topic}")
        consumer.close()
        return

    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    consumer.assign(tps)

    end_offsets = consumer.end_offsets(tps)
    committed = {tp: consumer.committed(tp) for tp in tps}
    consumer.close()

    print(f"\n── 消费进度查询 ──────────────────────────────────")
    print(f"  消息队列（topic） : {topic}")
    print(f"  消费者组（group） : {group}")
    print(f"──────────────────────────────────────────────────")
    print(f"  {'分区':<6} {'消费者读到':<12} {'队列最新':<12} {'积压(LAG)'}")
    print(f"  {'-'*46}")

    total_lag = 0
    for tp in tps:
        latest = end_offsets[tp]
        com = committed[tp]
        com_str = str(com) if com is not None else "（未提交）"
        lag = (latest - com) if com is not None else "?"
        total_lag += lag if isinstance(lag, int) else 0
        lag_str = str(lag) if lag != 0 else "0 ✅"
        print(f"  {tp.partition:<6} {com_str:<12} {latest:<12} {lag_str}")

    print(f"  {'-'*46}")
    print(f"  总积压：{total_lag} 条")

    print()
    if total_lag == 0:
        print("  结论：消息已被消费者拉走（LAG=0）")
        print("         但消费者代码里可能没打日志，或走了某个分支直接返回了")
        print("         建议检查消费者入口代码，确认消息内容是否符合处理条件")
    else:
        print(f"  结论：消费者还没读到这条消息，积压了 {total_lag} 条")
        print("         可能原因：消费者服务没启动 / 连的不是同一套 Kafka")
    print()


def main():
    parser = argparse.ArgumentParser(description="Kafka 消息发送工具")
    parser.add_argument("--topic",   help="目标 topic（不传则使用配置里的 default_topic）")
    parser.add_argument("--message", help="消息内容（JSON 字符串）")
    parser.add_argument("--file",    help="从文件读取消息内容")
    parser.add_argument("--key",     help="消息 key（可选，用于分区路由）")
    parser.add_argument("--header",  dest="headers", action="append",
                        metavar="KEY=VALUE", help="消息 header，可多次指定")
    parser.add_argument("--config",       help="指定配置文件路径（默认搜索本地 .local.toml）")
    parser.add_argument("--check-offset", action="store_true",
                        help="查询消费者 group 的 offset 和 LAG")
    parser.add_argument("--check-members", action="store_true",
                        help="查询当前 consumer group 里有哪些消费者实例在线")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.check_members:
        group = cfg.get("consumer_group", "")
        if not group:
            print("[错误] 需要 consumer_group（配置文件里填）")
            sys.exit(1)
        check_members(cfg, group)
        return

    if args.check_offset:
        topic = args.topic or cfg.get("default_topic", "")
        group = cfg.get("consumer_group", "")
        if not topic or not group:
            print("[错误] 需要 topic 和 consumer_group（配置文件里填或用 --topic 指定）")
            sys.exit(1)
        check_offset(cfg, topic, group)
        return

    topic = args.topic or cfg.get("default_topic", "")
    if not topic:
        print("[错误] 未指定 topic，且配置文件中没有 default_topic")
        sys.exit(1)

    message = parse_message(args)
    headers = parse_headers(args.headers)

    servers_display = cfg["bootstrap_servers"].split(",")[0] + (
        " ..." if "," in cfg["bootstrap_servers"] else ""
    )
    print(f"[kafka-tool] 连接 {servers_display}")

    try:
        producer = build_producer(cfg)
    except KafkaError as e:
        print(f"[错误] 无法连接 Kafka：{e}")
        sys.exit(1)

    key_display = f"  key: {args.key}" if args.key else ""
    header_display = f"  headers: {[k for k, _ in headers]}" if headers else ""
    print(f"[kafka-tool] 发送 → topic: {topic}{key_display}{header_display}")

    try:
        future = producer.send(
            topic,
            value=message,
            key=args.key,
            headers=headers if headers else None,
        )
        producer.flush()
        record = future.get(timeout=cfg.get("request_timeout_ms", 10000) / 1000)
        print(f"[kafka-tool] ✅ 消息已发出  分区={record.partition}  编号={record.offset}")
        print(f"[kafka-tool] 消息已存入 Kafka，等待消费者拉取...")
    except KafkaError as e:
        print(f"[kafka-tool] ❌ 发送失败：{e}")
        sys.exit(1)
    finally:
        producer.close()

    # 发送后自动检查消费进度
    group = cfg.get("consumer_group", "")
    if group:
        import time
        print(f"\n[kafka-tool] 等待 2 秒后自动检查消费进度...")
        time.sleep(2)
        check_offset(cfg, topic, group)


if __name__ == "__main__":
    main()
