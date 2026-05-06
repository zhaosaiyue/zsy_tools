---
name: reset-order
description: |
  测试数据清理工具。给定 order_no，查询并删除相关业务数据，用于重放消息模拟业务流程。
  触发词：清理业绩、重置业绩、reset order、清业绩、删除业绩
tags: [测试, 数据清理, 重置, reset]
---

# 清理业绩工具 reset-order

你是一个测试数据清理助手。收到触发词后，严格按以下步骤执行，不得跳过任何确认环节。

---

## 步骤一：询问 order_no

如果用户在触发词里已经提供了 order_no（如"删除业绩 6574192984971878400"），直接使用，跳过此步骤。

否则，直接用文字提问，**不使用 AskUserQuestion**：

> 请提供要清理的 order_no（支持多个，用逗号分隔）

---

## 步骤二：执行查询

运行以下命令（仅查询，不删除任何数据）：

```bash
cd {skill目录} && python reset_order.py --order_no {order_no} --query-only
```

从输出中提取 `__QUERY_RESULT_JSON__` 后面的 JSON 内容。

---

## 步骤三：展示查询结果并弹出确认框

解析 JSON，用 `AskUserQuestion` 展示如下内容，**必须等用户点击才能继续**：

问题标题：`以下数据即将被删除，请确认`

描述内容（有几个 order_no 就循环拼几段，全部放在「确认删除」选项的 description 里）：

```
=== order_no: {order_no_1} ===
[cashcow_betula]
  performance_detail_ext  : {N} 条
  performance_detail      : {N} 条
[sign_contribute]
  rec_contribute_node     : {N} 条
  rec_contribute          : {N} 条
  rec_receipt             : {N} 条（或：跳过（无数据））
  assign_node             : {N} 条
  assign_step_version     : {N} 条
  role_detail             : {N} 条
  role_version            : {N} 条

=== order_no: {order_no_2} ===
...
```

选项：
- `确认删除` — 执行删除
- `取消` — 放弃操作

---

## 步骤四：根据用户选择执行

**用户选择「确认删除」：**

```bash
cd {skill目录} && python reset_order.py --order_no {order_no} --do-delete
```

不需要展示脚本执行的详细过程，直接输出如下完成提示（必须包含所有 order_no）：

```
✅ 业绩数据清理完成！

订单号：
- {order_no_1}
- {order_no_2}
- ...

业绩相关数据已全部清除，可以重新发送消息重新触发业绩计算了 🎉
```

**用户选择「取消」：**

直接回复：`已取消，未删除任何数据`，流程结束。

---

## 注意事项

- 配置文件（优先级从高到低）：
  1. `skills/reset-order/reset_order.local.toml`（推荐，IDE 可见，已 gitignore）
  2. `~/.zsy_tools/reset_order.toml`（全局配置）
  - 首次使用：复制 `config.example.toml` 为上述任意路径，填入真实的 host/user/password
- 依赖安装：`pip install PyMySQL httpx tomli`（Python 3.11+ 不需要 tomli）
- skill 目录替换为本文件所在的绝对路径
