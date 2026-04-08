# zsy_tools

一个面向日常开发的工具集合，分为两大类：**技能（Skills）**（Claude Code 智能助手技能）和 **工具（Tools）**（独立 Python 工具）。

## 架构概览

```
zsy_tools/
├── README.md                        # 本文件：项目总览
├── skills/                          # Claude Code Skills（AI 辅助技能）
│   ├── README.md                    # Skills 目录说明
│   ├── ai-testcase/                 # AI 测试用例生成器
│   │   ├── README.md
│   │   └── SKILL.md                 # Skill 定义文件
│   └── naming-convention/           # 命名规范审查器
│       ├── README.md
│       └── SKILL.md
└── tools/                           # 独立 Python 工具
    ├── README.md                    # Tools 目录说明
    ├── timestamp_converter.py       # 时间戳 ↔ 日期 转换工具
    └── json_tool/                   # JSON 处理工具
        ├── README.md
        ├── json_tool.py
        ├── json_data                # 输入文件（粘贴原始数据）
        └── json_result              # 输出文件（处理结果）
```

## 功能速览

| 组件 | 类型 | 用途 |
|------|------|------|
| [ai-testcase](skills/ai-testcase/README.md) | 技能 | 解析需求/技术文档，生成 XMind 兼容的结构化测试用例 |
| [naming-convention](skills/naming-convention/README.md) | 技能 | 审查命名规范，提供新组件命名建议 |
| [timestamp_converter](tools/README.md#timestamp_converter) | 工具 | 时间戳与日期字符串双向转换，支持多格式与时区 |
| [json_tool](tools/json_tool/README.md) | 工具 | JSON 格式化、修复、转义/反转义、Unicode/URL 解码 |

## 技术栈

- Python 3.x，仅使用标准库（`datetime`、`json`、`re`、`urllib.parse`）
- Claude Code 技能系统

## 作者

zsy