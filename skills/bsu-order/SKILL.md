---
name: bsu-order
description: |
  BSU 定软电订单更新工具。给定 order_no + scene + amount，从 DB 读取已有字段，
  强制覆盖关键业绩字段（decorationPerfFlag/firstPerformanceCategoryId 等），
  按 BSU 金额逻辑（1061-1068）填充 orderAmounts，发送前展示摘要并等待确认。
  也支持核查 order_remark_ext 字段，对比 DB 现有值与预期全量值，缺失或不符时可选择写入。
  触发词：更新订单、updateOrder、bsu-order、发订单、写订单、update order、核查remark、检查remark、check remark
tags: [测试, BSU, 订单更新, updateOrder, remark核查]
---

# BSU 订单更新 Skill

你是一个 BSU 定软电订单更新助手。收到触发词后，严格按以下步骤执行，不得跳过确认环节。

---

## 步骤一：收集参数

如果用户已提供了 order_no、scene 和 amount，直接使用，跳过此步骤。

否则，直接用文字提问（**不使用 AskUserQuestion**）：

> 请提供：
> 1. order_no（子单的 orderNo 数字）
> 2. scene：sign（正签）/ place（下单）/ finish（履约完成）/ cancel（退单）
> 3. amount：当前节点的合同额（contractAmount），退单传冲销金额

---

## 步骤二：运行脚本

脚本会自动完成：
1. 从 DB 读取已有 remarkExts / timeExts / amounts
2. 强制覆盖以下关键字段（无论 DB 里是什么值）：
   - decorationPerfFlag = true
   - firstPerformanceCategoryId = 035002 / firstPerformanceCategoryName = 软装
   - secondPerformanceCategoryId = 035002001 / secondPerformanceCategoryName = 灯具
   - softBsuFlag = true
   - compositeOrderSplitRule = performance_first_category_id
3. 按 BSU 金额逻辑计算 1061-1068（基于 DB 已有金额做差值）
4. 打印摘要，等待用户输入 y/n 确认

**先预览（不发送）：**

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/bsu-order && \
  python update_order.py \
    --order_no {order_no} \
    --scene {scene} \
    --amount {amount}
```

脚本打印摘要后会停在 `确认发送？(y/n):` 处——此时用 AskUserQuestion 展示给用户确认。

---

## 步骤三：展示摘要并弹出确认框

将脚本打印的内容格式化后，用 `AskUserQuestion` 展示，**必须等用户点击才能继续**：

问题标题：`以下订单数据即将发送，请确认`

描述内容（放在「确认发送」选项的 description 里）：
```
order_no       : {order_no}
scene          : {scene}
outOrderStatus : {status}

[orderAmounts]
  {code} = {val}  ...

[orderTimeExts]
  {timeType} = {timeValue}  (DB / 生成)  ...

[orderRemarkExts] 共 N 个（DB:x 强制覆盖:y 兜底:z）
  强制覆盖字段：decorationPerfFlag/softBsuFlag/...
  兜底字段：...
```

选项：
- `确认发送` — 执行发送
- `取消` — 放弃操作

---

## 步骤四：根据用户选择执行

**确认发送**：通过管道自动输入 `y`：

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/bsu-order && \
  echo y | python update_order.py \
    --order_no {order_no} \
    --scene {scene} \
    --amount {amount}
```

成功后回复：
```
✅ 订单更新成功！
order_no : {order_no}
scene    : {scene}  (outOrderStatus={status})
amount   : {amount}
```

**取消**：直接回复"已取消，未发送任何请求"。

---

---

## 步骤五（check-remarks 模式）：核查 order_remark_ext 字段

触发词：核查remark、检查remark、check remark、检查扩展字段、检查拓展字段，或用户说"看看 remark 对不对"之类。

只需要 order_no，无需 scene 和 amount。

**第一步：先预览（不写入）：**

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/bsu-order && \
  python update_order.py \
    --order_no {order_no} \
    --check-remarks
```

脚本会：
1. 查询 DB 中 `order_remark_ext` 现有值
2. 与预期全量字段（FORCE_OVERRIDE_REMARKS + FALLBACK_REMARKS）对比，分三类展示：
   - ✅ 一致：DB 值与预期相同
   - ⚠️ 值不同：已存在但值有差异
   - ❌ DB 缺失：预期有但 DB 里没有
3. 若有差异或缺失，脚本停在 `是否通过接口将以上 N 个字段写入？(y/n):` 处（此时脚本因 EOFError 退出，属正常现象）

**第二步：将待写字段展示给用户，用 `AskUserQuestion` 确认：**

把脚本输出的 ⚠️ 值不同 / ❌ 缺失字段列出来，放在「确认写入」选项的 description 里：
```
待写入字段（共 N 个）：
  {key} = {value}
  ...
```
选项：`确认写入` / `取消`

**第三步：确认写入后，通过管道输入 `y` 执行：**

```bash
cd /Users/zsy/PycharmProjects/zsy_tools/skills/bsu-order && \
  echo y | python update_order.py \
    --order_no {order_no} \
    --check-remarks
```

**若脚本输出"脚本管控字段全部一致，无需写入"，则直接告知用户，无需弹确认框。**

---

## 重要：updateOrder 接口字段覆盖规则

**`orderRemarkExts` 是全量覆盖**：传什么字段就写什么字段，不传的字段会被清掉。

因此，每次调用 `updateOrder` 接口时，**必须先从 DB 读取所有现有 remarks**，在完整字段列表基础上做增减，绝不能只传想改的字段。`orderAmounts`、`orderTimeExts` 同理。

---

## 注意事项

- **脚本位置**：`skills/bsu-order/update_order.py`
- **配置文件**（优先级从高到低）：
  1. `skills/bsu-order/bsu_order.local.toml`（推荐）
  2. `~/.zsy_tools/bsu_order.toml`
  - 首次使用：复制 `config.example.toml`，填入真实 host/user/password
- **依赖安装**：`pip install PyMySQL tomli`（Python 3.11+ 不需要 tomli）
- **Cookie**：默认内置测试 Cookie，如需替换传 `--cookie`
- **场景对应 outOrderStatus**：sign=1200，place=3100，finish=3250，cancel=3300
