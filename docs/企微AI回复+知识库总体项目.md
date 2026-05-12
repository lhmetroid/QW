# 项目功能点与技术全景（最新版）

> 口径说明：**以当前代码与现有运行文档为准**，并对旧方案/旧文档中的过时描述做“以新覆盖旧”的统一归并；本文旨在把“系统已经具备的能力”完整拉平到可交付、可运维、可扩展的清单。

## 概述

本项目是一个面向销售团队的 **“企微实时智能 + 销售知识库治理（导入-审核-发布-检索-质量-回归）”** 一体化工作台：

- **对内（销售/运营/质检）**：提供知识库的标准化生产线（导入/候选/审核/发布门禁/治理/回滚/回归），确保“可用于对外承诺”的知识被严格治理。
- **对外（企微侧边栏/外部系统）**：提供侧边栏辅助接口与知识证据接口，把“真实会话 → 结构化摘要 → CRM画像 → 知识证据 → 回复建议（可复制/可质检/可追溯）”串成稳定链路。

## 最终实现目标（最终交付形态）

系统最终目标是实现 **“真实企微对话驱动的可控智能回复”**，并满足：

- **知识可控**：所有对外承诺（尤其报价）必须基于可追溯证据与结构化规则，发布前通过门禁校验，支持版本化与回滚。
- **链路可观测**：每次“智能触发/侧边栏请求”可沉淀快照、分步耗时、质量分、人工反馈，形成可运营闭环。
- **可选增强不拖累核心**：CRM、企微应用回调、会话存档 SDK、外部知识库2（Sales KB API）均是增强链路；**缺失时不影响知识库核心链路**（导入/检索/审核/发布）。

---

## 一、系统已有功能点（按业务链路与页面/接口）

### 1) 前端工作台（`frontend/index.html`）

当前前端为 **单页静态工作台**（Tailwind CDN + 原生 JS），由后端挂载为静态站点：

- **入口**：`GET /` 或 `GET /static`（后端 `app.mount("/static", StaticFiles(..., html=True))`）
- **顶层三大节点**（与现有使用说明一致）：
  - **企微实时智能**
  - **企微智能回复统计分析**
  - **知识库管理**
- **运行特性**：
  - 无登录页、无账号体系（生产如需鉴权需另行接入）。
  - 支持会话列表查询/日期筛选、右侧“回复生成链路”面板可拖拽调整宽度。

> 备注：`docs/AI销售项目的技术框架.md` 中提到的 React/Vite/Ant Design 属于**旧的/规划口径**；以当前仓库为准，前端实现已落地为 `frontend/index.html` 的静态工作台。

### 2) 企微实时智能（真实会话→分析→回复建议）

#### 2.1 真实会话同步（会话存档 SDK，可选）

- **同步今日真实记录**：`POST /api/sync/today`
- **按会话同步**：`POST /api/sync/session`
- **同步环境诊断**：`GET /api/system/archive_sync_status`
  - 返回 SDK/DLL/私钥/密钥是否齐全、游标文件、锁文件、最近同步事件、数据库摘要等。

实现要点：

- 会话存档适配器：`backend/archive_service.py`
  - Windows 下通过 `WeWorkFinanceSdk.dll`（官方 C-SDK V3）加载与映射。
  - 支持 **增量游标**（`backend/seq_cursor.txt`）与 **跨进程锁**（`backend/archive_sync.lock`）避免并发重复同步。
  - 同步写入 `message_logs`，并以 `archive_msg_id` 去重。
- 可选开关：`.env` 中 `ENABLE_ARCHIVE_POLLING`、`PRIVATE_KEY_PATH`、`CHATDATA_SECRET` 等（详见 `backend/config.py` 与 `docs/生产部署与配置清单.md`）。

#### 2.2 会话列表与消息读取（仅真实会话）

- **会话列表**：`GET /api/sessions`（仅 `message_logs.is_mock=false`）
  - 支持 `chat_date=YYYY-MM-DD` 按天筛选，并返回当日触发统计摘要（API 调用次数/质量分规则等）。
- **会话消息**：`GET /api/sessions/{user_id}/messages`

数据层：

- `MessageLog`：真实会话消息表（含 `archive_seq`、`archive_msg_id`）。

#### 2.3 结构化摘要（LLM1 / 可对比模型）

核心作用：把真实对话整理成可用于后续检索与生成的话术上下文（topic/core_demand/关键事实/风险/待确认/状态等），并持久化到 `intent_summaries`。

