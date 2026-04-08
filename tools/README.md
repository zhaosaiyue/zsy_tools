# tools

独立 Python 工具目录。每个工具无第三方依赖，开箱即用。

## 目录结构

```
tools/
├── timestamp_converter.py   # 时间戳 ↔ 日期字符串 转换
└── json_tool/               # JSON 处理工具套件
    ├── json_tool.py
    ├── json_data            # 输入文件（粘贴原始数据）
    └── json_result          # 输出文件（处理结果）
```

## 工具列表

### timestamp_converter

时间戳与日期字符串的双向转换工具。

**支持场景：**
- 秒级 / 毫秒级时间戳 → 格式化日期字符串
- 日期字符串 → 毫秒时间戳
- 自动识别 7 种常用日期格式
- 支持时区参数

**快速使用：**
```python
# 修改 timestamp_converter.py 底部的 INPUT 变量，直接运行
INPUT = 1700000000000        # 时间戳 → 日期
INPUT = "2026-04-08 10:00:00"  # 日期 → 时间戳
```

**核心函数：**

| 函数 | 说明 |
|------|------|
| `to_date_string(ts, fmt, tz)` | 时间戳 → 日期字符串 |
| `to_timestamp(date_str, fmt, tz)` | 日期字符串 → 毫秒时间戳 |
| `now_timestamp()` | 当前毫秒时间戳 |
| `now_date_string(fmt)` | 当前时间格式化字符串 |

---

### json_tool

JSON 数据处理与修复工具。详见 [json_tool/README.md](json_tool/README.md)。

**快速使用：**
```bash
# 1. 将原始数据粘贴到 json_tool/json_data
# 2. 运行
python tools/json_tool/json_tool.py
# 3. 查看 json_tool/json_result
```
