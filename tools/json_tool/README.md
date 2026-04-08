# json_tool

JSON 处理与修复工具，专为日志分析和数据调试设计。支持自动识别编码类型并链式处理。

## 使用方法

```bash
# 1. 将原始数据（可以是损坏/转义/URL编码的 JSON）粘贴到：
#    tools/json_tool/json_data

# 2. 运行工具
python json_tool.py

# 3. 查看处理结果
#    tools/json_tool/json_result
```

控制台会打印处理链路，例如：
```
[自动识别] URL解码 → Unicode解码 → 格式化
[完成] 结果已写入 json_result
```

## 功能说明

| 函数 | 说明 |
|------|------|
| `fmt(text)` | 格式化美化（自动忽略注释） |
| `compress(text)` | 压缩为单行 |
| `escape(text)` | 转义（`"` → `\"`） |
| `unescape(text)` | 反转义，不修改数据内容 |
| `decode_unicode(text)` | `\uXXXX` → 中文等 Unicode 字符 |
| `decode_url(text)` | URL 解码（`%XX` → 字符） |
| `auto(text)` | **自动**：检测编码并链式处理 |

## 自动模式处理链

```
原始输入
  ↓ URL 解码（检测到 %XX）
  ↓ 直接解析（已是合法 JSON）
  ↓ Unicode 解码（检测到 \uXXXX）
  ↓ 反转义（检测到 \"、\n、\t）
  ↓ 自动修复（缺少括号则补全）
  ↓ 输出结果
```

## 修复策略（非破坏性）

- 补全缺失的 `{}`、`[]`
- 移除外层多余引号
- 所有策略**只修复结构，不修改数据内容**

## 注释支持

支持解析含注释的 JSON（在格式化时自动剥离）：
- 单行注释：`// comment`
- 多行注释：`/* comment */`
- 字符串内的注释内容**不会**被剥离

## 文件

| 文件 | 说明 |
|------|------|
| `json_tool.py` | 工具主程序 |
| `json_data` | 输入文件，粘贴待处理的原始数据 |
| `json_result` | 输出文件，处理后的结果 |
