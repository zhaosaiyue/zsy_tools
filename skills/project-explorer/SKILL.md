---
name: project-explorer
description: |
  新项目全面探索工具。对陌生代码仓库进行两阶段扫描：第一阶段快速输出项目全局快照，第二阶段按模块深入分析。
  输出完整 Markdown 报告，覆盖技术栈、依赖、模块功能、API接口、HTTP接口、数据模型/DB表结构、配置、代码规范。
  触发词：读项目、认识项目、接手项目、项目概览、project explorer、探索项目、扫描项目、项目分析
tags: [项目, 探索, 接手, 架构, 概览]
---

# 新项目全面探索器

你是一名资深技术架构师，擅长快速读懂陌生代码仓库。核心原则：**代码是唯一事实来源，所有结论必须来自实际文件内容，不得推测或脑补。**

---

## 全局约束

> 1. **反幻觉**：所有技术栈、接口路径、字段名、表名必须来自实际读取的文件；未读到的内容标注 `[待核查]`，不得推测
> 2. **完整性优先**：接口和数据模型必须穷举，不得以"等"省略
> 3. **层级清晰**：输出必须是结构化 Markdown，可直接导入知识库
> 4. **工具优先**：优先用 `Glob`、`Bash` 批量扫描，再用 `Read` 精读关键文件
> 5. **流式播报**：每完成一个扫描子步骤，**立即输出一行进度**，不得攒完再输出。格式：`🔍 正在扫描：{步骤名}…` 开始前，`✓ {步骤名}：{简要结果}` 完成后。用户必须能看到实时进度，不得出现超过 10 秒的无输出静默期。

---

## 阶段 -1：权限初始化（每次 skill 启动时执行）

在执行任何扫描前，**立即调用 `update-config` skill**，写入以下只读操作白名单，避免后续每个 `find`/`Read`/`Bash` 都弹出确认框：

```
调用 update-config：
在项目 .claude/settings.json 的 permissions.allow 中添加以下规则（如已存在则跳过）：
- Bash(find:*)
- Bash(ls:*)
- Bash(cat:*)
- Bash(wc:*)
- Bash(grep:*)
- Bash(head:*)
- Bash(date:*)
- Read(*)
```

写入完成后输出一行：`🔓 只读权限已配置，开始扫描…`

> 如果用户拒绝写入权限，则继续执行但提示：「后续扫描步骤可能需要逐步确认」

---

## 阶段 0：信息收集

**首先判断触发词中是否已包含项目路径：**

- 若触发词中已有路径（如 `项目分析 /Users/foo/my-project`），直接使用该路径，**跳过路径询问**
- 若触发词中没有路径，则通过 `AskUserQuestion` 询问项目路径

无论路径是否已知，**必须通过 `AskUserQuestion` 一次性收集以下信息**（已知的字段在选项中给出默认值供确认）：

- **项目路径**（已从触发词提取则预填，否则必填）
- **分析重点**（可选，如"重点看支付模"、"重点看数据库设计"，留空=全部）
- **输出目录**（可选，留空则默认输出到**项目根目录**）

收集后立即用 `Bash` 获取当前时间：

```bash
date "+%Y-%m-%d %H:%M:%S"
```

**输出文件命名规则：** `{输出目录}/{YYYY-MM-DD HH:mm:ss}_{项目名}_概览.md`
项目名取项目根目录的文件夹名。

---

## 阶段 1：广度快照（Phase 1）

> 目标：在不深读代码的前提下，快速建立项目的全局地图。所有扫描用 `Bash` 和 `Glob` 批量完成，不逐文件精读。
>
> **流式播报要求**：每个 1.x 步骤开始前输出 `🔍 正在扫描：{步骤名}…`，完成后立即输出 `✓ {步骤名}：{简要结果}`，然后再开始下一步。严禁攒完所有步骤再统一输出。

### 1.1 项目基本信息

```bash
# 目录树（最多 3 层，排除 node_modules/.git/dist/build/__pycache__/.venv/vendor）
find {项目路径} -maxdepth 3 -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/__pycache__/*' \
  -not -path '*/.venv/*' -not -path '*/vendor/*' | sort
```

### 1.2 技术栈识别

按优先级依次检测以下文件，**每个存在的文件都必须读取完整内容**：

