---
name: sharing-reset
description: |
  分账测试数据清理工具。给定 contract_no，查询并删除应分、实分、履约计划、重新分账流程相关数据，用于重放 reSharinngRecord 或分账消息。
  触发词：清理分账、重置分账、reset sharing、清应分、清实分、清履约计划、删除分账
tags: [测试, 数据清理, 分账, 应分, 实分, 履约计划, reset]
---

# 清理分账工具 sharing-reset

你是一个分账测试数据清理助手。收到触发词后，严格按以下步骤执行，不得跳过配置读取、查询展示和删除确认环节。

---

## 运行原则

- **先读配置，再连库**：每次执行查询或删除前，必须先读取配置文件，确认本次使用的主库和分账库连接信息。
- **优先使用本 skill 自带脚本**：无论在 Codex、Claude 还是其他 Agent 中执行，都优先运行 `sharing_reset.py`，不要先假设存在 MCP 工具。
- **MCP 只是备选**：只有本地脚本不可用、依赖不可用且无法安装时，才考虑使用 MCP/数据库工具直连；使用 MCP 时也必须按配置文件里的库信息核对目标库。
- **只读先行**：默认只运行 `--query-only`，展示影响范围后，用户明确确认才允许运行 `--do-delete`。
- **配置不明就停止**：如果配置文件不存在、字段缺失、或主库/分账库无法确认，停止操作并提示缺少配置，不要凭记忆拼连接。

---

## 固定路径和配置

skill 目录固定为：

```bash
/Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset
```

配置文件优先级从高到低：

1. `/Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset/sharing_reset.local.toml`
2. `~/.zsy_tools/sharing_reset.toml`

配置字段必须包含：

```toml
[db_main]
host = "..."
port = 10239
user = "..."
password = "..."
database = "CP_FINANCE"

[db_sharing]
host = "..."
port = 10012
user = "..."
password = "..."
database = "CP_FINANCE"
```

读取配置命令：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && sed -n '1,120p' sharing_reset.local.toml
```

如果 `sharing_reset.local.toml` 不存在，再读全局配置：

```bash
sed -n '1,120p' ~/.zsy_tools/sharing_reset.toml
```

---

## 执行命令模板

查询单个合同（只查询，不删除）：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no} --query-only
```

查询多个合同（英文逗号分隔）：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no_1},{contract_no_2},{contract_no_3} --query-only
```

删除单个合同（必须先完成查询展示和用户确认）：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no} --do-delete
```

删除多个合同（必须先完成查询展示和用户确认）：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no_1},{contract_no_2},{contract_no_3} --do-delete
```

查看脚本参数：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --help
```

依赖安装：

```bash
pip install PyMySQL tomli
```

---

## 步骤一：读取并确认配置

执行任何查询前，先按优先级读取配置文件，并在内部确认：

- `db_main` 指向 10239 主库，用于查询 `order_info`、`receivable`、`paidup`。
- `db_sharing` 指向 10012 分账库，用于查询和清理应分、实分、履约计划、流程辅助表。
- 两个库的 `database` 都是期望的业务库，例如 `CP_FINANCE`。

如果配置文件不存在或缺字段，停止并提示用户补齐配置。

---

## 步骤二：询问 contract_no

如果用户在触发词里已经提供了 contract_no（如"清理分账 BJ123456"），直接使用，跳过此步骤。

否则，直接用文字提问，**不使用 AskUserQuestion**：

> 请提供要清理的 contract_no（支持多个，用逗号分隔）

---

## 步骤三：执行查询

运行以下命令（仅查询，不删除任何数据）：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no} --query-only
```

从输出中提取 `__QUERY_RESULT_JSON__` 后面的 JSON 内容。

---

## 步骤四：展示查询结果并等待确认

解析 JSON，展示如下内容，**必须等用户明确确认才能继续**。

在 Codex Plan 模式且 `AskUserQuestion` 可用时，可以用确认框；在 Claude、Codex Default 模式或没有确认框能力时，直接文字询问用户回复 `确认删除 {contract_no}`。不能因为用户最初说“删除”就跳过查询后的二次确认。

问题标题：`以下分账数据即将被删除，请确认`

描述内容（有几个 contract_no 就循环拼几段，全部放在「确认删除」选项的 description 里）：

```text
=== contract_no: {contract_no_1} ===
order_info_id: {order_info_id}
business_id: {business_id}
receivable_ids: {N} 条
paidup_ids: {N} 条

[应分]
  receivable_item_charge             : {N} 条
  receivable_item_charge_detail      : {N} 条
  receivable_item_charge_plat        : {N} 条
  receivable_sub_account_detail      : {N} 条
  receivable_charge_version          : {N} 条

[实分]
  paidup_item_charge                 : {N} 条
  paidup_item_charge_detail          : {N} 条
  paidup_item_charge_plat            : {N} 条
  paidup_sub_account_detail          : {N} 条
  paidup_charge_version              : {N} 条

[履约计划/结算]
  sharing_fulfill_plan               : {N} 条
  sharing_fulfill_plan_detail        : {N} 条
  sharing_settle_detail              : {N} 条
  sharing_settle_detail_ref          : {N} 条

[流程辅助]
  re_sharing_record                  : {N} 条
  op_sharing_log                     : {N} 条
  biz_execute_record                 : {N} 条
  biz_execute_record_param           : {N} 条
  sharing_exception_log              : {N} 条
  sync_lft_item_charge               : {N} 条
  charge_sync_lft_related            : {N} 条
```

选项：
- `确认删除` — 执行删除
- `取消` — 放弃操作

---

## 步骤五：根据用户选择执行

**用户选择「确认删除」：**

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset && python3 sharing_reset.py --contract_no {contract_no} --do-delete
```

不需要展示脚本执行的详细过程，直接输出如下完成提示（必须包含所有 contract_no）：

```text
分账数据清理完成！

合同编号：
- {contract_no_1}
- {contract_no_2}
- ...

应分、实分、履约计划及重分流程辅助数据已清除，可以重新触发分账流程。
```

**用户选择「取消」：**

直接回复：`已取消，未删除任何数据`，流程结束。

---

## 注意事项

- 配置文件（优先级从高到低）：
  1. `skills/sharing-reset/sharing_reset.local.toml`（推荐，IDE 可见，已补全测试环境配置）
  2. `~/.zsy_tools/sharing_reset.toml`（全局配置）
- 10239 是主库，用于查询 `order_info`、`receivable`、`paidup`。
- 10012 是分账库，用于查询和清理应分、实分、履约计划、流程辅助表。
- 依赖安装：`pip install PyMySQL tomli`（Python 3.11+ 不需要 tomli）
- skill 目录固定为 `/Users/zsy/PycharmProjects/zsy_tools/skills/sharing-reset`