相关接口（前端触发/后端沉淀）：

- **手动触发某一步链路（“拔枪”）**：`POST /api/sessions/{user_id}/trigger_llm`
- **读取分析快照**：`GET /api/sessions/{user_id}/analysis`、`GET /api/sessions/{user_id}/analysis_versions`
- **创建/保存分析版本**：`POST /api/sessions/{user_id}/analysis_versions`

实现要点：

- LLM 调用封装：`backend/intent_engine.py`
  - 支持 **Dify app-key（`app-` 前缀）** 与 **OpenAI 兼容网关** 两类调用方式（自动选择 `/chat-messages`、`/completion-messages` 或 `/chat/completions`）。
  - 支持对比模型（`LLM1_COMPARE_*`、`LLM2_COMPARE_*`）与 prompt trace 存证（可脱敏，见 `LOG_DESENSITIZE_ENABLED`）。

#### 2.4 CRM 客户画像（可选增强）

作用：为 LLM2 生成话术提供客户背景与风险信息；属于增强链路，未配置不影响知识库核心能力。

- CRM Router：`backend/crm_profile.py`（以 `app.include_router(crm_profile_router)` 挂载）
- CRM 连接配置：`CRM_DBHost/Port/Name/UserId/Password/ODBC Driver` 等（详见 `docs/生产部署与配置清单.md`）。

#### 2.5 知识证据（双通道：本地知识库V2 + 外部知识库2 API）

系统在“刷新知识/侧边栏直出”时支持两路知识证据来源（可并行、可降级）：

- **本地知识库 V2（本项目内置）**：统一导入/审核/发布/检索/治理，接口 `POST /api/kb/retrieve`
- **外部知识库2（Sales KB API）**：通过 HTTPS 反向代理域名访问，接口基址 `SALES_KB_API_BASE_URL`（默认 `https://knowledgebase.speedasia.net`）

与知识库2相关的运行诊断：

- `backend/startup_check.py` 会阻断“核心配置仍为占位符”的启动，并强制校验 `SALES_KB_API_BASE_URL`：
  - 必须 `https`
  - 不允许旧内网 IP（如 `192.168.31.124`）
  - 建议不带显式端口

#### 2.6 二阶段回复建议（LLM2，多风格/对比模型/质量分）

目标：给出**可直接复制发送给客户**的 `reply_reference`，并同时输出**给销售看的** `followup_rationale`（两字段拆分，避免复制时混入“思路说明”）。

能力点：

- 支持 **多风格候选**（`reply_style_results_v2`）、支持 **对比模型**（compare slot）。
- 支持把候选与真实销售回复做 **贴合度评分**（由配置开关控制：`API_REPLY_ENABLE_SCORING`）。
- 支持 **线程事实门禁**：例如非正式报价阶段禁止确定性报价承诺；客户已确认时间不应再追问同一时间等（`backend/knowledge_governance.py`）。

对外接口（企微侧边栏）：

- `POST /api/wecom/sidebar_assist`
  - 请求：`external_userid`、`userid`、`force_refresh`、`sync_archive_before_read`
  - 响应：`reply_reference`、`followup_rationale`、`reply_style_results_v2`、链路耗时与阶段状态等
  - 特性：**请求去重缓存 + in-flight 并发去重**（同会话同消息节点短时间重复请求直接复用结果，降低模型成本与延迟）

### 3) 企微智能回复统计分析（按触发逐条审计）

该模块用于把“每一次触发”沉淀为可运营数据，用于追踪：

- 每次触发的多步链路内容（会话输入/快扫/LLM1/CRM/知识证据/LLM2/校验）
- 耗时、质量分、人工回复、人工质检标签/备注

相关接口（节选，具体以 `backend/main.py` 为准）：

- 触发统计：`GET /api/wecom/trigger_analytics`
- 质量标注：`POST /api/wecom/trigger_analytics/quality_annotation`
- Thread 事实读取：`GET /api/thread_facts/{session_id}`

### 4) 知识库管理（V2 治理闭环：导入→审核→发布→检索→治理→回归→回滚）

#### 4.1 知识实体与状态机

核心实体（见 `backend/database.py`）：

- `KnowledgeDocument`：文档主表（来源、状态、版本、生效期、风险、标签、批次）
- `KnowledgeChunk`：切片表（实际参与检索的“业务可调用知识单元”）
- `PricingRule`：结构化报价规则（高风险知识的核心证据）
- `KnowledgeCandidate`：候选知识（从反馈/会话抽取/邮件抽取生成，需编辑后转草稿）
- `KnowledgeHitLog`：检索命中日志（可反向产出候选知识）
- `JobTask`：异步任务（导入、回归、训练、补全等）