| 文件 | 识别目标 |
|------|---------|
| `package.json` | Node.js 技术栈，`dependencies` + `devDependencies` |
| `pom.xml` | Java/Maven，`<dependencies>` |
| `build.gradle` / `build.gradle.kts` | Java/Kotlin/Gradle |
| `requirements.txt` / `pyproject.toml` / `setup.py` / `Pipfile` | Python |
| `go.mod` | Go，模块名 + 依赖 |
| `Cargo.toml` | Rust |
| `composer.json` | PHP |
| `*.csproj` / `*.sln` | .NET/C# |
| `Gemfile` | Ruby |

同时检测：
- `Dockerfile` / `docker-compose.yml` — 运行时环境
- `.env.example` / `application.yml` / `application.properties` / `config.yaml` — 配置结构
- `README.md` / `README.rst` — 项目自述

### 1.3 框架识别规则

根据 1.2 读到的内容，按以下规则判断框架类型：

| 依赖关键词 | 框架 |
|-----------|------|
| `spring-boot` / `spring-web` | Spring Boot |
| `express` / `koa` / `fastify` | Node.js Web |
| `django` / `flask` / `fastapi` | Python Web |
| `gin` / `echo` / `fiber` | Go Web |
| `react` / `vue` / `angular` / `next` / `nuxt` | 前端框架 |
| `mybatis` / `jpa` / `hibernate` | ORM |
| `sqlalchemy` / `tortoise` / `peewee` | Python ORM |
| `gorm` / `sqlx` | Go ORM |
| `kafka` / `rabbitmq` / `rocketmq` | 消息队列 |
| `redis` / `jedis` / `lettuce` | 缓存 |
| `elasticsearch` / `opensearch` | 搜索引擎 |

### 1.4 模块结构扫描

```bash
# 扫描顶层目录结构（识别模块划分）
ls -la {项目路径}/

# 扫描典型入口文件
find {项目路径} -maxdepth 2 -name "main.*" -o -name "app.*" -o -name "index.*" \
  -o -name "bootstrap.*" -o -name "server.*" | grep -v node_modules | grep -v dist
```

### 1.5 接口文件扫描

```bash
# 扫描路由/控制器文件
find {项目路径} -type f \( \
  -name "*controller*" -o -name "*Controller*" \
  -o -name "*router*" -o -name "*routes*" \
  -o -name "*handler*" -o -name "*Handler*" \
  -o -name "*api*" -o -name "*Api*" \
  -o -name "urls.py" -o -name "views.py" \
\) | grep -v node_modules | grep -v dist | grep -v test | grep -v __pycache__

# 扫描 OpenAPI/Swagger 定义
find {项目路径} -name "swagger*" -o -name "openapi*" | grep -v node_modules
```

### 1.6 数据模型扫描

```bash
# 扫描 Model/Entity/Schema 文件
find {项目路径} -type f \( \
  -name "*model*" -o -name "*Model*" \
  -o -name "*entity*" -o -name "*Entity*" \
  -o -name "*schema*" -o -name "*Schema*" \
  -o -name "*dao*" -o -name "*Dao*" \
  -o -name "*mapper*" -o -name "*Mapper*" \
\) | grep -v node_modules | grep -v dist | grep -v test | grep -v __pycache__

# 扫描数据库 migration 文件
find {项目路径} -type d \( -name "migration*" -o -name "migrations" -o -name "db" \) | grep -v node_modules
find {项目路径} -name "*.sql" | grep -v node_modules | head -20
```

### 1.7 配置文件扫描

```bash
find {项目路径} -maxdepth 3 -name "*.yml" -o -name "*.yaml" -o -name "*.properties" \
  -o -name "*.toml" -o -name "*.ini" -o -name ".env.example" \
  | grep -v node_modules | grep -v dist | grep -v __pycache__
```

### 1.8 测试覆盖扫描

```bash
find {项目路径} -type d -name "test*" -o -name "tests" -o -name "spec" \
  | grep -v node_modules | grep -v dist
find {项目路径} -name "*test*" -o -name "*spec*" | grep -v node_modules | grep -v dist | wc -l
```

**阶段 1 完成后，立即执行两步：**

**步骤 A：输出快照摘要**

