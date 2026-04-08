# skills

Claude Code **技能（Skills）** 目录。技能是挂载在 Claude Code 中的 AI 辅助能力，通过关键词触发，由 `SKILL.md` 定义工作流和行为规则。

## 技能列表

| 技能 | 触发方式 | 功能 |
|------|----------|------|
| [ai-testcase](ai-testcase/README.md) | 关键词：用例、测试用例、测试case... | 解析文档生成 XMind 结构化测试用例 |
| [naming-convention](naming-convention/README.md) | 关键词：命名、重命名、规范审查... | 审查命名规范，给出改进建议 |

## 如何新增 Skill

1. 在 `skills/` 下新建目录，使用短横线小写命名（如 `my-skill`）
2. 创建 `SKILL.md`，定义触发词、工作流、输出格式
3. 创建 `README.md`，说明功能和使用方式