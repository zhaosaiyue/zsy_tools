"""
kafka_tool.py  —  Kafka 消息发送工具

用法：
  python kafka_tool.py                          # 读 kafka_data，自动取 #profile 行
  python kafka_tool.py --profile zhuangke       # 指定 profile
  python kafka_tool.py --topic xxx --message '{...}'  # 临时覆盖 topic 和消息体
  python kafka_tool.py --check-offset           # 查消费进度
  python kafka_tool.py --check-members          # 查哪些服务实例在消费
  python kafka_tool.py --list-profiles          # 列出所有可用 profile
"""

import argparse
import json
import sys
import time
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
_DATA_FILE = _SCRIPT_DIR / "kafka_data"
_CONFIG_CANDIDATES = [
    _SCRIPT_DIR / "kafka_tool.local.toml",
    Path.home() / ".zsy_tools" / "kafka_tool.toml",
]


# ── 配置加载 ──────────────────────────────────────────────

def load_config() -> dict:
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    print("[错误] 未找到配置文件，请创建以下任意一个：")
    for p in _CONFIG_CANDIDATES:
        print(f"  {p}")
    print(f"参考 {_SCRIPT_DIR / 'config.example.toml'} 填写内容")
    sys.exit(1)


def resolve_profile(raw: dict, profile_name: str | None) -> dict:
    """common + 指定 profile 合并，profile 同名字段优先。"""
    profiles = raw.get("profiles", {})
    common = raw.get("common", {})

    if not profiles:
        return raw

    if profile_name:
        if profile_name not in profiles:
            print(f"[错误] profile '{profile_name}' 不存在，可用的有：{list(profiles.keys())}")
            sys.exit(1)
    else:
        profile_name = next(iter(profiles))

    cfg = {**common, **profiles[profile_name]}
    cfg["_profile"] = profile_name
    return cfg


# ── kafka_data 解析 ───────────────────────────────────────

def read_data_file() -> tuple[str | None, str]:
    """
    读取 kafka_data，解析第一行的 #profile: xxx 指令。
    返回 (profile_name_or_None, 消息体)
    """
    if not _DATA_FILE.exists() or not _DATA_FILE.read_text(encoding="utf-8").strip():
        print(f"[提示] 请将消息体写入 {_DATA_FILE}")
        sys.exit(1)

    content = _DATA_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()

    profile = None
    msg_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#profile:"):
            profile = stripped[len("#profile:"):].strip()
        else:
            msg_lines.append(line)

    return profile, "\n".join(msg_lines).strip()


# ── 消息解析 ──────────────────────────────────────────────

def parse_message(args, cfg: dict) -> str:
    """
    消息体优先级：--message > --file > profile.message > kafka_data 消息体
    """
    if args.message and args.file:
        print("[错误] --message 和 --file 不能同时使用")
        sys.exit(1)

    if args.message:
        raw = args.message.strip()
    elif args.file:
        p = Path(args.file).expanduser()
        if not p.exists():
            print(f"[错误] 文件不存在：{p}")
            sys.exit(1)
        raw = p.read_text(encoding="utf-8").strip()
    elif cfg.get("message", "").strip():
        raw = cfg["message"].strip()
        print(f"[kafka-tool] 读取消息体来自配置文件 profile")
    else:
        _, raw = read_data_file()
        if not raw:
            print(f"[提示] 请在配置文件 profile 里填 message，或将消息体写入 {_DATA_FILE}")
            sys.exit(1)
        print(f"[kafka-tool] 读取消息体来自 kafka_data")

    try:
        json.loads(raw)
    except json.JSONDecodeError:
        print("[警告] 消息内容不是合法 JSON，将原样发送")

    return raw


# ── Kafka 工具 ────────────────────────────────────────────

def build_producer(cfg: dict) -> KafkaProducer:
    servers = [s.strip() for s in cfg["bootstrap_servers"].split(",")]
    kwargs = {
        "bootstrap_servers": servers,
        "security_protocol": cfg.get("security_protocol", "PLAINTEXT").upper(),
        "request_timeout_ms": cfg.get("request_timeout_ms", 10000),
        "value_serializer": lambda v: v.encode("utf-8") if isinstance(v, str) else v,
        "key_serializer": lambda k: k.encode("utf-8") if isinstance(k, str) else k,
    }
    mechanism = cfg.get("sasl_mechanism", "").strip()
    if mechanism:
        kwargs["sasl_mechanism"] = mechanism
        kwargs["sasl_plain_username"] = cfg.get("sasl_username", "")
        kwargs["sasl_plain_password"] = cfg.get("sasl_password", "")
    return KafkaProducer(**kwargs)


def parse_headers(header_args: list[str]) -> list[tuple[str, bytes]]:
    headers = []
    for h in (header_args or []):
        if "=" not in h:
            print(f"[警告] header 格式错误（应为 key=value）：{h}，已跳过")
            continue
        k, v = h.split("=", 1)
        headers.append((k.strip(), v.strip().encode("utf-8")))
    return headers


def get_members(cfg: dict, group: str) -> list:
    """返回 consumer group 在线成员列表"""
    servers = [s.strip() for s in cfg["bootstrap_servers"].split(",")]
    admin = KafkaAdminClient(bootstrap_servers=servers)
    try:
        described = admin.describe_consumer_groups([group])
    finally:
        admin.close()
    if not described:
        return []
    return described[0].members