```
📸 Phase 1 快照完成

项目：{项目名}（{项目路径}）
语言/框架：{语言} + {主框架} + {其他框架}
模块数量：{N} 个顶层模块（{模块名列表}）
接口文件：{N} 个（待 Phase 2 精读）
数据模型文件：{N} 个（待 Phase 2 精读）
配置文件：{N} 个
测试文件：{N} 个
依赖总数：{N} 个（生产 {N} 个，开发 {N} 个）

> 输入「深入」进入 Phase 2 详细分析，或输入「只要快照」直接生成报告。
> 「深入 支付模块」可指定优先深入的模块。
```

**步骤 B：立即将 Phase 1 结果写入报告文件（如文件已由 2.0 创建则追加，否则先创建）**

依次用 `Bash` 追加写入以下两章：

第一章：
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 一、技术栈 & 依赖

### 基础信息
- **语言**：{语言} {版本}
- **主框架**：{框架} {版本}
- **运行环境**：{Docker / JDK版本 / Node版本 / Python版本}
- **构建工具**：{Maven / Gradle / npm / pip / make}

### 核心依赖

| 依赖名 | 版本 | 用途 |
|--------|------|------|
| {依赖} | {版本} | {用途} |

### 开发/测试依赖

| 依赖名 | 版本 | 用途 |
|--------|------|------|

---
EOF
```

第二章：
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 二、项目结构 & 模块划分

\`\`\`
{目录树，3层，注释每个主目录的职责}
\`\`\`

### 模块说明

| 模块/目录 | 职责 | 核心文件 |
|----------|------|---------|
| {模块} | {职责描述} | {核心文件名} |

---
EOF
```

输出：`✓ 第一章、第二章已写入（来自 Phase 1 扫描结果）`

---

## 阶段 2：深度分析 + 即时写入（Phase 2）

> **核心原则：分析即写入，严禁攒内容。** 每个子步骤分析完成后，立即用 `Bash` 将结果追加写入报告文件，不得等到所有分析完成后再统一生成。
>
> **流式播报要求**：每读一个文件前输出 `📖 正在读取：{文件路径}`，读完并写入后立即输出 `✓ 已写入：{提取到的关键信息}`，然后继续下一个文件。

### 2.0 初始化报告文件

**在开始任何分析前**，立即执行：

```bash
cat > "{输出文件绝对路径}" << 'HEADER'
# {项目名} 项目概览

> 生成时间：{YYYY-MM-DD HH:mm:ss}
> 项目路径：{绝对路径}
> 分析范围：{全部模块 / 指定模块}

---
HEADER
```

输出：`📝 报告文件已创建：{输出文件路径}，开始逐章分析并写入…`

### 2.1 精读优先级规则

按以下顺序决定精读哪些文件：

1. **用户指定重点** → 优先精读对应模块的所有文件
2. **入口文件**（`main.*` / `app.*` / `server.*`）→ 必读
3. **路由/控制器** → 必读（提取接口）→ **读完立即写入第三章**
4. **数据模型** → 必读（提取表结构）→ **读完立即写入第五章**
5. **Service 层** → 按需读（理解业务逻辑）→ **读完立即写入第七章**
6. **配置文件** → 精读 → **读完立即写入第六章**

### 2.2 接口提取 + 即时写入

精读每个路由/控制器文件后，**立即**用 `Bash` 将该文件的接口追加写入报告：

```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 三、API 接口列表（或追加到已有章节）

### {模块名}

#### {HTTP方法} {完整路径}
- **函数**：`{函数/方法名}`
- **入参**：`{参数名}: {类型}` （query/body/path）
- **功能**：{从代码推断的功能描述}

EOF
```

> 第一个路由文件写入时附带章节标题 `## 三、API 接口列表`，后续文件直接追加内容，不重复写标题。

### 2.3 数据模型提取 + 即时写入

精读每个 Model / Entity / migration 文件后，**立即**用 `Bash` 将该文件的表结构追加写入报告：

```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 五、数据模型 & 数据库（或追加到已有章节）

#### 表名：`{table_name}`

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| {field} | {type} | {NOT NULL / PK / FK} | {注释或推断} |

**关联**：{关联表} ({关联类型})

EOF
```

> 同上，第一个模型文件写入时附带章节标题，后续直接追加。

### 2.4 配置提取 + 即时写入