状态机（文档/切片/规则联动）：

- `draft` 草稿 → `review` 审核中 → `active` 已发布 → `archived` 已归档；以及 `rejected` 驳回
- 发布前有两层门禁：
  - **结构门禁**：例如报价类必须有生效时间、且每个报价切片必须有结构化规则（`_document_publish_errors`）
  - **发布门禁（gate）**：用于更复杂的风险校验与强制发布理由（`_ensure_publish_gate`）

#### 4.2 手工新增/编辑

- 新增单条知识（单文档单切片）：`POST /api/kb/documents/manual`
- 新增多切片文档：`POST /api/kb/documents/manual_multi`
- 文档列表/详情：`GET /api/kb/documents`、`GET /api/kb/documents/{document_id}`
- 切片列表/详情：`GET /api/kb/chunks`、`GET /api/kb/chunks/{chunk_id}`
- 给切片补报价规则：`POST /api/kb/chunks/{chunk_id}/pricing_rule`
- 报价规则集中查看/停用归档：`GET /api/kb/pricing_rules`、`POST /api/kb/pricing_rules/{rule_id}/archive`

实现细节（重要）：

- 写入/编辑切片时会调用 `EmbeddingService` 生成向量（失败可降级为无向量模式）。
- 若创建报价类知识且未给 `pricing_rule`，会尝试推断规则候选（`infer_pricing_rule_candidate`）。

#### 4.3 审核、发布、归档、驳回、版本恢复

单文档：

- 提交审核：`POST /api/kb/documents/{document_id}/submit_review`
- 审核通过：`POST /api/kb/documents/{document_id}/approve`
- 发布：`POST /api/kb/documents/{document_id}/publish`（含 force/force_reason 支持）
- 归档：`POST /api/kb/documents/{document_id}/archive`
- 驳回：`POST /api/kb/documents/{document_id}/reject`
- 恢复到历史版本：`POST /api/kb/documents/{document_id}/restore/{version_no}`

批量：

- `POST /api/kb/bulk/documents/submit_review`
- `POST /api/kb/bulk/documents/approve`
- `POST /api/kb/bulk/documents/publish`
- `POST /api/kb/bulk/documents/archive`

批次（Import Batch）：

- 批次列表/详情：`GET /api/kb/import_batches`、`GET /api/kb/import_batches/{import_batch}`
- 批次文档：`GET /api/kb/import_batches/{import_batch}/documents`
- 批次提交审核/发布/归档/通过/回滚：对应 `POST /api/kb/import_batches/{import_batch}/...`

#### 4.4 导入中心（Excel/CSV/辅助文本，多种来源）

1) **统一知识 Excel 模板/导入**（导入中心主入口）

- 模板列表：`GET /api/kb/import/templates`
- 下载模板：`GET /api/kb/import/template/download` 或 `GET /api/kb/import/templates/{template_type}/download`
- 预览校验（不落库）：`POST /api/kb/import/excel/preview`
- 确认落库（同步）：`POST /api/kb/import/excel/commit`
- 确认落库（异步）：`POST /api/kb/import/excel/commit_async`（落到 `JobTask`）

关键能力：

- Excel 行支持 `auto_split`：触发 LLM 自动切分为多条 chunk（强约束 JSON 输出，避免兜底编造）。
- 预览/落库会产出 `import_batch`，后续可批次审核发布/回滚。

2) **业务知识 CSV 导入**（更偏“批量基建数据”）

- `POST /api/kb/import/business_csv`
- 实现：`backend/business_csv_import.py`
  - 内置行级 override、跳过策略（`DEFAULT_SKIP_ROWS`）、标题归一化
  - embedding 失败可降级（`_optional_embedding_for_import`）

3) **FAQ Excel 快捷导入**

- `POST /api/kb/import/faq_excel`

4) **辅助文本导入（LLM 辅助拆分→落库）**

- `POST /api/kb/import/assisted_text`

#### 4.5 候选知识（从反馈/抽取产生→编辑→转草稿）

- 候选列表/详情：`GET /api/kb/candidates`、`GET /api/kb/candidates/{candidate_id}`
- 更新候选：`PATCH /api/kb/candidates/{candidate_id}`
- 从命中日志反馈生成候选：`POST /api/kb/candidates/from_feedback`
- 候选转草稿：`POST /api/kb/candidates/{candidate_id}/promote`
- 批量转草稿：`POST /api/kb/candidates/batch_promote`

