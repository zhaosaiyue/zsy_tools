---
name: bsu-amount
description: |
  BSU 定软电订单金额变化测试工具。验证正签、下单、履约完成、退单各节点的费用项（1061-1068）计算是否正确。
  触发词：BSU金额、bsu amount、费用项验证、检查bsu、验bsu金额、bsu费用项
tags: [测试, BSU, 金额验证, 费用项]
---

# BSU 定软电费用项测试 Skill

## 背景

BSU 定软电订单（S单_sku 维度）通过合同额消息驱动，分正签、下单、履约完成、退单四个节点，每个节点写入不同的费用项（orderAmounts）。

同一子单会被多次触发，金额是**增量叠加**而非覆盖，最终合同总额 = 正签 + 下单增量 + 履约完成增量。

---

## 费用项定义（1061-1068）

| code | 字段名 | 含义 | 写入节点 |
|---|---|---|---|
| 1061 | BSU_SOFT_SIGN_AMOUNT | 正签金额，正签节点的合同额 | 正签 |
| 1062 | BSU_SOFT_PLACE_ORDER_AMOUNT | 下单金额（非下单角色），下单相对正签的增减量 | 下单 |
| 1063 | BSU_SOFT_AGREEMENT_FINISH_AMOUNT | 履约完成金额（非下单角色），履约完成相对正签+下单的增减量 | 履约完成 |
| 1064 | BSU_SOFT_AGREEMENT_FINISH_DEDUCT_SIGN_AMOUNT | 履约完成扣正签金额，调减时从正签扣的部分，调增时为 0 | 履约完成 |
| 1065 | BSU_SOFT_AGREEMENT_FINISH_DEDUCT_PLACE_ORDER_AMOUNT | 履约完成扣下单金额，调减时从下单扣的部分，调增时为 0 | 履约完成 |
| 1066 | BSU_SOFT_CONTRACT_AMOUNT | 合同总额，当前累计合同总额，全程跟随更新 | 正签/下单/履约完成/退单 |
| 1067 | BSU_SOFT_PLACE_ORDER_AMOUNT_FOR_PLACE_ORDER_ROLE | 下单金额（下单角色），下单时刻的合同总额快照，写入后不再修改 | 下单 |
| 1068 | BSU_SOFT_AGREEMENT_FINISH_AMOUNT_FOR_PLACE_ORDER_ROLE | 履约完成金额（下单角色），履约完成累计合同额 - 1067 | 履约完成 |

---

## 各节点应有的 code

| 节点 | 必须存在的 code |
|---|---|
| 正签 | 1061、1066 |
| 下单 | 1061、1062、1066、1067 |
| 履约完成 | 1061、1062、1063、1064、1065、1066、1067、1068 |
| 退单 | 1066 |

---

## 计算公式

### changeType = 计入 / 冲销后计入

消息中 `contractAmount` 含义：**截止当前节点的累计合同总额**

```
正签节点：
  1061 = contractAmount
  1066 = contractAmount

下单节点：
  1062 = contractAmount - 1061
  1066 = contractAmount
  1067 = contractAmount（等于1066，即正签+下单的累计）

履约完成节点：
  1063 = contractAmount - 1062 - 1061
  1066 = contractAmount
  1067 不变（下单时的快照）
  1068 = 1066 - 1067
```

### changeType = 冲销

消息中 `contractAmount` 含义：**本次冲销的金额本身（负数）**，不是累计值，所以不做减法

```
下单冲销：
  1062 = contractAmount（直接用，不减1061）
  1066 = 1061 + contractAmount
  1067 = 1061 + contractAmount（等于1066）

履约完成冲销：
  1063 = contractAmount（直接用，不减前两项）
  1066 = 1061 + 1062 + contractAmount
  1068 = 1066 - 1067
```

---

## 验证规则（快速断言）

```
规则1：1066 = 1061 + 1062 + 1063
规则2：1067 = 1061 + 1062（下单时的1066快照，履约完成节点不变）
规则3：1068 = 1066 - 1067
规则4：调增时 1064 = 0，1065 = 0
       调减时 1064 + 1065 = 1063（1063为负，拆分到1064/1065上）
```

