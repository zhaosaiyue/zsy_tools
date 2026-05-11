# bsu-order

调用 `updateOrder` 接口更新 BSU 定软电订单。

## 触发词

`更新订单`、`updateOrder`、`bsu-order`、`发订单`、`写订单`、`update order`

## 用法

在 Claude Code 中输入触发词，按提示提供参数即可。也可以在命令行直接调用底层脚本：

```bash
cd skills/bsu-order

# 正签
python update_order.py --order_no 6585951162319339521 --scene sign --sign 100

# 下单
python update_order.py --order_no 6585951162319339521 --scene place --sign 100 --place 111

# 履约完成
python update_order.py --order_no 6585951162319339521 --scene finish --sign 100 --place 200 --finish 150

# 下单冲销
python update_order.py --order_no 6585951162319339521 --scene place --sign 100 --place -50 --place-type cancel
```

## 依赖

```bash
pip install PyMySQL tomli   # Python 3.11+ 不需要 tomli
```

## 配置

复制 `skills/bsu-order/config.example.toml` 为以下任一路径，填入真实连接信息：

- `skills/bsu-order/bsu_order.local.toml`（推荐）
- `~/.zsy_tools/bsu_order.toml`