#### 4.6 检索测试与命中日志

- 证据检索（只返回证据包，不生成回复）：`POST /api/kb/retrieve`
- 命中日志：`GET /api/kb/hit_logs`
- 命中统计：`GET /api/kb/hit_logs/stats`
- 命中反馈（反哺候选）：`POST /api/kb/hit_logs/{log_id}/feedback`

#### 4.7 质量治理

- 质量报告：`GET /api/kb/quality/report`
- 冲突检测：`GET /api/kb/quality/conflicts`
- 临期检测：`GET /api/kb/quality/expiring`

#### 4.8 回归测试（知识库验收集）

- 用例列表：`GET /api/kb/regression_cases`
- 同步执行：`POST /api/kb/regression_cases/run`
- 异步执行：`POST /api/kb/regression_cases/run_async`（落 `JobTask`）

用例来源：

- `backend/kb_regression_cases.json`（按 group/category/risk_level 等过滤）

#### 4.9 运行状态与配置诊断

- 健康检查：`GET /api/health`、`GET /api/health/ready`
- 配置诊断：`GET /api/system/config_check`
- 公网端点映射：`GET /api/system/public_endpoints`

诊断覆盖：

- PostgreSQL、Embedding、LLM1/LLM2、CRM、企微应用、会话存档 SDK、外部知识库2 API（Sales KB）

---

## 二、技术栈与关键技术（以当前实现为准）

### 1) 前端

- **形态**：静态单页（`frontend/index.html`），后端托管静态资源
- **UI**：Tailwind CSS（CDN `https://cdn.tailwindcss.com`）
- **交互**：原生 JavaScript（无 React/Vite/AntD 依赖）

技术取舍（简要）：

- 选择静态单页是为了缩短交付与部署复杂度，减少前端工程化依赖；后续如需多角色权限/大型组件化，可再演进到 React 工程。

### 2) 后端

- **框架**：FastAPI（路由集中在 `backend/main.py`）
- **配置**：Pydantic Settings（`backend/config.py` 从项目根 `.env` 读入）
- **ORM/DB**：SQLAlchemy + PostgreSQL
- **HTTP 客户端**：`requests`（LLM/Embedding/外部 KB API 调用，支持 `HTTP_TRUST_ENV` 控制代理继承）
- **异步/后台任务**
  - 轻量任务队列：`backend/worker.py`（`Thread(daemon=True)` 写 `JobTask` 状态）
  - 线程池：`ThreadPoolExecutor(max_workers=8)` 用于回复链路并发执行与 in-flight 去重（`REPLY_CHAIN_EXECUTOR`）

### 3) AI 与 RAG

#### 3.1 Embedding（向量化）

- 统一封装：`backend/embedding_service.py`
- 支持 provider：
  - **Ollama**：`/api/embeddings` + `/api/tags`
  - **Dify**：`/v1/chat-messages` / `/v1/completion-messages`（从返回中抽取 embedding/vector，允许无向量降级）
  - **OpenAI-compatible**：`/embeddings` + `/models`
- 内置优化：
  - embedding 结果 **TTL 缓存**（最多 256 条，300 秒）
  - 统一维度校验（`EMBEDDING_DIM`）

#### 3.2 LLM（两阶段 + 对比模型）

- LLM1：结构化抽取（摘要/特征）
- LLM2：回复生成（可复制回复 + 跟进说明）+ 多风格候选
- 对比模型：LLM1_COMPARE、LLM2_COMPARE（用于 A/B 与质量评估）
- Prompt 存证：可脱敏、可截断（`LOG_LLM_PROMPTS`、`LOG_DESENSITIZE_ENABLED`、`LOG_LLM_PROMPT_MAX_CHARS`）

#### 3.3 知识库治理（门禁与质量评分）

- 内容治理与质量评分：`backend/knowledge_governance.py`
  - 知识类型/切片类型/库类型推断（reference/fact）
  - 报价承诺与线程状态一致性校验（阻断不合规回复）
  - 质量分维度：清晰度/完整性/证据可靠性/可复用性等（聚合为 useful/publishable/usable_for_reply）

### 4) 数据模型与存储策略

- PostgreSQL 为主存储（建议 14+）
- 向量字段当前默认以 **JSON** 存储（见 `KnowledgeBase.embedding` 注释：Windows 下 pgvector 扩展/DDL 兼容性原因）
- 同时保留了 **pgvector 可选启用** 的配置入口（`PGVECTOR_ENABLED/REQUIRED` 等），用于未来升级到真实向量索引