---

## 举例说明

> 所有例子基准：正签 contractAmount = 10

---

### 场景1：正签 → 下单金额增加

下单 contractAmount = 12（计入）

```
1061 = 10
1062 = 12 - 10 = 2
1066 = 12
1067 = 12
```

---

### 场景2：正签 → 下单金额减少

下单 contractAmount = 8（计入）

```
1061 = 10
1062 = 8 - 10 = -2
1066 = 8
1067 = 8
```

---

### 场景3：正签 → 下单金额增加 → 履约完成金额不变

下单 contractAmount = 12，履约完成 contractAmount = 12（计入）

```
1061 = 10
1062 = 2
1063 = 12 - 2 - 10 = 0
1064 = 0（调增/不变）
1065 = 0（调增/不变）
1066 = 12
1067 = 12（下单快照）
1068 = 12 - 12 = 0
```

---

### 场景4：正签 → 下单金额增加 → 履约完成金额增加

下单 contractAmount = 12，履约完成 contractAmount = 15（计入）

```
1061 = 10
1062 = 2
1063 = 15 - 2 - 10 = 3
1064 = 0（调增）
1065 = 0（调增）
1066 = 15
1067 = 12（下单快照）
1068 = 15 - 12 = 3
```

---

### 场景5：正签 → 下单金额增加 → 履约完成金额减少（下单够扣）

下单 contractAmount = 12，履约完成 contractAmount = 10（计入）

```
1061 = 10
1062 = 2
1063 = 10 - 2 - 10 = -2
sum = placeOrderAmount + 1063 = 2 + (-2) = 0  >= 0，下单够扣
  1064 = 0（不扣正签）
  1065 = -2（从下单扣）
1066 = 10
1067 = 12（下单快照）
1068 = 10 - 12 = -2
```

---

### 场景6：正签 → 下单金额增加 → 履约完成金额减少（下单不够扣，需扣正签）

下单 contractAmount = 12，履约完成 contractAmount = 6（计入）

```
1061 = 10
1062 = 2
1063 = 6 - 2 - 10 = -6
sum = placeOrderAmount + 1063 = 2 + (-6) = -4  < 0，下单不够扣
placeOrderAmount = 2 >= 0，走扣两个节点分支：
  1064 = sum = -4（扣正签）
  1065 = -2（扣下单，取 placeOrderAmount 的反）
1066 = 6
1067 = 12（下单快照）
1068 = 6 - 12 = -6
```

---

### 场景7：正签 → 下单金额减少 → 履约完成金额增加

下单 contractAmount = 8，履约完成 contractAmount = 12（计入）

```
1061 = 10
1062 = -2
1063 = 12 - (-2) - 10 = 4
1064 = 0（调增）
1065 = 0（调增）
1066 = 12
1067 = 8（下单快照）
1068 = 12 - 8 = 4
```

---

### 场景8：正签 → 下单金额减少 → 履约完成金额减少

下单 contractAmount = 8，履约完成 contractAmount = 5（计入）

```
1061 = 10
1062 = -2
1063 = 5 - (-2) - 10 = -3
sum = placeOrderAmount + 1063 = -2 + (-3) = -5  < 0，下单不够扣
placeOrderAmount = -2 < 0，走特殊分支（下单本身就是负的）：
  1064 = 1063 = -3（扣正签，等于履约完成金额）
  1065 = 0（下单已经是负的，不再扣）
1066 = 5
1067 = 8（下单快照）
1068 = 5 - 8 = -3
```

---

### 场景9：正签 → 退单

正签 contractAmount = 10，退单 contractAmount = 0

退单只更新 1066，不新增任何费用项。

存在的费用项：**1061、1066**

```
1061 = 10（正签写入，不变）
1066 = 0（退单更新）
```

---

### 场景10：正签 → 下单 → 退单

正签 contractAmount = 10，下单 contractAmount = 12，退单 contractAmount = 0

退单只更新 1066，不新增任何费用项。

存在的费用项：**1061、1062、1066、1067**

```
1061 = 10（正签写入，不变）
1062 = 2（下单写入，不变）
1066 = 0（退单更新）
1067 = 12（下单写入，不变）
```

