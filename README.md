# zsy_tools

个人效率工具集，包含 Claude Code Skills 和日常开发小工具。

## Skills

在 Claude Code 对话中通过关键词触发，自动执行对应工作流。

| Skill | 触发词 | 说明 |
|-------|--------|------|
| [ai-testcase](skills/ai-testcase/) | 用例 / 出用例 / 测试用例 / testcase | 解析需求/技术文档，生成结构化测试用例，输出 `.md` + `.xmind` |
| [naming-convention](skills/naming-convention/) | 命名 / 重命名 / 规范审查 | 审查命名规范，或为新组件生成候选命名 |

## Tools

| 工具 | 说明 | 使用方式 |
|------|------|----------|
| [json_tool](tools/json_tool/) | JSON 格式化/修复，支持 URL编码、Unicode、转义自动处理 | `python json_tool.py` |
| [timestamp_converter.py](tools/timestamp_converter.py) | 时间戳与日期互转 | `python timestamp_converter.py` |

## 初始化

首次使用 `ai-testcase` 需安装 Node.js 依赖：

```bash
cd skills/ai-testcase && npm install
```