# kafka-tool

向 Kafka 发送消息的命令行工具，用于测试时重放消息、触发业务流程。

---

## 环境准备

```bash
pip3 install kafka-python
```

---

## 配置

复制配置模板，填入真实信息：

```bash
cp config.example.toml kafka_tool.local.toml
```

`kafka_tool.local.toml` 已加入 `.gitignore`，不会提交到 Git。

### 配置结构

```toml
# 公共配置（认证方式、超时，所有场景共享）
[common]
security_protocol = "PLAINTEXT"
sasl_mechanism = ""
...

# 各业务场景（每个场景独立配置 broker、topic、消息体）
[profiles.overdue]
bootstrap_servers = "kafka11:9092,kafka12:9092"
topic = "finance_performance_perf_change"
consumer_group = "sign-contribute-test"
message = '''
{ "orderNo": "123" }
'''

[profiles.zhuangke]
bootstrap_servers = "..."
topic = "nrs-starfish-domain-event"
...
```

| 字段 | 说明 |
|------|------|
| `bootstrap_servers` | Broker 地址，从研发配置 `kafka.xxx.servers` 里复制 |
| `topic` | 目标 topic，从研发配置 `kafka.xxx.topic` 里复制 |
| `consumer_group` | 消费者组，从研发配置 `kafka.xxx.group.id` 里复制，用于查消费进度 |
| `message` | 消息体，用 `'''` 包裹多行 JSON |
| `security_protocol` | 认证方式，内网无认证填 `PLAINTEXT` |

---

## 切换场景

`kafka_data` 文件只需一行，写要用哪个 profile：

```
#profile: overdue
```

改成 `#profile: zhuangke` 就切换到撞客场景，消息体、topic 全部跟着换。

查看所有可用场景：

```bash
python3 kafka_tool.py --list-profiles
```

---

## 发送消息

```bash
# 读 kafka_data 里的 #profile，自动取对应消息体发送
python3 kafka_tool.py

# 临时切换场景（不改 kafka_data）
python3 kafka_tool.py --profile zhuangke

# 临时覆盖消息体（不改配置文件）
python3 kafka_tool.py --message '{"orderNo":"123456"}'

# 从文件读消息体
python3 kafka_tool.py --file /tmp/msg.json

# 带 key（同一 key 的消息进同一分区，保证顺序）
python3 kafka_tool.py --key "123456"

# 带 header（部分消费者会校验 traceId 等字段）
python3 kafka_tool.py --header traceId=abc123
```

发送成功后自动等 2 秒查消费进度，确认消息是否被消费者拉走。

---

## 查询命令

**查消费进度（LAG）**

```bash
python3 kafka_tool.py --check-offset
```

- `LAG=0`：消息已被消费者拉走
- `LAG>0`：消息还没被消费，可能消费者没启动

**查哪些服务实例在消费（排查多环境抢消息问题）**

```bash
python3 kafka_tool.py --check-members
```

输出每个在线消费者的 IP，对比大禹平台上的 Pod IP，可以确认消息被哪个环境抢走了。

> **多环境共用 Kafka 时**，不同环境如果配了相同的 `group.id`，消息只会被其中一个消费者拿到。
> 解决方法：在自己的服务配置里把 `group.id` 改成唯一的名字（如加个人名后缀），这样每个环境都能独立收到消息。

---

## 输出说明

```
[kafka-tool] ✅ 消息已发出  分区=2  编号=43135
```

- **分区**：消息存在 Kafka 的哪个分区（Kafka 把消息分散存在多个分区里）
- **编号**：消息在该分区的序号，每发一条加 1