---

## 三、当前技术优势与亮点（可对外汇报的“为什么可用”）

### 1) “知识可控”的工程化闭环是主亮点

- **发布门禁**：报价类强制生效期 + 结构化报价规则；不满足即阻断发布（可强制发布但必须给理由，风险可追溯）。
- **版本化与回滚**：文档发布自动递增版本，支持恢复到历史版本并重新进入审核流。
- **命中日志→候选→入库**：把线上真实问题与纠错反馈反哺到候选知识，再转草稿进入治理流程，形成闭环。

### 2) “真实会话驱动”的全链路可观测

- 企微侧边栏 API 具备：
  - 请求去重缓存（短时间重复请求直接复用结果）
  - in-flight 并发去重（同节点多请求只跑一次重链路）
  - 分步耗时与阶段状态（便于定位慢点与失败点）

### 3) 强约束的 LLM 输出策略，避免“兜底胡写”

- Excel `auto_split` 明确要求 **无知识就返回空**，禁止兜底编造 FAQ。
- Thread 事实门禁明确禁止“不在事实阶段却做确定性承诺”，将大模型输出从“能说”约束到“能被允许说”。

### 4) 配置诊断与可选增强解耦

- `startup_check.py` 对核心链路配置做硬性校验，避免“启动成功但实际不可用”的假健康。
- CRM/企微应用/会话存档 SDK/外部知识库2 均是可选增强，缺失时有明确 degraded 提示且不拖累核心知识库链路。

---

## 四、尝试过/考虑过的其他方式与弃用原因（以当前演进结果为准）

### 1) 前端工程化（React/Vite/AntD）→ 当前改为静态单页

- **尝试/规划**：旧文档中存在 React/Vite/AntD 的 SaaS 化规划。
- **弃用/延后原因**：
  - 交付周期与部署复杂度更高（Node 构建链、依赖安装、产物托管、版本一致性）
  - 当前核心价值在“知识治理闭环 + 企微链路”，静态单页已满足交付与迭代速度

### 2) pgvector 原生向量类型 → 当前默认 JSON 存储（可选再启用 pgvector）

- **尝试**：模型层曾计划使用 `Vector(1024)`。
- **弃用原因**：
  - Windows/目标环境在 DDL/扩展安装上存在不确定性与交付风险
  - 先保证全链路可用与数据可落库，再逐步升级向量索引

### 3) 单一 LLM/单一风格 → 当前支持多模型对比 + 多风格候选

- **原因**：业务方需要在不同客户/场景下切换风格，并需要可量化的对比评估；同时在成本与稳定性上需要可降级与可对照。
- **当前策略**：默认可配置为“单模型单风格输出”（`API_REPLY_SINGLE_MODEL_SINGLE_STYLE=true`），生产可按稳定性收敛。

### 4) 旧内网直连知识库2 → 当前统一 HTTPS 域名反代

- **原因**：内网 IP 在生产环境不可控、证书/跨网不稳定；改为 HTTPS 域名与反代后可统一运维与访问策略。
- **配套**：`startup_check.py` 强制校验 `SALES_KB_API_BASE_URL` 以避免回退到旧 IP。

---

## 五、部署与运维要点（摘要）

以 `docs/生产部署与配置清单.md` 为准，关键结论：

- **核心必备**：PostgreSQL + Embedding 服务 + LLM1 + LLM2 + Sales KB API（知识库2）
- **可选增强**：CRM（SQL Server）、企微应用（回调/发消息）、会话存档 SDK（WeWorkFinanceSdk.dll + 私钥 + CHATDATA_SECRET）
- **推荐入口**：
  - `GET /api/health/ready`
  - `GET /api/system/config_check`
- **生产网络注意**：代理策略（`HTTP_TRUST_ENV`）、内网服务绕代理、HTTPS 反向代理与上传体积/超时配置

---

## 六、文档索引（仓库内）

- `docs/功能清单与使用说明.md`：产品使用口径（页面与操作）
- `docs/生产部署与配置清单.md`：生产部署与排障清单
- `docs/企微侧边栏辅助接口文档.md`：对外侧边栏接口字段说明
- `docs/销售知识库 API 接入文档.md`：外部知识库2接口（注意其中 Base URL 为旧口径，已由生产清单的 HTTPS 域名覆盖）

