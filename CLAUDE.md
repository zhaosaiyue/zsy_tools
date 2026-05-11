# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

个人效率工具集，包含两类内容：

- **Skills** (`skills/`)：挂载在 Claude Code 中的 AI 辅助能力，由 `SKILL.md` 定义工作流，通过关键词触发
- **Tools** (`tools/`)：独立运行的日常开发小脚本

## Setup

首次使用 `ai-testcase` skill 需安装 Node.js 依赖：

```bash
cd skills/ai-testcase && npm install
```

需要数据库连接的 skill（`reset-order`、`bsu-amount`）需安装 Python 依赖并配置本地 TOML：

```bash
pip install PyMySQL tomli   # Python < 3.11 需要 tomli；3.11+ 不需要
```

复制对应 skill 目录下的 `config.example.toml` 为 `<skill-name>.local.toml`（已 gitignore），填入真实的数据库 host/user/password。

## Running Tools

```bash
python tools/json_tool/json_tool.py       # JSON 格式化/修复
python tools/timestamp_converter.py       # 时间戳与日期互转
python tools/pinus_shard.py
```

## Architecture

### Skill 结构

每个 skill 是一个目录，核心文件是 `SKILL.md`：

```
skills/<skill-name>/
├── SKILL.md          # 工作流定义，Claude 执行时读取此文件
├── README.md         # 使用说明
└── <script>.py/.js   # 可选：skill 调用的后端脚本
```

`SKILL.md` 使用 YAML frontmatter 声明 `name`、`description`（含触发词）、`tags`，正文定义 Claude 的完整执行流程。

### 现有 Skills

| Skill | 触发词 | 后端脚本 |
|-------|--------|---------|
| `ai-testcase` | 用例/测试用例/testcase | `md2xmind.js`（Markdown → .xmind） |
| `naming-convention` | 命名/规范审查 | 无 |
| `project-explorer` | 读项目/项目分析/接手项目 | 无 |
| `reset-order` | 清业绩/重置业绩/reset order | `reset_order.py`（操作 MySQL） |
| `bsu-amount` | BSU金额/费用项验证 | `bsu_amount.py`（操作 MySQL） |
| `bsu-order` | 更新订单/updateOrder/发订单/写订单 | `bsu-order/update_order.py`（调接口） |

### 新增 Skill 步骤

1. 在 `skills/` 下新建 kebab-case 目录（如 `my-skill`）
2. 创建 `SKILL.md`，YAML frontmatter 中填 `name`、`description`（含触发词）、`tags`
3. 创建 `README.md`

## Naming Conventions

| 对象 | 规范 | 示例 |
|------|------|------|
| 目录、代码文件（.js/.py/.json/.sql） | `kebab-case` | `reset-order/`, `md2xmind.js` |
| 说明/模板文档（.md/.txt） | `UPPER_SNAKE_CASE` | `SKILL.md`, `README.md` |
| 类/接口 | `PascalCase` | `BillDetailService` |
| 方法/变量 | `camelCase` | `getBillDetail()` |
| 常量/环境变量 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |

## Config Files (gitignored)

- `skills/reset-order/reset_order.local.toml` — 数据库连接（reset-order）
- `skills/bsu-amount/bsu_amount.local.toml` — 数据库连接（bsu-amount）
- 全局备选路径：`~/.zsy_tools/<skill-name>.toml`