def check_members(cfg: dict, group: str):
    members = get_members(cfg, group)
    if not members:
        print(f"[kafka-tool] 消费者组 {group} 当前没有在线实例")
        return
    print(f"[kafka-tool] 消费者组 {group} 共 {len(members)} 个在线实例：")
    ips = sorted({m.client_host.lstrip("/") for m in members})
    for ip in ips:
        print(f"  {ip}")


def check_offset(cfg: dict, topic: str, group: str) -> bool:
    """返回 True 表示 LAG=0（消息已被消费）"""
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
        return False

    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    consumer.assign(tps)
    end_offsets = consumer.end_offsets(tps)
    committed = {tp: consumer.committed(tp) for tp in tps}
    consumer.close()

    total_lag = sum(
        (end_offsets[tp] - committed[tp])
        for tp in tps
        if committed[tp] is not None
    )
    return total_lag == 0


# ── main ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Kafka 消息发送工具")
    parser.add_argument("--profile",       help="指定 profile 名（不传则读 kafka_data 第一行，或用第一个）")
    parser.add_argument("--topic",         help="临时覆盖 topic")
    parser.add_argument("--message",       help="消息内容（JSON 字符串）")
    parser.add_argument("--file",          help="从文件读取消息内容")
    parser.add_argument("--key",           help="消息 key（可选，用于分区路由）")
    parser.add_argument("--header",        dest="headers", action="append",
                        metavar="KEY=VALUE", help="消息 header，可多次指定")
    parser.add_argument("--check-offset",  action="store_true", help="查询消费进度")
    parser.add_argument("--check-members", action="store_true", help="查询在线消费者实例")
    parser.add_argument("--list-profiles", action="store_true", help="列出所有可用 profile")
    args = parser.parse_args()

    raw_cfg = load_config()

    # 列出所有 profile
    if args.list_profiles:
        profiles = raw_cfg.get("profiles", {})
        if not profiles:
            print("（当前配置文件无 profiles，为单配置模式）")
            return
        print("\n可用 profile：")
        for name, p in profiles.items():
            print(f"  {name:<20} topic={p.get('topic', '')}  group={p.get('consumer_group', '')}")
        print()
        return

    # 确定最终 profile（优先级：--profile > kafka_data #profile > 第一个）
    profile_from_file = None
    if not args.profile:
        profile_from_file, _ = read_data_file() if _DATA_FILE.exists() else (None, "")
    profile_name = args.profile or profile_from_file
    cfg = resolve_profile(raw_cfg, profile_name)

    print(f"[kafka-tool] 使用 profile: {cfg.get('_profile', '（默认）')}")

    if args.check_members:
        group = cfg.get("consumer_group", "")
        if not group:
            print("[错误] 需要 consumer_group（配置文件里填）")
            sys.exit(1)
        check_members(cfg, group)
        return

    topic = args.topic or cfg.get("topic", "")

    if args.check_offset:
        if not topic:
            print("[错误] 请用 --topic 指定 topic，或在配置文件里填 topic")
            sys.exit(1)
        group = cfg.get("consumer_group", "")
        if not group:
            print("[错误] 需要 consumer_group（配置文件里填）")
            sys.exit(1)
        consumed = check_offset(cfg, topic, group)
        if consumed:
            print(f"[kafka-tool] ✅ 消息已被消费")
            members = get_members(cfg, group)
            if members:
                ips = sorted({m.client_host.lstrip("/") for m in members})
                print(f"[kafka-tool] 消费者 IP：{', '.join(ips)}")
        else:
            print(f"[kafka-tool] ⚠️  消息还未被消费（有积压）")
        return

    # 发送
    if not topic:
        print("[错误] 请用 --topic 指定 topic，或在配置文件 profile 里填 topic")
        sys.exit(1)

    message = parse_message(args, cfg)
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
    extra = f"{key_display}{header_display}"
    if extra:
        print(f"[kafka-tool] 发送中{extra}")

    try:
        future = producer.send(
            topic,
            value=message,
            key=args.key,
            headers=headers if headers else None,
        )
        producer.flush()
        record = future.get(timeout=cfg.get("request_timeout_ms", 10000) / 1000)
        print(f"[kafka-tool] ✅ 发送成功")
        print(f"[kafka-tool]   消息队列（topic） : {topic}")
    except KafkaError as e:
        print(f"[kafka-tool] ❌ 发送失败：{e}")
        sys.exit(1)
    finally:
        producer.close()

    # 发送后自动检查消费进度
    group = cfg.get("consumer_group", "")
    if group:
        print(f"[kafka-tool]   消费者组（group） : {group}")
        time.sleep(2)
        consumed = check_offset(cfg, topic, group)
        if consumed:
            members = get_members(cfg, group)
            ips = sorted({m.client_host.lstrip("/") for m in members})
            print(f"[kafka-tool] ✅ 消息已被消费  消费者 IP：{', '.join(ips)}")
        else:
            print(f"[kafka-tool] ⚠️  消息还未被消费（有积压）")


if __name__ == "__main__":
    main()