---

### 场景11：正签 → 下单 → 履约完成 → 退单

正签 contractAmount = 10，下单 contractAmount = 12，履约完成 contractAmount = 15，退单 contractAmount = 0

退单只更新 1066，不新增任何费用项。

存在的费用项：**1061、1062、1063、1064、1065、1066、1067、1068**

```
1061 = 10（正签写入，不变）
1062 = 2（下单写入，不变）
1063 = 3（履约完成写入，不变）
1064 = 0（履约完成写入，不变）
1065 = 0（履约完成写入，不变）
1066 = 0（退单更新）
1067 = 12（下单写入，不变）
1068 = 3（履约完成写入，不变）
```

---

## 两套角色视角说明

```
非下单角色（如正签经纪人）：按节点增量拿业绩
  正签拿 1061
  下单拿 1062（增量，可正可负）
  履约完成拿 1063（增量，可正可负）

下单角色：按累计快照拿业绩
  下单拿 1067（= 正签 + 下单的累计，是下单时刻的总额快照）
  履约完成拿 1068（= 当前合同总额 - 1067）
```

---

## Skill 操作流程

你是一个 BSU 定软电金额测试助手。收到触发词后，严格按以下步骤执行。

---

### 步骤一：收集参数

如果用户已在触发词中提供了 order_no 和各节点金额（如"order_no=xxx，正签10，下单8，履约完成2"），直接使用，跳过此步骤。

否则，直接用文字提问，**不使用 AskUserQuestion**：

> 请提供：
> 1. order_no（子单）
> 2. 正签 contractAmount
> 3. 下单 contractAmount（可选）
> 4. 履约完成 contractAmount（可选）
> 5. 如有冲销节点，请注明哪个节点是冲销（changeType=cancel）

---

### 步骤二：执行查询

运行以下命令（仅查询，不写库）：

```bash
cd {skill目录} && python bsu_amount.py --order_no {order_no} --sign {sign} [--place {place}] [--finish {finish}] [--place-type cancel] [--finish-type cancel] --query-only
```

从输出中提取 `__QUERY_RESULT_JSON__` 后面的 JSON 内容。

---

### 步骤三：展示对比结果并弹出确认框

解析 JSON，用 `AskUserQuestion` 展示如下内容，**必须等用户点击才能继续**：

问题标题：`以下费用项即将写入，请确认`

描述内容放在「确认写入」选项的 description 里：

```
order_no: {order_no}
表: ke_pinus.{table}

code    字段名                                              现有值        期望值        操作
1061    BSU_SOFT_SIGN_AMOUNT                               {cur}         {exp}         {INSERT/UPDATE/一致}
1062    BSU_SOFT_PLACE_ORDER_AMOUNT                        {cur}         {exp}         {INSERT/UPDATE/一致}
...（只列出本场景涉及的 code）
```

选项：
- `确认写入` — 执行写入
- `取消` — 放弃操作

---

### 步骤四：根据用户选择执行

**用户选择「确认写入」：**

```bash
cd {skill目录} && python bsu_amount.py --order_no {order_no} --sign {sign} [--place {place}] [--finish {finish}] [--place-type cancel] [--finish-type cancel] --do-write
```

输出完成提示：

```
✅ BSU 金额写入完成！

order_no：{order_no}
场景：正签={sign}，下单={place}，履约完成={finish}

费用项已按期望值写入，可重新触发消息验证计算结果 🎉
```

**用户选择「取消」：**

直接回复：`已取消，未写入任何数据`，流程结束。

---

## 注意事项

- 配置文件（优先级从高到低）：
  1. `skills/bsu-amount/bsu_amount.local.toml`（推荐，已 gitignore）
  2. `~/.zsy_tools/bsu_amount.toml`（全局配置）
  - 首次使用：复制 `config.example.toml` 为上述任意路径，填入真实的 host/user/password
- 依赖安装：`pip install PyMySQL tomli`（Python 3.11+ 不需要 tomli）
- skill 目录替换为本文件所在的绝对路径
- `--place-type cancel` / `--finish-type cancel` 用于冲销场景，默认不传即为计入