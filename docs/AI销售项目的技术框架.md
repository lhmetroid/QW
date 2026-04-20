### 1.1 前端（Web SaaS 平台）

- **核心框架：React 18（基于 Vite 构建）**
  - **开发模式**：全面采用 **Hooks (函数式组件)** 机制（如 `useState`, `useEffect`, `useMemo`），确保复杂业务逻辑（如审阅状态转换、轮询请求）的高度解耦与可维护性。
  - **架构特性**：面向企业级 **SaaS** 应用设计，支持多租户逻辑与灵活的权限管理；遵循 **API-First** 原则，通过 Axios 实现非阻塞的前后端分离交互。
  - **构建工具**：使用 **Vite** 提供极速的热更新 (HMR) 和生产环境优化，适配现代浏览器环境。
- **UI 技术栈：Ant Design (企业级专业 UI 规范)**
  - **核心库**：采用 **Ant Design 5.x**，利用其高度成熟的组件体系快速构建复杂的 后台。
- **业务架构特性：**
  - **高度组件化**：提取了如 `ReviewItemEditor`（审阅编辑器）、`DefinitionPatchTooltip`（定义差异展示）等针对 AI 业务深度定制的复用组件，确保全局交互体验的一致性。
  - **实时性与一致性**：针对模型训练这种长耗时任务，内部封装了统一的状态轮询与反馈机制，确保前端界面能实时体现后端异步任务的进展。
  - **标准化扩展**：遵循 Ant Design 的视觉设计语言（Design Language），使得新功能的开发（如新增评估维度或模型对比模块）能够快速融入现有界面风格，实现项目间的视觉与操作统一。
- **路由技术标准：React Router v6**
  - **路由模式**：采用 `History` 模式（`BrowserRouter`），确保页面 URL 具有语义化（如 `/manual-review/batch/001`），支持浏览器的前进、后退和页面刷新保持。
  - **集中化路由配置 (`routes/index.jsx`)**：禁止在各组件中散乱定义路由，应建立统一的路由表配置文件。
- **布局与导航统一 (Layout & Navigation)**
  - **菜单映射**：将当前的 `Tabs` 切换升级为 Ant Design 的 **`Layout + Sider`（侧边栏菜单）** 布局。
  - **联动机制**：菜单的选中状态、URL 路径、面包屑（`Breadcrumb`）应始终保持三向同步。
- **网络通信**：
  - Axios（统一封装请求拦截与错误处理）
    - 自动注入 JWT Token
    - 支持 Token 过期自动刷新
    - 全局异常处理与日志记录
  - WebSocket / SSE（用于实时任务通知、进度推送等）

- **文件上传**：
  - 支持分片上传（适用于大文件 / 视频等场景）
  - 断点续传与失败重试由客户端与后端协同实现

## 1.2 后端（推荐：FastAPI，面向 AI/数据处理优先）

- **服务框架**：FastAPI
  - 架构风格：REST（必要时补充 WebSocket/SSE）
  - 负责业务接口、AI/数据处理能力编排与对外服务
- **身份认证（Authentication）**：
  - JWT（Access Token）+ Refresh Token
  - 支持多端登录与安全刷新、吊销与过期策略
- **权限控制（Authorization）**：
  - **RBAC（角色权限）**：菜单/功能级权限
  - **ABAC（属性策略）**：按部门/标签/类别/项目等属性进行细粒度授权（Policy 化实现，统一中间件校验）
- **异步任务与调度（Background Jobs）**：
  - 推荐 **RQ / Celery + Redis**（二选一）
    - **RQ**：落地快、适合多数 ToB 异步任务（导入导出、文件处理、转写、批处理）
    - **Celery**：适合更复杂任务编排、重试策略与多队列场景
  - 任务状态：提供 taskId 查询与进度上报（前端可轮询或订阅）
- **实时通知（Real-time）**：
  - **WebSocket**（任务完成通知、进度推送、会议转写完成等）
  - 备选：SSE（仅单向推送场景更简单）
- **AI/数据处理支持（加分项，建议写进方案）**：
  - 推理/批处理任务统一走后台队列，避免阻塞 API
  - 大文件/视频/音频处理采用异步管线（上传→入队→处理→回写结果）

## 1.3 数据库（开源推荐）

PostgreSQL（推荐首选，商业交付友好）
目前这个系统的数据连接：

DBHost=your-db-host
DBPort=5432
DBName=your-db-name
DBUserId=your-db-user
DBPassword=your-db-password