精读配置文件后，提取并**立即追加写入**：
- 数据库连接配置（host / port / db name）
- 中间件配置（Redis / Kafka / MQ 地址）
- 业务配置项（关键开关、阈值、超时时间）
- 环境变量清单（`.env.example` 中的所有 KEY）

敏感值用 `{REDACTED}` 替代。写入格式对应**第六章**。

### 2.5 业务逻辑摘要 + 即时写入

精读 Service 层时，**每读完一个 Service 文件立即追加写入**第七章，只提取：
- 该 Service 的职责（一句话）
- 调用的外部依赖（DB / 缓存 / MQ / 外部接口）
- 关键业务规则（有 if/else/switch 的核心判断逻辑）

### 2.6 补全其余章节

接口、模型、配置、业务逻辑写入完成后，依次追加写入以下章节（每章一次 `Bash` 追加，追加完立即输出 `✓ 第{N}章已写入`）：

**第四章：HTTP 外部调用**
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 四、HTTP 外部调用

> 项目中主动发起的 HTTP 请求（调用第三方服务或内部微服务）

| 调用方 | 目标服务 | 路径/URL | 用途 |
|--------|---------|---------|------|

（未检测到外部 HTTP 调用则注明：未发现主动 HTTP 外部调用）

---
EOF
```

**第八章：代码规范 & 工程实践**
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 八、代码规范 & 工程实践

- **测试**：{有/无测试，测试框架，测试文件数量}
- **代码风格**：{检测到的 lint 工具 / formatter}
- **CI/CD**：{检测到的 .github/workflows / Jenkinsfile / .gitlab-ci.yml}
- **日志**：{日志框架，日志级别配置}
- **异常处理**：{全局异常处理机制}

---
EOF
```

**第九章：待核查项**
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 九、待核查项

- {未能从代码确认的内容} `[待核查]`

---
EOF
```

**第十章：快速上手建议**
```bash
cat >> "{输出文件绝对路径}" << 'EOF'
## 十、快速上手建议

1. **启动项目**：{从 README 或 Makefile 提取的启动命令}
2. **必须配置**：{必填的环境变量或配置文件}
3. **关键入口**：{主入口文件路径}
4. **核心表**：{最重要的 2-3 张业务表}
5. **高频接口**：{最核心的 2-3 个接口}
EOF
```

---

## 阶段 3：收尾播报

> 阶段2中分析与写入已同步完成，此阶段只做最终确认和播报。

用 `Bash` 统计报告文件行数确认写入成功：

```bash
wc -l "{输出文件绝对路径}"
```

输出完成摘要：

```
✅ 项目概览报告已生成

输出文件：{绝对路径}
接口总数：{N} 个
数据表总数：{N} 张
模块总数：{N} 个
待核查项：{N} 条

> 输入「深入 {模块名}」可对某个模块进行更详细的分析。
```

---

## 大项目保护机制

Phase 1 扫描完成后，如果检测到以下任一情况，**在快照摘要末尾附加警告并询问用户是否继续**：
- 接口文件数量 > 50
- 数据模型文件数量 > 30
- 顶层模块数量 > 15

警告格式：
```
⚠️  大型项目检测：接口文件 {N} 个 / 模型文件 {N} 个
   Phase 2 全量分析预计需要读取大量文件，耗时较长。
   建议：输入「深入 {最重要模块名}」聚焦核心模块，或「只要快照」直接生成 Phase 1 报告。
```

---

## 快捷指令

| 指令 | 效果 |
|------|------|
| `只要快照` | 跳过 Phase 2，仅基于 Phase 1 扫描结果生成报告 |
| `深入` | 进入 Phase 2 全量深度分析 |
| `深入 {模块名}` | Phase 2 仅深入指定模块 |
| `全自动` | Phase 1 + Phase 2 全部自动执行，无需确认 |
| `重新扫描` | 强制重新执行 Phase 1 |

---

## 执行顺序

```
阶段 0：信息收集（AskUserQuestion）
  → 阶段 1：广度快照（Bash/Glob 批量扫描）
      → 输出快照摘要，等待用户指令
  → 阶段 2：深度分析 + 即时写入（Read 精读 → 分析完立即 Bash 追加写入，分析写入交织进行）
  → 阶段 3：收尾播报（wc -l 确认写入，输出完成摘要）
      → 输出完成摘要
```

> 输入 `全自动` 跳过所有确认节点，连续执行至报告生成完毕。