## 1.4 文件存储（cos存储）

COS_SECRET_ID=your-cos-secret-id
COS_SECRET_KEY=your-cos-secret-key
COS_REGION=your-cos-region
COS_BUCKET=file-1300976706

## 1.5 向量检索（RAG 必备）

P0：先用 PostgreSQL + pgvector（一体化部署，最省心）
P1/P2：规模大可换 Milvus/Qdrant（可选）

## 1.6 文档解析与索引

文档解析：
Office：OpenXML SDK / NPOI（Excel/Word/PPT）
PDF：UglyToad.PdfPig（纯文本）+ 可选 OCR（Tesseract）
图片：OCR（Tesseract 或 PaddleOCR 的服务化版本）
音视频：转写（Whisper）

索引：
结构化：Postgres（文件名/标签/类别/上传者）
全文：P0 可先用 Postgres Full-Text Search；P1 可上 OpenSearch/Elasticsearch（可选）

## 1.7 大模型与语音模型（名称 + 功能）

你要“模型名称和功能”，我给你一套可落地组合（可替换）：
文字问答（LLM）
OpenAI GPT-4o / GPT-4.1（云端，质量高）

私有化可选：
Llama 3.x Instruct（本地/自建推理服务）
Qwen2.5 Instruct（中文更强，适合企业中文知识库）
功能：问答、摘要、分类、标签建议、行动项提取、版本差异解释

Embedding（向量化）
云端：text-embedding-3-large / 3-small
私有化：bge-m3（多语言强）或 bge-large-zh（中文）

语音转写（ASR）
Whisper large-v3（准确率高，支持中英文）
部署方式：本地 GPU 服务 或 云端服务

文档/图片 OCR
Tesseract OCR（开源）
可升级：PaddleOCR（效果更好，需额外服务化）



## 1.8 AI 协同与自动化结单规范 (Scenario 2)

**本规范用于指导 AI 助手在完成代码修改后的自动化收尾工作，确保版本管控与提交记录的标准化。**

> **AI 触发指令**：`任务完成，执行结单流程`

### 自动化 SOP 执行步骤：

1. 变更分析 (Analysis)：
   - AI 自动对比自本次任务开始以来的所有代码差异（Diff），精准识别业务逻辑变更。
2. 版本自动化管理 (Version Bump)：
   - **操作**：修改 `package.json`（或指定版本文件），将版本号的 **补丁位 (Patch)** 自动自增 1。
   - **意义**：确保每次功能迭代或 Bug 修复都有唯一的版本标识，增强 SaaS 平台的可追溯性。
3. 技术总结 (ChangeLog Generation)：
   - AI 需按照以下结构输出变动总结：
     - **【版本号】**：`v[New Version]`
     - **【变更内容】**：简述核心代码改动及其目的。
     - **【影响范围】**：受影响的组件、页面或后端接口。
4. 自动化 Git 归档 (Git Commit)：
   - **指令**：顺序执行 `git add .` 与 `git commit`。
   - **提交格式**：`chore: release v[新版本号] - [一句话简短总结]`。
5. 离场确认 (Final Report)：
   - 展示提交成功后的 **Commit ID**、最新的 **版本号** 以及生成的 **ChangeLog** 摘要供人核验。

## 1.9 每日项目总结规范 (Daily Progress Sync)

**本规范要求 AI 在每个任务阶段（或结单时）实时维护一份“项目进度日志”，确保项目轨迹透明可追溯。**

### 日志维护逻辑：

1. 文件定位：
   - AI 自动检查 `docs/logs/` 目录下是否存在名为 `YYYY-MM-DD.md`（当日日期）的文件。
   - 若不存在，则按模板创建新文件；若已存在，则在文件末尾追加本次变动。
2. 记录时机：
   - **里程碑触发**：每当完成一个重要的功能模块、修复一个复杂 Bug 或执行“自动结单”时。
3. 内容格式：
   - 记录必须清晰、简短，包含以下要素：
     - **时间戳**：`[HH:mm]`
     - **任务标题**：例如 `人工审阅页状态流转逻辑重构`。
     - **执行动作**：`Edit / Debug / Refactor`。
     - **关键结果**：简述该步骤产生的实质影响（如：“修复了状态不刷新的 Bug”，“新增了确认弹窗”）。
     - **遗留问题 (Optional)**：若该步骤未彻底完成，需标注 `[TODO]` 及下一步计划。
