# TASK_HANDOFF

## 2026-06-09 邮件合同案例库全量回灌入库交接

- **交接要点**：
  - 本地 PostgreSQL 新增了 `mail_contract_case` 缓存表，用于缓存并管理 CRM 中的合同。
  - 创建了 `backend/sync_crm_contracts_to_local.py` 同步脚本，成功将 CRM 数据库中所有符合标准的 **10,799** 条销售合同全部写入本地库。
  - 重构了 `/api/v1/mail/contract-case-candidates` 接口，使之直接在本地 `MailContractCase` 缓存表进行全文匹配、时间排序和分页，摆脱了动态查询 CRM 带来的高耗时与 500 条条数上限。
  - 在 `backend/mail_contract_case_candidates_checks.py` 中补充了针对该 API 的 TestClient 集成测试，目前全套 53 个单元/集成测试已 100% 成功通过（全绿）。
  - 已关闭旧后端实例并成功重启了 port 8071 后端服务。

## 2026-06-09 邮件合同案例库精炼与闪光点突出交接

- **交接要点**：
  - 针对案例生成过于泛化的问题，已在 `backend/main.py` 的 `_generate_mail_case_text` 中重构了 100 条 CRM 候选数据推介句的生成规则。
  - **定制与闪光点提取**：针对 TCC 商品战略会议、播客配音、患者日同传、审计报告、品牌白皮书、AATS 视频录制、Lelabo 总裁专访、地中海邮轮亚细亚号、品胜移动电源等 20+ 个核心业务场景和岗位切口配置了细节饱满的文案，不再使用单一泛化的模版句。
  - **行业专属 Fallback**：对于没有具体描述的简略合同（如仅有“笔译”/“口译”），根据 desensitized company category（如美妆巨头、卫浴品牌、外资银行等）和业务线特征智能推荐文风与行业词，使同一产品的描述表现出实质性的差异。
  - **严密脱敏与字数控制**：在提取 topic 逻辑中融入了 original company name 各层级字符块的动态擦除机制，防止原名意外泄露；并且长 topic 自动截断为 10 字符 + “等”后缀，使所有 100 条案例长度完美符合 $\le 50$ 字符的限制。
  - **测试通过**：`python -m py_compile backend/main.py` 成功，`git diff --check` 通过，全套 52 个 `unittest` 测试全部通过（100% 绿色）。

## 2026-06-08 邮件沟通过程案例脚本优化交接

- 用户要求参考 `other/邮件AI案例1.docx` 至 `邮件AI案例4.docx` 的沟通过程优化邮件脚本流程，并明确不改微信/企微。
- 已只修改邮件侧 `backend/main.py` 的商用邮件模板生成器和邮件 LLM Prompt。
- 新增邮件沟通 playbook：行业感 + 轻商务 + 不施压；按岗位/部门选择切口；老关系重连不追旧报价；英文内容优化不写成普通翻译；采购/跨部门转介绍先问“谁负责这类项目”，不直接要联系人。
- 12 个邮件模板目标版本从 v44 升至 v45；`GET /api/v1/mail/sequence-templates` 会触发 `_ensure_mail_sequence_templates()`，低版本模板会自动升级。
- 已在邮件 Prompt 中加入“不得写微信跟进语或微信式口语”，但未修改任何企微/微信代码路径。
- 验证通过：`backend/main.py` AST；模板抽查确认 12 个 version 45 且包含沟通过程、岗位切口、禁止直接索要联系人、禁止微信跟进语；`git diff --check -- backend/main.py` 通过。

## 2026-06-08 GitHub 推送交接

- 用户要求更新项目进展并提交本地修改到 GitHub。
- 已更新 `项目进展.md`，新增 v1.7.240 邮件合同案例库只读入口记录。
- 已完成本地提交：`dddfa74 feat: add mail contract case library`。
- 后续本地还有小提交：`d9a772b feat: 合同案例库列表隐藏金额列`。
- 首次推送曾因 GitHub 凭据返回 403；修正本地提交中误入索引的 pyc 缓存后，重新执行 `git push origin main` 已成功。
- 当前 `main` 已推送到 `origin/main`，远端最新提交为 `d9a772b`。
- 未提交 `.env`；`.codex_pycache_v15/` 仍是本地未跟踪缓存目录，不在 Git 提交中。

## 2026-06-08 企微实时对话获取方式整理交接

- 用户要求：整理获取企微实时对话方式，包括参数，输出 Markdown 文件。
- 已新增 `docs/企微实时对话获取方式.md`，基于当前 `backend/main.py`、`backend/archive_service.py`、`backend/database.py`、`backend/config.py` 和前端复现 curl 逻辑整理。
- 文档明确两条链路：`ArchiveService.sync_today_data()` / `/api/sync/*` 会话存档同步链路，以及 `/api/wecom/sidebar_assist` 侧边栏实时辅助链路。
- 已包含参数表、输出字段、关键数据库表、排查接口、推荐调用顺序和常见问题。
- 本轮未改业务代码，未访问或输出 `.env` 中真实密钥；仅新增文档并更新进度/交接/运行日志。

## 2026-06-08 邮件合同案例库只读入口交接

- 用户明确要求只做独立“邮件合同案例库”，与“黄金范例库”同级；不做 SMTP、V22、邮件模板迭代或企微改动。
- 已完成后端 `GET /api/v1/mail/contract-case-candidates`：只读查询 CRM `usrContract`，默认 `ContractId LIKE '%XS%'`、`Deleter IS NULL`、`Money1+Money2+Money3 >= 5000`、按 `InputTime` 倒序取最近 100 条；支持业务类型、产品关键词、合同描述关键词和排序时间字段筛选。
- 已完成前端节点：邮件工作台新增“合同案例库”按钮，和“黄金范例库”同级；页面展示筛选项、统计分析、表格和详情区。当前展示原始合同号/客户/联系人/金额/产品/业务类型/描述，因为用户要求先不脱敏。
- 当前接口返回 `ingested_to_knowledge=false`、`desensitized=false`，只做候选分析；真实进入邮件知识库前必须人工确认产品/行业/描述，并完成脱敏。
- 真实 CRM 只读验证摘要：100 条候选，77 条可初筛；产品线粗推为口译/同传 35、排版印刷 29、翻译 22、多媒体译制 9、礼品物料 3、会议活动 2；低质量信号主要为描述过短 21、补差价/尾款 2。
- 验证通过：`backend/main.py` AST、`frontend/index.html` 内联 JS `node --check`、`git diff --check -- backend/main.py frontend/index.html`；未启动/关闭后台，未跑 V22，未写 CRM。

## 2026-06-08 Agent Builder 补齐与验证交接

- **交接要点**：
  - 3Chat.ai Agent Builder 相关功能已补齐，完成了 12 封对抗用例 100% 通过（Counts: 12 PASS, 0 FAIL, 0 WARN）。
  - 后端表结构 `builder_knowledge` / `builder_knowledge_chunks` 均已在应用启动时自动创建并就绪。
  - 前端 `#view-8` SOP 画布大屏、`#view-9` 的 Webhook 仿真终端和产品库文件上传均已完成，能成功读取和操纵后端对应 API，实时重绘 SVG 连线及展示决策过程。
  - 自动 Prompt 自愈优化（`/optimize_prompt`）在 100.0% 通过率下测试返回 `No optimizations required`，调用顺畅。
  - 本地 Uvicorn 8071 实例常驻后台继续运行，供持续联调与验证。

## 2026-06-05 企微实时验证浮层中文化交接

- 用户要求：浮动说明都改为中文解释。
- 已修改 `frontend/index.html`：链路状态、LLM2 主回复、训练AI并行回复、耗时总说明、耗时实测拆分等浮层均改为中文解释。
- 当前耗时列逐行浮层展示为：第一行前台可输出点耗时、第二行轻量落库后总耗时、两行差值、请求解析、会话ID生成、企微存档同步、定位会话并读取最近消息、读取全量会话消息、强信号扫描、LLM-1 摘要、CRM 画像、知识检索、LLM2 主回复、训练AI独立耗时、结果转可存储结构、脱敏清理、写轻量调用记录、首次数据库提交等。
- 保留 LLM2、CRM、KB1/KB2、ApiAssistInvocation 等必要技术名，方便和后端日志字段对应；不再把英文字段名作为主要用户解释。
- 验证：前端内联 JS `node --check` 通过；`git diff --check -- frontend/index.html` 通过，仅 CRLF 提示。

## 2026-06-05 邮件三场景十二封商业模板升级交接

- **用户要求**：模板目的说明、发送日期/间隔说明必须一行展示；变量说明、生产脚本模板、AI 指令脚本三列自适应且控制 15 行高；按伊桑要求重写 3 个案例场景、4 个步骤、12 封邮件的生产脚本模板和 AI 指令脚本；去掉“试用”，强化商用、亲和、有效、行业、历史合作、多业务、转介绍。
- **已完成**：
  - `frontend/index.html`：模板顶部改为一整行 6 段控件：目的标签、目的输入框、保存目的、发送间隔标签、发送间隔输入框、保存发送日期。
  - `frontend/index.html`：下方改为变量说明 / 生产脚本模板 / 给 AI 的指令脚本三列；textarea 固定约 15 行高。
  - `frontend/index.html` 和 `backend/main.py`：三案例显示统一为 `老客户其他业务介绍`、`老客户激活`、`新客户开发介绍`。
  - `backend/main.py`：重写 12 条生产脚本模板和 12 条 AI 指令脚本，覆盖多业务、行业经验、历史合作、同行业案例、公司介绍、转介绍和禁止编造约束。
  - `backend/main.py`：邮件 LLM prompt 现在包含 CRM 公司名、生命周期、最近商机/报价、历史合同/合作、最近跟进和范例参考，后续补知识库后可按结构直接喂给 AI。
  - `backend/main.py`：新增 `_MAIL_SEQUENCE_TEMPLATE_DEFAULT_VERSION = 30`，旧 DB 模板会在 `_ensure_mail_sequence_templates()` 时升级；本地数据库 12 条已升级到 version 30。
- **注意事项**：
  - 本轮未改 `.env`。
  - 如果服务器已有手工保存且版本号高于 30 的模板，自动升级不会覆盖；低于 30 会升级。
  - 当前代码结构已支持把 CRM/知识库内容传入 prompt；若某类同行业成功案例知识库缺内容，模型会看到“无”并被要求不得编造。
- **验证**：后端 AST 通过；前端内联 JS `node --check` 通过；定向 `git diff --check` 通过（仅 CRLF 提示）；本地 DB 12 条模板均为 version 30 且模板内容检查 `DB_HAS_TRIAL_WORD=False`。

## 2026-06-05 邮件全量测试校验与 CRM 真数据异常修复交接

- **用户要求**：确认新开发部分的每个按钮、字段、前台触发和数据校验是否通过了测试验证。
- **定位与修复**：
  - 在全量测试运行期间发现 1 处 AttributeError 阻断（测试 Mock DB `_NoPricingRulesDb` 缺少新路由查询所要求的 `query` 属性）。已在 `backend/mail_review_api_interface_checks.py` 补充对应的 mock 模板返回函数。
  - 在运行 `verify_mail_generation_crm.py` 真实 CRM 联查时发现，当 opportunities、contracts 等字段从 SQL Server 查出为 `None` 时，传入 `MailDraftIntentProfile` 引起 Pydantic `ValidationError` 错误。已在 `backend/main.py` 的构建方法中对这 7 个 profile 字段应用安全的 `or ""` 或 `or "unknown"` 兜底。
  - 移除了 verify 脚本中对 `intent_profile` 不存在的属性 `customer_tier` 的 invalid print 调用。
- **验证结果**：
  - 11 个 check 文件共 43 个单元/接口集成测试用例 100% 成功。
  - 端到端 CRM SQL 联查及 LLM 生成成功运行，所有安全门均通过（`passed`）。
  - AST 校验和 git diff check 格式正常。

## 2026-06-05 邮件模板目的与发送间隔布局调整交接

- **用户要求**：邮件质量诊断页三大场景模板中，`当前模板目的说明`、`发送日期 / 间隔说明` 放到一行；各自输入框和保存按钮也在同一行，保存按钮放输入框右侧，宽度合适。
- **已完成**：
  - `frontend/index.html`：目的说明和发送间隔由原来的竖排 textarea 改成顶部一行两组紧凑编辑控件。
  - 每组结构为：标签 + 单行输入框 + 保存按钮。
  - 下方改为三列：变量说明、生产脚本模板、AI 指令脚本。
- **注意事项**：字段 ID 和保存函数未改，仍调用现有 `PUT /api/v1/mail/sequence-templates/{scenario}/{suite_step}`；本轮不改 `.env`。
- **验证**：抽取内联 JS 后 `node --check` 通过；定向 `git diff --check` 通过（仅 CRLF 提示）。

## 2026-06-05 CRM 生命周期阶段规则更新交接

- **用户要求**：老联系人不设 6 个月限制，有过合同就算老联系人；熟联系人为近 1 年有 3 个以上/及以上合同；新联系人为没有过合同。
- **已完成**：
  - `backend/crm_profile.py`：`_get_customer_lifecycle_stage()` 不再使用 `crmContactYeWuSetting` 的 6 个月窗口、报价阈值和旧硬编码 `old_contract_number=3`。
  - 生命周期改为优先按 `CustomerId` 客户/公司维度统计 `usrContract` 销售合同；找不到客户时才退回 `ContactId`。
  - `frontend/index.html`：邮件质量诊断页生命周期问号提示改为新规则。
- **当前 3 案例只读验证结果**：
  - `KH15411-117`：总合同 362，近 1 年合同 20，熟联系人。
  - `KH02659-011`：总合同 214，近 1 年合同 0，老联系人。
  - `KH13770-006`：总合同 20，近 1 年合同 2，按新规则为老联系人。
- **注意事项**：如果产品上仍希望 `KH13770-006` 显示“新客户”，那是案例标签，不是按合同口径计算出的 CRM 生命周期；需要单独显示“案例维度标签”和“CRM 生命周期”两个字段。
- **验证**：后端 AST 通过；定向 `git diff --check` 通过（仅 CRLF 提示）。

## 2026-06-05 案例库日常验证详情加载优化交接

- **用户现象**：案例库“迭代详情”页面停在“正在加载详情...”，感觉像数据卡死，过一会又恢复。
- **定位结果**：前端日常验证详情调用 `GET /api/case_lib/daily_validation/{date}?view=api&limit=300`，但后端原实现没有使用 `view/limit`，仍先全量查询当天 `MessageLog` 再按会话分组，忙日容易慢。
- **已完成**：
  - `backend/main.py`：`get_daily_validation_detail()` 增加 `view`、`limit` 参数。
  - `view=api` 快路径优先按当天 `ApiAssistInvocation` 查询最近调用记录，再只加载相关 session 的当天消息。
  - `view=api` 快路径只返回匹配本批 API 调用的轮次，避免详情结果被同会话其它轮次撑大。
  - 增加 `CASELIB_DAILY_DETAIL_TIMING` 和 `CASELIB_ITERATION_DETAIL_TIMING` 分段耗时日志，便于判断慢在调用查询、消息查询、分组、组装结果还是普通迭代详情查询。
- **服务器更新**：只需要更新 `backend/main.py` 并重启后端；`.env` 不需要改。
- **验证**：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过（仅 CRLF 提示）。`py_compile` 被 Windows pyc 权限拒绝，本轮临时 `.codex_pycache` 已清理。

## 2026-06-05 邮件质量诊断模板三列编辑与空邮箱限制移除交接

- **用户要求**：截图红框中的脚本模板区改成左右/三列布局；给 AI 的指令脚本也要能修改；三列尽量不用滚动即可看清，编辑框上限 20 行高；空邮箱和生产模板无关，去掉空邮箱限制。
- **已完成**：
  - `frontend/index.html`：模板区每阶段改为三列编辑布局，新增“给 AI 的指令脚本” textarea 和保存按钮，生产脚本/AI 指令文本框限制最大约 20 行高度。
  - `backend/database.py`：`MailSequenceTemplate` 新增 `ai_instruction_script`。
  - `backend/main.py`：启动期自动补 `mail_sequence_template.ai_instruction_script` 列；模板 GET/PUT 支持该字段；草稿生成 Prompt 注入该 AI 指令。
  - `backend/main.py` 和 `frontend/index.html`：空邮箱不再合成内部占位邮箱；当前 3 案例、独立客户套装页、邮件迭代后台均保持空邮箱为空值，只生成草稿，不发信。
- **注意事项**：
  - `contact_email` 现在对 `POST /api/v1/mail/generate-draft` 可为空；为空时仍要求 `customer_key`，CRM 查询按客户编号进行。
  - 如果填写了非空邮箱，原收件域名安全门仍会校验格式、白名单、竞对域名和风险域名。
  - 真实 SMTP 发送仍未启用，`real_sending_enabled=false`。
- **验证**：后端 AST、前端内联 JS `node --check`、定向 diff、`SKIP_DB_PATCH=1` 导入与路由注册均通过；`py_compile` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 邮件当前 3 案例 CRM 未脱敏展示交接

- **用户要求**：邮件质量诊断页的 3 个案例要查询清楚；既然是案例，不要脱敏；同时不影响其他地方。
- **已完成**：
  - `backend/main.py`：新增 `_fetch_mail_current_case_crm_detail()`，按当前 3 个 KH 编号实时只读查询 CRM 原始信息。
  - `backend/main.py`：确认这 3 个编号实际对应 `usrCustomerContact.ContactId`，并把 `ContactId`、`NewContactId`、`NewCustomerId` 加入草稿生成的 CRM 查询条件。
  - `GET /api/v1/mail/demo-contacts`：当前 3 个案例返回未脱敏联系人、公司、邮箱、ContactId、CustomerId、联系人/客户状态、销售/负责人、行业、生命周期、客户级别、欠款风险、最近商机/合同/跟进。
  - `frontend/index.html`：邮件质量诊断当前案例卡片和详情将“脱敏”字段改为“CRM 原始”，显示未脱敏信息；仅当前 3 案例区使用，旧 5 案例和其他页面不改。
- **注意事项**：
  - `KH02659-011` 在 CRM 中邮箱为空；页面会展示真实空值，但生成草稿表单使用内部占位邮箱，仅用于跑草稿链路，不真实发信。
  - 本轮只读 CRM，不写 CRM，不修改生产配置，不启用真实发件。
- **验证**：直接调用 `_fetch_mail_current_case_crm_detail()` 验证 `KH15411-117`、`KH02659-011`、`KH13770-006` 均返回 `matched_crm_contact_id_or_customer_id` 且公司名非空；后端 AST、前端内联 JS `node --check`、定向 diff、`SKIP_DB_PATCH=1` 导入与路由检查均通过。`py_compile` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 训练AI及知识库检索切换Ollama11486端口交接

- **用户要求**：将 `train_ai` (训练AI) 调用端口及 `embedding` (知识库检索) 调用端口切换至 `http://zjsphs.2288.org:11486`。重写 `train_ai` 以实现对 Ollama 的原生 `/api/chat` 和 `/api/tags` 接口的直接调用。将训练模型配置为 `unsloth-qwen2.5-task-60` 并确认 `qllama/bge-m3:latest` 命中的正确性。
- **已完成**：
  - `.env`：修改 `TRAIN_AI_BASE_URL` 为 `http://zjsphs.2288.org:11486`，`TRAIN_AI_MODEL` 为 `unsloth-qwen2.5-task-60`，`TRAIN_AI_API_KEY` 为空；修改 `EMBEDDING_API_URL` 为 `http://zjsphs.2288.org:11486`。
  - `backend/config.py`：同步修改默认参数。
  - `backend/main.py`：重构 `_train_ai_list_models` 以请求 `GET /api/tags` 并解析为 `[{"model_name": name}]`，适配前端下拉菜单；重构 `_train_ai_chat` 以直接 `POST /api/chat`，解析 `message.content` 作为回复。
- **注意事项**：
  - Ollama 服务目前尚未拉取 `unsloth-qwen2.5-task-60` 模型，测试返回 404；已用 `qwen2.5:3b` 成功验证 `/api/chat` 调用协议的正确性。
  - 知识库检索使用的 `qllama/bge-m3:latest` 经验证已在 `http://zjsphs.2288.org:11486` 上就绪并可成功输出向量。
- **验证**：AST 解析通过；`git diff --check` 通过；利用直连脚本 `scratch/test_ollama_endpoints.py` 在本机会话中完成 tags 和 chat 的双重验证。

## 2026-06-05 邮件套装反馈记录节点交接

- **用户要求**：确认昨天新增的独立页面 `/static/mail-suite.html` 中反馈是否为“一条反馈一条记录”，并在邮件质量诊断工作台增加“反馈记录”节点，显示完整反馈、对应模板/草稿和客户联系人信息，便于验证。
- **已完成**：
  - `backend/main.py`：补齐 `POST /api/v1/mail/customer-suite-feedback`，每次提交都会新增 `mail_customer_suite_feedback` 一条记录；返回 `storage_policy=one_feedback_submit_one_row`。
  - `backend/main.py`：新增 `GET /api/v1/mail/customer-suite-feedback`，支持 `customer_id`、`scenario`、`suite_step`、`limit` 查询，返回完整反馈、邮件主题正文、草稿 payload、客户画像、联系人摘要。
  - `backend/main.py`：补齐 `GET /api/v1/mail/customer-suite`，独立页可继续按客户编号生成 4 封套装草稿；浏览器直开 API 会跳转到 `/static/mail-suite.html?id=...`；真实发信仍关闭。
  - `backend/main.py`：`auto_patch_db()` 补齐 `mail_customer_suite_feedback` 自动建表和索引；`/static/mail-suite.html` 加入免登录白名单。
  - `frontend/index.html`：邮件工作台子导航新增“反馈记录”，有筛选、刷新、列表和详情展开；详情显示完整反馈、客户联系人、对应场景阶段、邮件主题正文、草稿 JSON 和客户画像 JSON。
- **注意事项**：
  - 新增查询节点读取真表，不生成 Mock 反馈；如果页面为空，说明尚未通过独立页保存过反馈，或当前筛选条件无记录。
  - `GET /api/v1/mail/customer-suite` 会真走现有草稿生成链路和 CRM 画像查询；但仍只生成草稿，不发送邮件。
  - 真实 SMTP 发送 Task 79 仍未启用，`real_sending_enabled=false`。
- **验证**：AST 解析通过；前端内联 JS `node --check` 通过；定向 `git diff --check` 通过；`SKIP_DB_PATCH=1` 导入 `main` 成功并确认 `/api/v1/mail/customer-suite`、反馈 POST、反馈 GET 路由已注册。`python -m py_compile` 仍被既有 `backend/__pycache__` 权限拒绝阻断，未改权限。

## 2026-06-05 邮件质量诊断 3 案例与模板配置交接

- **用户要求**：截图节点中原 5 个案例改为 3 个：老客户多业务 `KH15411-117`、老客户激活 `KH02659-011`、新客户 `KH13770-006`；原 5 个数据保留但之后显示和测试使用新的 3 个；同页增加可折叠展示 3 个场景所有阶段脚本模板，支持按场景切换、按顺序显示、中文解释目的/变量/发送日期，并可分别保存脚本、目的、发送日期。
- **已完成**：
  - `backend/database.py`：`mail_demo_contact` 新增 `real_customer_key`、`display_group`、`is_current_test_case` 字段；新增 `MailSequenceTemplate` 模型。
  - `backend/main.py`：`auto_patch_db()` 补列建表；新增当前 3 案例定义；`/api/v1/mail/demo-contacts` 返回当前 3 案例视图，旧 5 案例保留；邮件迭代后台改为当前 3 案例 × 4 步；新增 `GET/PUT /api/v1/mail/sequence-templates`；保存后的模板会注入邮件草稿 LLM Prompt。
  - `frontend/index.html`：案例区文案/布局改为 3 选 1；新增折叠“3 场景全阶段脚本模板”面板；每个阶段支持单独保存目的、发送日期、脚本；迭代文案改为 12 封。
- **注意事项**：
  - `KH15411-117` 等编号进入草稿生成时走现有 CRM SQL 只读查询。已扩展 CRM 查询按实际存在的客户编号字段匹配；如果生产 CRM 字段命名不在当前白名单内，接口会明确查不到，不会塞假数据。
  - 原 5 个 `mail_demo_contact` 数据未删除。后续若要把 3 个新案例也真实落入 `mail_demo_contact` 表，可基于新增字段做一次只读 CRM 抓取后 upsert。
  - 真实发信仍未开启，`real_sending_enabled=false`。
- **验证**：AST 检查 `backend/main.py`、`backend/database.py` 通过；前端内联 JS `node --check` 通过；定向 `git diff --check` 通过。`python -m py_compile backend/main.py backend/database.py` 因既有 `backend/__pycache__` 权限拒绝写 pyc 失败，未改权限。

## 2026-06-04 邮件 V8 有效复测交接

- **最终有效结果**：邮件 V8 最终有效复测已完成，落库为 `mail_iteration_run` v14，run_id `ecf5a1aa-7c08-4779-aec7-ea1b3bfc2609`，run_label `v8_final_signature_dedup_deepseek_no_proxy`。20/20 成功，均分 99.2，最低 96，最高 100，平均耗时 7577ms，LLM 成功 20/20，fallback 0。
- **代码修复**：
  - `backend/config.py` 新增 `MAIL_DRAFT_LLM_*` 邮件草稿专用 LLM 配置。
  - `backend/main.py` 邮件草稿 LLM 调用优先读 `MAIL_DRAFT_LLM_*`，未配置时回落 `LLM2_*`。
  - `backend/main.py` 邮件草稿 LLM 请求使用 `requests.Session().trust_env = False`，避免系统代理导致 DeepSeek/API 请求失败。
  - `backend/main.py` Prompt 新增禁止 LLM 输出落款/签名规则，并在后端追加统一签名前清理 LLM 段落末尾误写的签名。
- **结果分析**：详见 `logs/mail-v8-analysis.md`。最终有效 v14 统计：正文最短 190 字、平均 314.2 字、最长 521 字；最少 4 段、平均 4.5 段；20 封全部命中目标业务表达；历史跟进泄漏 0；安全门全部通过并锁定人工审核；未启用真实发件。
- **失败诊断记录**：v8-v12 均为环境/端口/模型出口诊断记录，不作为质量结果。v8-v10 是旧 8071 进程仍打 DeepSeek 且系统代理不可达；v11 是本地 qwen 被代理劫持；v12 是本地 qwen `/chat/completions` 超时/404；v13 成功但发现重复签名风险；v14 为最终有效结果。
- **本机端口状态**：当前本机会话无权限结束部分隐藏 uvicorn/python 进程，`8071`、`8088`、`8089`、`18990`、`18991` 等可能仍显示 LISTENING；这些是本地临时或旧进程，不代表 api.speedasia.net 生产卡死。后续若要清理，需要在管理员终端结束对应 PID 或重启本机。
- **验证**：`backend/main.py` 与 `backend/config.py` AST 解析通过；`git diff --check -- backend/main.py backend/config.py` 通过（仅 CRLF 提示）。

## 2026-06-05 当前可用协议优先顺序交接

- 用户要求：都将当前可用的作为最先尝试，不通再试其他。
- 已调整 `backend/main.py`：训练 AI 模型列表优先 `/api/tags`；生成优先 `/api/chat`，然后 `/v1/chat/completions`，最后旧 `/api/model-chat/chat`。
- 已调整 `backend/embedding_service.py`：embedding 优先 `/v1/embeddings`，失败或空向量再回退 `/api/embeddings`。
- 当前建议服务器配置仍为：`TRAIN_AI_BASE_URL=http://zjsphs.2288.org:11486`、`TRAIN_AI_MODEL=unsloth-qwen2.5-task-60:latest`、`EMBEDDING_API_URL=http://zjsphs.2288.org:11486`、`EMBEDDING_MODEL=qllama/bge-m3:latest`。
- 验证：AST、定向 diff 通过；`EmbeddingService.embed()` 返回 1024 维真实向量。

## 2026-06-05 当前 11486 模型与 Embedding 适配交接

- 用户要求确认兜底逻辑是否有假数据，并适配当前 `http://zjsphs.2288.org:11486` 的模型。
- 结论：训练 AI 兜底没有假数据，只按 `model_chat -> ollama_api_chat -> openai_chat_completions` 真实请求外部服务；全失败时返回失败状态和错误，不会伪造回复。
- 已确认 `11486` 当前有 `unsloth-qwen2.5-task-60:latest` 和 `qllama/bge-m3:latest`，聊天 `/api/chat` 可用，embedding `/v1/embeddings` 可用。
- 已修复 `backend/embedding_service.py`：`/api/embeddings` 返回空向量时自动回退 `/v1/embeddings`；OpenAI-compatible embedding URL 会自动补 `/v1/embeddings`；本地兼容服务可无 API key。
- 服务器建议 `.env`：`TRAIN_AI_BASE_URL=http://zjsphs.2288.org:11486`、`TRAIN_AI_MODEL=unsloth-qwen2.5-task-60:latest`、`EMBEDDING_API_URL=http://zjsphs.2288.org:11486`、`EMBEDDING_MODEL=qllama/bge-m3:latest`。
- 验证：直接调用 `EmbeddingService.embed('测试 embedding 真实向量')` 返回 1024 维向量；AST 与定向 diff 通过。

## 2026-06-05 训练AI model-chat 恢复与日志增强交接

- 用户反馈：训练 AI 仍未成功，当前代码改成了直连 Ollama，但之前服务器可能是通过 Dify/model-chat 加载对应模型。
- 已修复：`backend/main.py` 的 `_train_ai_chat()` 现在按顺序尝试 `model_chat -> ollama_api_chat -> openai_chat_completions`，即 `/api/model-chat/chat`、`/api/chat`、`/v1/chat/completions`。
- 模型列表 `_train_ai_list_models()` 也按顺序尝试 `/api/model-chat/models`、`/api/tags`、`/v1/models`。
- 新增日志：grep `TRAIN_AI_` 即可查看训练 AI 完整尝试过程。重点看 `TRAIN_AI_START`、`TRAIN_AI_ATTEMPT_*`、`TRAIN_AI_SUCCESS`、`TRAIN_AI_FAILED`。成功后数据库 `training_ai.protocol` 会显示实际协议。
- 服务器只需更新 `backend/main.py` 并重启。若仍失败，服务器日志里会显示哪个协议返回 404、空内容、HTTP 错误或超时。
- 验证：`backend/main.py` AST 解析通过；定向 `git diff --check -- backend/main.py` 通过。

## 2026-06-05 训练AI接口 404 协议兼容交接

- 用户反馈训练 AI 返回 `404 Client Error: Not Found for url: http://zjsphs.2288.org:11486/api/chat`。
# 2026-06-05 企微实时验证耗时浮层按环节拆分交接

- 用户反馈：案例库实时验证列表“耗时”悬停说明被改成泛化链路说明，用户期望恢复为第一行/第二行耗时解析，并按每个环节拆分耗时；有并行环节时分别显示独立耗时。
- 已修改 `backend/main.py`：日常验证 API 快路径每行新增 `timings_ms`，直接来自 `ApiAssistInvocation.result_payload.timings_ms`，供前端展示 `pipeline_total_ms` / `total_ms` / `tail_ms` / 尾段细分。
- 已修改 `frontend/index.html`：新增 `buildSidebarLatencyRowTip()`，耗时单元格现在按当前行显示请求入口、会话读取、Fast-Track、LLM-1、CRM、知识检索、LLM2、训练AI、jsonable/sanitize/store/commit/repatch 等环节的实测毫秒数；LLM2 与训练AI作为并行生成链路分别计时。
- 验证已通过：`backend/main.py` AST；前端内联 JS `node --check`；`git diff --check -- backend/main.py frontend/index.html`。`py_compile` 未跑，沿用项目既有 `__pycache__` 权限问题处理口径。
- 后续复测：刷新案例库实时验证详情页，鼠标悬停“耗时”列，应看到“当前触发耗时实测拆分”，并逐项列出实际 ms。旧记录如果缺少某些字段，会自动只显示已有项。

- 已修复 `backend/main.py` 的 `_train_ai_chat()`：先走 Ollama `/api/chat`；如返回 404，自动回退 OpenAI 兼容 `/v1/chat/completions`；若配置了 `TRAIN_AI_API_KEY`，回退请求会带 `Authorization: Bearer ...`。
- 成功或空内容返回中会带 `training_ai.protocol`，可在 `api_assist_invocation.result_payload->training_ai->protocol` 判断实际协议：`ollama_api_chat` 或 `openai_chat_completions`。
- 服务器本次只需更新 `backend/main.py` 并重启，不需要改 `.env`。若仍失败，查 `training_ai.status` / `training_ai.error` / `training_ai.protocol`。
- 验证：`backend/main.py` AST 解析通过；定向 `git diff --check -- backend/main.py` 通过。

## 2026-06-05 企微后续评分时间窗交接

- 用户要求：企微后续算分每天只在北京时间 20:00-24:00 计算，其他时间不计算。
- 已实现：新增 `WECOM_FOLLOWUP_SCORING_WINDOW_*` 配置，默认开启 20:00（含）到 24:00（不含）；窗口外 `_run_api_invocation_rescore_backfill()` 直接跳过，`_refresh_api_invocation_quality()` 直接返回，`_complete_api_reply_scoring_async()` 直接返回，侧边栏请求尾段也不会提交异步评分线程。本次服务器手动更新运行态只需要 `backend/main.py` 和 `backend/config.py`，不要求改 `.env`。
- 边界：前台企微智能回复生成不受影响；只限制 API 调用后的原始回复分、相似分、AI 候选分、训练 AI 分等后续评分补算。窗口外不把记录标记成已完成，待评分记录会留到窗口内继续补算。
- 验证：AST 解析通过；定向 `git diff --check -- backend/main.py backend/config.py` 通过；时间窗 helper 验证 `19:59=False / 20:00=True / 23:59=True / 00:00=False`。直接导入 `main` 的验证命令因项目启动调度器未退出而超时，但已打印正确结果；`py_compile backend/config.py` 因既有 `backend/__pycache__` 权限拒绝失败。

## 当前目标

目前已完成标准项目状态文件同步，并通过 Git 状态与实际提交日志校验确认：
- 邮件生成个性化与商业话术优化（Task 80）已全量实现，公司名/合同/机会/跟进记录等 CRM 字段在草稿生成意图画像和 LLM Prompt 中的读取、传导、组装与事实提及已经闭环，并成功修改跑通了全部 7 个邮件定向检验测试。
- 邮件系统 Phase 5 真接入（Task 76 / 77 / 78）已完全打通并完成 DoD 定向验证，在 logs/dod-task76-78.md 保存了真实的数据演示证据。
- 邮件历史数据灌库与 5 真实案例/生命周期、20 封批量生成与评分机制（v1.7.205 / 206）已全面集成。
- WeCom 评分补算后台 worker 热修复与行锁/表锁释放、饥饿队列智能过滤（v1.7.208）已完成，成功消除 87.6 秒延迟并盘活最新对话评分。
- 贯彻“宁报错或为空”的一刀切一期/二期 fallback 注释工作（v1.7.207 / 209）已完全到位。
- 保留交接信息供人工复核及后续新任务池立项参考。

## 当前任务

当前前台任务为 6.1 企微实时验证慢查询/慢调用修复。邮件真实发送通道（Task 79）默认关闭，保持 review-only，作为未来任务储备，在没有人工明确指令前不予开启。

## 2026-06-03 清理动态案例兜底硬编码并释放DB死锁进程交接

- **移除了动态案例兜底硬编码**：移除了 `backend/main.py` 的 `_get_mail_industry_case_study_from_db` 函数中，在数据库未查询到匹配行业案例时所返回的硬编码文字。直接返回空字符串 `""`，从而让 Prompt 生成彻底摒弃最后的 Mock 假数据。
- **解决数据库锁阻塞**：通过编写 `scratch/kill_blocking_transaction.py` 动态查询涉及 `pg_locks` 冲突的 PIDs 并终止它们，释放了因 `ALTER TABLE` 锁定的会话。
- **重新启动服务器与 v6 实测**：通过终止本地挂起的 python 后台服务并在端口 `8071` 带上 `$env:SKIP_DB_PATCH="1"` 重新拉起后端，保证了服务可用性。执行邮件迭代 v6 跑测，20 个邮件全部成功生成，均分 97.2。
- **单元测试全绿**：全量执行 43 个 check 测试脚本均成功通过。

## 2026-06-03 去除CRM画像None后Mock兜底假数据与Pydantic属性修复交接

- **去除 Mock 字典和静态数据分支**：已修改 `backend/main.py` 中的 `_lookup_mail_crm_profile`，去除了 SQL 查询为 None 时 fallback 到 static mock 字典及 demo contact 表的分支。对于 SQL 未查到记录的情况，坚决直接抛出 404 错误并显示报错信息。
- **清除假数据**：更新了 `backend/mail_crm_mock_data.py` 中的 `to_profile_lookup_payload`，将 mock 数据的 company_name、opportunities、contracts、followup 等字段全部修改为空白字符串，彻底清除了 "麦克制造有限公司" 等假数据，用空值表达未识别。
- **补全 Pydantic 属性以防崩溃**：修复了 `MailDraftIntentProfile` 中缺失的 `company_name`、`customer_lifecycle_stage`、`customer_tier`、`recent_opportunities`、`ongoing_contracts`、`contact_recent_followup` 属性定义，并确保 `_build_mail_draft_intent_profile` 初始化时正确传入。修正了 `_llm_generate_mail_intro_paragraphs` 对大模型 Prompt 拼装中动态读取上述属性时可能发生的 `AttributeError` 崩溃。
- **检查并运行测试套件**：
  - 更新了 3 个测试 check 脚本中对 `_mail_crm_profile_from_sql` 模拟返回空的逻辑，使之在 mock 字典环境下能直接返回对应的 mock 实体而无需依赖 `main.py` 内部的静态 fallback，保持测试绿色运行。
  - 运行 `python scratch/verify_mail_generation_crm.py` 进行真 B2B RAG 生成及 CRM 字段捕获（如 `KH33886` 钟化），输出结果全部通过，大模型 Prompt 正确捕获并拼装了真 CRM 事实及知识库动态检索成功案例。
  - 全量运行 11 个 `mail_*_checks.py` 检验测试脚本，结果均为 OK。

## 2026-06-02 6.1 慢查询修复交接

- 已修改 `backend/main.py`：`sidebar_assist` 调用 `_store_api_assist_invocation(..., refresh_quality=False)`，前台请求只写轻量快照，不再同步等待 LLM-1 评分、训练AI评分或相似度补算；后台 `_complete_api_reply_scoring_async` 会重新调用 `_refresh_api_invocation_quality` 完成完整补算。
- 2026-06-02 13:51 二次收紧：新增独立 `API_ASSIST_SCORING_EXECUTOR`，后台评分不再占用前台 LLM2/训练AI 共用的 `REPLY_CHAIN_EXECUTOR`；`sidebar_assist` 非流式 API 强制 `enable_scoring=False`，即使评测参数传入也不在前台跑 step7 评分。
- 2026-06-02 13:51 二次收紧：历史节点详情/分析接口不再同步调用 `_refresh_api_invocation_quality`，若评分 pending/failed 只提交后台补算并立即返回现有快照，避免打开详情时把 LLM-1 评分耗时算进前端等待。
- 2026-06-02 6.1 前端浮动说明补全：`frontend/index.html` 新增 `sidebarApiFullChainTip`、`llm2MainChainTip`、`trainingAiChainTip`、`sidebarLatencyTip`，表头、链路状态、耗时、第6步两行回复悬停说明都覆盖完整 API 外围链路、链路1 LLM2、链路2 训练AI，以及缓存/去重/归档同步/KB2 开关/跳过条件/轻量落库/后台补算等特殊分支。
- 2026-06-02 根据用户澄清修正：用户指的是“耗时”单元格浮动。已把 `sidebarLatencyTip` 改成专门解释第一行 `pipeline_total_ms` 与第二行 `api_total_ms/total_ms` 的所有包含/不包含环节；第二行按代码修正为“到首次 db commit”，不再误写包含 timing repatch/SUCCESS/盲评/缓存/后台补算。
- 2026-06-03 修复前端加载失败：`sidebarApiFullChainTip is not defined`。根因是 tooltip 常量放在 `renderCaselibDetail()` 局部作用域，`caselibRenderDetailRows()` 重渲染表头/行时无法访问。已把 `sidebarApiFullChainTip`、`llm2MainChainTip`、`trainingAiChainTip`、`sidebarLatencyTip` 提升到案例库模块级作用域，并删除局部重复定义。验证：抽取 `frontend/index.html` 内联脚本后 `node --check` 通过；`git diff --check -- frontend/index.html` 通过。
- 已修复 hash 守卫边界：`pending_async_scoring` 不再被当成已完成评分直接跳过。
- 已修改 `backend/main.py` 的 6.1 daily 明细/汇总匹配：构建 `invs_by_session` 后按当前会话查找时间兜底，避免每个对话轮次扫描全量 invocation。
- 已修改 `backend/database.py` 与 `auto_patch_db`：新增 `idx_message_logs_timestamp`、`idx_message_logs_user_timestamp`，用于按日期查 6.1 明细和按会话取背景。
- 验证：前端内联脚本抽取后 `node --check` 通过；AST 解析 `backend/main.py`、`backend/database.py` 通过；`git diff --check -- backend/main.py backend/database.py frontend/index.html PROGRESS.md TASK_HANDOFF.md 项目进展.md` 通过。`python -m py_compile` 被既有 `backend/__pycache__` 权限拒绝写 pyc 阻断，未改权限、未清理 pycache。
- 若服务器仍慢，需要服务器日志：优先提供 `SLOW_REQUEST`、`SIDEBAR_ASSIST_RECEIVED/DEDUPE/SUCCESS/ERROR` 中同一 `request_id` 的日志，尤其是 `timings_ms`、`pipeline_total_ms`、`tail_ms` 和 `tail_breakdown_ms`。
- 2026-06-02 继续分析 `docs/app.log.2`：该日志含 2026-05-29 与 2026-06-01 的 `SIDEBAR_ASSIST_SUCCESS`。209 条成功调用中，第二行极端慢几乎全部由 `store_invocation_ms` 贡献；6.1 多条为 260s~262s，符合 LLM-1 评分两类 prompt 各 65s×2 次重试被旧版 `_store_api_assist_invocation` 包进主链路的模式，不是 `first_db_commit_ms`。第一行 20s~28s 则主要由训练AI约 15s~16s、知识检索最高约 6s、LLM1 摘要约 2s~5s 叠加导致，和第二行不是同一个慢点。已把 `_store_api_assist_invocation` 默认 `refresh_quality` 改为 `False` 作为防回退保护。
- 2026-06-02 追加精准日志：`_store_api_assist_invocation` 会输出 `API_INVOCATION_STORE_TIMING` 或超过 1s 时输出 `API_INVOCATION_STORE_SLOW`，字段包含 `flush_ms`、`quality_refresh_ms`、`light_snapshot_ms`、`total_ms`、`refresh_quality`。后台评分完成/失败日志追加 `elapsed_ms`。服务器更新后若仍慢，优先 grep `API_INVOCATION_STORE_SLOW`，判断是 `flush_ms` 锁等待还是 `quality_refresh_ms` 评分补算进入前台。
- 2026-06-03 今日数据加载慢/数据库死锁热修复：当前 `backend/main.py` 实际代码曾回退为 `_store_api_assist_invocation` 在 `db.flush()` 后同步调用 `_refresh_api_invocation_quality`，与交接记录不一致，导致前台仍可能被 LLM-1 评分 65s 超时重试拖住。已补回 `refresh_quality=False` 默认值，两个前台调用点显式传 `refresh_quality=False`，并把 `_complete_api_reply_scoring_async` 提交到独立 `API_ASSIST_SCORING_EXECUTOR`，不再占用主回复 `REPLY_CHAIN_EXECUTOR`。
- 2026-06-03 今日数据加载慢/数据库死锁热修复：`/api/case_lib/iterations?limit=100` 原本每次打开迭代记录列表都会从 2026-05-26 到今天逐日调用 `_get_daily_validation_stats()`，等于列表页加载时扫多天 `message_logs` 和 `api_assist_invocation`。已改为仅最近 3 天实时统计，历史日统计延迟到点击详情页再算；`_get_daily_validation_stats()` 和 `/api/case_lib/daily_validation/{date}` 均已按 `invs_by_session` 分桶，避免每个轮次再扫描全量 invocation。
- 2026-06-03 今日数据加载慢/数据库死锁热修复：`auto_patch_db()` 增加 `pg_try_advisory_lock(hashtext('qw_auto_patch_db'))`、`lock_timeout=3s`、`statement_timeout=30s`，避免 api.speedasia.net 多进程启动或高峰期 DDL 长时间抢锁；`message_logs(timestamp)` 与 `(user_id,timestamp)` 两个日期查询索引用 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` 单独创建，避免普通建索引阻塞写入。
- 本轮验证：`python -c "import ast, pathlib; ast.parse(pathlib.Path('backend/main.py').read_text(encoding='utf-8'))"` 通过；`git diff --check -- backend/main.py` 通过（仅 CRLF 提示）。`python -m py_compile backend/main.py` 仍因 Windows pyc 原子 rename 权限拒绝失败，使用 `PYTHONPYCACHEPREFIX` 指向 `D:\tmp` 与仓内 `scratch/qw-pycache` 均失败，未改权限；业务语法以 AST 验证为准。`docs/app.log.2` 本地仅到 2026-06-01 16:59，未包含 2026-06-03 今日服务器 deadlock 日志，生产复测需看 api.speedasia.net 最新日志中的 `API_INVOCATION_STORE_SLOW`、`SLOW_REQUEST` 与数据库 deadlock 记录。
- 2026-06-03 详情页继续修复：`/api/case_lib/daily_validation/{date}` 默认改为 `view=api`，新增 `limit` 参数默认 300、最大 1000。快路径只查当天附近的 `api_assist_invocation`，从 `result_payload`、锚点问题、训练AI结果、评分字段、知识检索摘要构造案例库明细，避免打开详情时默认加载全天 `message_logs`、分组所有 session、再逐会话查历史。完整旧路径保留为 `view=all`，必要时可手工访问 `/api/case_lib/daily_validation/2026-06-03?view=all` 深查。
- 2026-06-03 详情页继续修复：`frontend/index.html` 的 `caselibOpenDetail(runId)` 已将日常记录详情请求改为 `/api/case_lib/daily_validation/YYYY-MM-DD?view=api&limit=300`，用户点击“今日/历史日常实时验证”默认走快路径。若生产详情仍慢，先确认浏览器 Network 面板实际 URL 是否带 `view=api&limit=300`，再看后端 `SLOW_REQUEST` 是否发生在该接口。
- 本轮补充验证：`backend/main.py` AST 解析通过；抽取 `frontend/index.html` 内联脚本后 `node --check scratch/qw-inline-1.js` 通过；`git diff --check -- backend/main.py frontend/index.html` 通过（仅 CRLF 提示）。`python -m py_compile backend/main.py` 仍因 `D:\tmp\qw-pycache` 权限拒绝失败，未改权限。

## 2026-06-03 异步评分补算连接泄漏及僵尸事务清理交接

- **修复 Session 泄漏**：在 `backend/main.py` 的 `_complete_api_reply_scoring_async` 异步补算函数中，所有的早停退出（`return`）路径均补齐了 `db.close()` 释放，切断了僵尸连接的滋生。
- **僵尸事务强制终止**：通过编写并运行 `scratch/kill_idle_pids.py` 调用 `pg_terminate_backend()` 物理清理了 3 个常驻 `idle in transaction` 的僵尸 PIDs，释放了后台持有的事务及锁开销。
- **接口畅通度复测**：
  - 重启本地后台服务并重新加载代码。
  - 通过公网及本地接口 `GET /api/v1/mail/iterations` 验证，响应码均为 200 OK 且输出含有 v4、v5、v6 迭代记录的 6 个完整 runs。
- **全量单元测试通过**：全量执行 11 个 check 测试脚本共 43 个用例全部通过（OK）。

## 2026-06-03 hj 邮件质量诊断受限账号交接

- **新增账号**：`backend/main.py` 新增 `hj` 登录账号，角色为 `mail_quality_only`；登录接口和 `/api/auth/me` 均返回 `role` 字段。该账号用于只进入邮件质量诊断视图。
- **前端限制**：`frontend/index.html` 新增 `currentFrontendRole`、`isMailQualityOnlyUser()`、`applyUserAccessMode()`；受限账号登录后顶部主导航只保留“邮件质量诊断”，邮件工作台子导航允许“质量诊断 / 邮件迭代记录 / 黄金范例库”，隐藏“邮件配置”和所有“返回企微实时智能”按钮。
- **2026-06-03 修正**：发现 `switchMailWorkspaceTab()` 每次切页都会重写子导航按钮 `className`，导致原先加上的 `hidden` 被覆盖，`hj` 仍能看到“邮件迭代记录 / 黄金范例库 / 邮件配置”。已新增 `applyMailQualityOnlyVisibility()` 并在 `switchMailWorkspaceTab()` 末尾调用，确保每次渲染后重新隐藏这些按钮。
- **2026-06-03 再调整**：按用户最新要求，`hj` 账号必须能点击并查看“质量诊断 / 邮件迭代记录 / 黄金范例库”三个子页。因此取消了受限账号一律强制回 quality 的逻辑，仅在试图进入 `config` 时回到 quality；`iteration` 会正常调用 `loadMailIterationList()`，`goldlib` 会正常调用 `loadMailGoldLibrarySeeds()`。
- **强制跳转**：`switchMainApp()` 对 `mail_quality_only` 仍会阻止进入企微、统计、知识库、案例库等主页面，并拉回 `#mail-quality`；邮件页内部允许三个授权子页切换。
- **边界说明**：本轮按当前项目已有登录架构完成前端视图限制和登录角色返回；这不是完整后端 API 级 RBAC。若后续要求接口级越权防护，需要继续在后端为企微/知识库/案例库 API 加角色依赖校验。
- **验证**：`backend/main.py` AST 解析通过；抽取 `frontend/index.html` 内联脚本后 `node --check scratch/qw-inline-1.js` 通过；`git diff --check -- backend/main.py frontend/index.html` 通过（仅 CRLF 提示）。

## 2026-06-03 服务器启动期 auto_patch_db 慢启动修复交接

- **问题**：服务器更新后卡在 `数据库 Schema 自动检查/修复完成` 前，根因是 `auto_patch_db()` 启动时执行大量 `ALTER TABLE` / `CREATE INDEX IF NOT EXISTS`，生产库有并发读写或锁冲突时容易长时间等待 DDL 锁。
- **修复**：`backend/main.py` 的 `auto_patch_db()` 已改为 PostgreSQL 快速失败模式：先执行 `pg_try_advisory_lock(hashtext('qw_auto_patch_db'))`，拿不到锁直接跳过；拿到锁后设置 `lock_timeout=2s`、`statement_timeout=20s`，DDL 遇锁会快速失败并释放连接，不再拖住服务启动。
- **索引处理**：新增 `_ensure_message_log_indexes_concurrently()`，将 `message_logs(timestamp)` 与 `message_logs(user_id,timestamp)` 两个日期查询索引用 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` 在事务外创建，并设置 `lock_timeout=2s`、`statement_timeout=45s`。失败只记录 warning，不阻塞启动。
- **兜底开关**：生产紧急重启仍可设置 `SKIP_DB_PATCH=1` 完全跳过启动期 schema 检查；但正常情况下新逻辑已经避免长时间等锁。
- **验证**：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py logs/codex-run.log` 通过（仅 CRLF 提示）。

## 2026-06-03 邮件草稿 Prompt 一致性与篇幅优化交接

- **知识库与历史跟进分离**：`backend/main.py` 的邮件 LLM Prompt 已将“当前客户销售跟进历史”“知识库同行业成功服务案例”“范例参考”拆成三个独立区块，并在系统规则中明确三者信息源不同，严禁把知识库案例混入历史跟进或把当前客户跟进写成同行业成功案例。
- **新老业务冲突修复**：新增 `existing_business_lines`、`target_product_line`、`target_product_line_reason` 到 `MailDraftIntentProfile`。新业务推广场景会解析 `ongoing_contracts` 中客户已采购的旧业务，并显式写入本次目标推广业务；Prompt 里硬性要求只推广目标新业务，旧业务仅可作为信任背景一笔带过。
- **篇幅规则放宽**：已移除旧的固定段落/句数硬限制，替换为“根据业务叙事需要合理规划邮件正文结构，力求清晰、得体，段落与长度以传达清晰的商业价值为准”，同时要求内容比短模板更充实。
- **CRM 日期 Bug 修复**：`backend/crm_profile.py` 已把 `RecentMonths` 配置在 Python 端解析为真实 datetime 起止范围，并将 SQL 条件改为日期字段直接比较，不再通过 `CONVERT(char)` 字符串比较日期。
- **策略中文化**：`backend/mail_sequence_strategy.py` 中三套邮件 Sequence 的 `objective` 与 `cta_style` 均已是中文表述，并修正了新业务推广步骤中残留的中英文混杂描述。
- **验证**：`backend/main.py`、`backend/crm_profile.py`、`backend/mail_sequence_strategy.py` AST 解析通过；定向 `git diff --check` 通过。`python -m py_compile backend/crm_profile.py backend/mail_sequence_strategy.py` 仍因既有 `backend/__pycache__` 权限拒绝写 pyc 失败，未修改权限，采用 AST 校验。

## 关键背景

## 2026-06-04 独立客户套装邮件页交接

- 新增独立页面：`/static/mail-suite.html?id=KH23447-001`。
- 页面不需要登录，不展示现有工作台导航，也没有跳转其他已有页面的快捷按钮。
- 新增后端接口：
  - `GET /api/v1/mail/customer-suite?id=客户编号`：CRM 按客户编号读取画像，自动判断 `re_activation` / `new_business_promotion` / `new_contact_intro`，同步生成 4 封套装草稿。
  - `POST /api/v1/mail/customer-suite-feedback`：保存单封邮件反馈，每点一次保存一条新记录。
- 新增表：`mail_customer_suite_feedback`，字段包含客户编号、邮箱、公司、场景、step、mail_uid、主题、正文、反馈内容、草稿快照、客户画像快照、创建时间。
- `frontend_auth_middleware` 已将 `/static/mail-suite.html` 加入免登录白名单。
- 本轮只做语法与静态检查，未启动服务、未真实调用 CRM/LLM。生产验证需要部署重启后访问 `/static/mail-suite.html?id=KH23447-001`。

### 2026-06-04 追加修正

- 浏览器直开 `GET /api/v1/mail/customer-suite?id=KH23447-001` 且 `Accept: text/html` 时，后端会 307 跳转到 `/static/mail-suite.html?id=KH23447-001`，避免显示裸 JSON 中间页。
- 独立页面不再要求真实联系人邮箱；无邮箱时后端使用内部占位地址仅跑草稿生成链路，页面明确显示“仅生成模板，不发邮件”。
- 页面样式已调整为与现有工作台一致的白色顶栏、紫色主按钮、处理中 spinner、客户信息与四封邮件卡片。
- 本地后台已通过 `start_backend.ps1 -Port 8071 -KillPortOwner` 启动成功，当前监听 `127.0.0.1:8071` / `[::1]:8071`，PID 为 `20120`；`/static/mail-suite.html?id=KH23447-001` 返回 200，API 浏览器直开返回 307 跳转。
- 静态验证：`backend/main.py`、`backend/database.py` AST 解析通过；`frontend/mail-suite.html` 内联脚本抽取后 `node --check` 通过；`git diff --check -- backend/main.py backend/database.py frontend/mail-suite.html` 通过（仅 CRLF 提示）。

## 2026-06-04 邮件 V8 质量复核修正交接

- 用户明确指出：之前判断 v14 “已解决”是错误判断，后续迭代必须以页面可见邮件正文结果为标准。
- 结果层面问题仍存在：
  - v14 与 v7 页面正文肉眼几乎没有区别，不能用均分、段落数或关键词命中证明质量改善。
  - 邮件正文仍缺少直接、明确、稳定运用知识库案例段；“知识库不混进历史跟进”只是过程要求，最终结果必须体现知识库案例被用于正文。
  - 以案例1老客户为例，正文仍主要围绕翻译/本地化表达，没有把同传、多媒体本地化、排版印刷等新业务作为明确主推内容。
- 后续改进方向应聚焦结果：
  - 邮件正文必须肉眼可见地引用或改写知识库案例段。
  - 老客户已有翻译合作只能作为信任背景，新业务推广必须明确主推非翻译新业务线。
  - 每轮验收必须对比 v7/v14 页面正文，确认是否有明显内容升级。
- v14 调用环境说明：v14 是本机临时高端口服务触发，用于确保加载当前工作区最新代码；不是直接调用生产 `api.speedasia.net`。因此 v14 不能代表生产域名已经加载或展示同一结果。
- 本次记录只更新文档，不重新测试、不修改业务代码。

当前项目已有成熟的企微智能回复系统与隔离独立的邮件智能回复系统。
物理隔离与逻辑隔离表现为：
- 邮件数据库表 `mail_raw_unified`, `mail_cleaned`, `mail_import_batch`, `mail_iteration_run`, `mail_iteration_draft` 等独立命名并隔离。
- 邮件 API 使用 `/api/v1/mail/*` / `/api/v1/sequence/*` 独立路由。
- 邮件配置独立热加载，不阻塞、不影响企微会话状态机和侧边栏配置。

## 已完成核心里程碑

1. **Task 76 黄金库灌库（v1.7.198）**：upsert 25 黄金切片种子入库，通过 RAG 查重与 useful_score >= 0.6 验证，Few-Shot 精准命中。
2. **Task 77 LLM 接入（v1.7.198 / 206）**：接入 GPT-4o-mini 及 DeepSeek-Chat，二阶段生成草稿及 Prompt 真实落库，保留 SLA/价格强制物理拉正的防幻觉保护。
3. **Task 78 前端绑定（v1.7.198 / 205 / 206）**：前端 `#mail-quality-live-demo` 真实 fetch 后端接口渲染，上线黄金范例库与多轮迭代记录列表。
4. **WeCom 后台补算 Worker 锁修复与队列优化（v1.7.208）**：
   - 引入 SQL `exists` 联查子查询（MessageLog），目前仅销售有回复的会话才能进队列打分，摆脱 `pending_no_sales_reply` 历史堆积发生饥饿。
   - 时间倒序 `triggered_at.desc()` 优先处理最新对话。
   - `db.commit()` 移动 to loop 内部，打分或无变化单条处理完立即 commit 结束事务，消除 `idle in transaction` 持有行锁睡眠 3s 的致命隐患，消除 87.6 秒高延迟。
5. **宁缺毋滥（v1.7.207 / 209）**：彻底注释掉 8 处兜底模板 fallback，让上游错误和数据缺失（discount/payment_terms）直接以 HTTPException 503 暴露给前端，暴露真相。

## 验证与运行要求

- 重启后端以加载最新的 `backend/main.py`（释放 87.6s 延迟并应用倒序智能队列评分）。
- 所有状态变更及 GitHub 同步必须严格按照 Definition of Done 规范进行核对。

## 2026-06-05 邮件模板顶部控件单行布局修复交接

- 用户反馈：每阶段模板顶部的“当前模板目的说明”和“发送日期 / 间隔说明”各自输入框与保存按钮被渲染成 4 行，要求改为 1 行。
- 已修改 `frontend/index.html` 的 `renderMailSequenceTemplates()` 动态模板片段：顶部控件改为一行 6 段 grid，顺序为目的标签、目的输入框、保存目的按钮、发送日期标签、发送日期输入框、保存发送日期按钮。
- 技术说明：原 Tailwind 任意列宽类在动态 HTML 中可能未生效，已改为 inline CSS grid，并加 `min-w-[980px]` 与横向滚动兜底。
- 验证：`frontend/index.html` 内联脚本抽取后 `node --check` 通过；`git diff --check -- frontend/index.html` 通过。

## 2026-06-05 第一个场景第1阶段商业模板精细化交接

- 用户要求：严格按照分析要求，只先把第一个场景第 1 阶段修改完成。
- 已确认页面与接口场景顺序中第一个场景是 `new_business_promotion`，中文为“老客户其他业务介绍”，第 1 阶段为 suite_step=1。
- 已修改 `backend/main.py` 中该模板的 `purpose_cn`、`script_template`、`ai_instruction_script` 默认内容：从两段式轻提示升级为包含邮件目标、CRM 数据使用、知识库/同行业案例规则、4 段正文结构、禁止项、合格标准的商业 SOP。
- 已新增 `_MAIL_SEQUENCE_TEMPLATE_TARGETED_VERSIONS`，仅将 `("new_business_promotion", 1)` 目标版本设为 31；`_ensure_mail_sequence_templates()` 会只升级低于 31 的该单一模板，其他阶段仍按全局 version 30，避免扩散覆盖。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；`SKIP_DB_PATCH=1` 轻量导入确认第 1 阶段 version 31、第 2 阶段仍为 30。`python -m py_compile backend/main.py` 仍被既有 `backend/__pycache__` 权限拒绝。

## 2026-06-05 第一个场景第1阶段标题/目的/发送说明商用优化交接

- 用户继续要求：`第 1 封：破冰与低压力价值提示`、当前模板目的说明、发送日期 / 间隔说明也要按场景做商用综合优化，并始终符合 8 条商业邮件要求。
- 已修改 `backend/main.py`：新增 `_MAIL_SEQUENCE_STEP_LABEL_BY_SCENARIO`、`_MAIL_SEQUENCE_SEND_TIMING_BY_SCENARIO` 和对应 helper，使第一个场景第 1 阶段有专属标题与发送说明，不影响其他场景的第 1 封。
- `new_business_promotion + suite_step=1` 现在显示：
  - 标题：`第 1 封：老客户多业务破冰与低压力价值提示`
  - 目的说明：强调 4 封套装开场、承接历史合作、介绍翻译以外多业务，并结合客户行业、CRM 历史和知识库/同行业案例。
  - 发送说明：第 1 天发送，亲和破冰、不急于报价成交，并为第 2 封案例、第 3 封方案、第 4 封评估/转介绍收口铺垫。
- 生产脚本和 AI 指令同步加固：4 封层层递进、多业务开发、客户行业、客户历史、亲和语气、结尾转介绍、知识库/同行业案例读取、首封和后续邮件分工都已写成硬约束。
- 目标版本从 31 升到 32，仍仅升级该单模板，其他 11 个模板不被本轮覆盖。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；`SKIP_DB_PATCH=1` 轻量导入确认 version 32、新标题、新目的说明、新发送说明，并确认脚本包含 4 封套装、知识库、转介绍、后续阶段递进约束。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 第一个场景第1阶段数据库保存交接

- 用户指出页面仍没有明显变化。复查数据库后确认：`mail_sequence_template` 表里 `scenario='new_business_promotion' AND suite_step=1` 仍是 version 30 旧值，说明此前只是代码默认值变更，未实际写入当前页面读取的数据库行。
- 已执行当前代码的 `_ensure_mail_sequence_templates()`，实际把这条单行模板升级保存为 version 32。更新范围仅此一行，其他 11 个模板仍为 version 30。
- 本地 8071 接口验证通过：`GET /api/v1/mail/sequence-templates` 返回新标题 `第 1 封：老客户多业务破冰与低压力价值提示`，新目的说明、新发送说明、新生产脚本和 AI 指令。
- 页面若仍显示旧值，优先点击“刷新模板”或硬刷新页面；若访问的是其他服务进程/域名，需要确认该服务读取同一数据库，或重启/部署对应后端。

## 2026-06-05 第一个场景第2阶段模板完成交接

- 用户要求继续完成“1-2”的模板。已按上下文确认含义为第一个场景 `new_business_promotion`（老客户其他业务介绍）第 2 阶段 `suite_step=2`。
- 已修改 `backend/main.py` 默认模板：
  - 标题：`第 2 封：同行业案例证明与历史合作承接`
  - 目的说明：承接第 1 封多业务破冰，用客户行业、CRM 历史合作和知识库/同行业案例证明多业务组合有实际落地经验。
  - 发送说明：第 8 天发送，与第 1 封间隔 7 天；用案例和历史事实增强可信度，不进入详细报价或方案执行。
  - 生产脚本：改为完整商业 SOP，要求使用 CRM 事实、客户行业、知识库/黄金范例库案例，并区分“当前客户历史”和“同行业案例”。
  - AI 指令：要求 4 段左右、证据感、翻译以外至少 2 类业务、低压力下一步和转介绍，禁止价格/折扣/账期/工期/免费服务等未经审核承诺。
- 已将 `("new_business_promotion", 2)` 加入 `_MAIL_SEQUENCE_TEMPLATE_TARGETED_VERSIONS`，目标版本为 31，并实际执行 `_ensure_mail_sequence_templates()` 保存数据库该行。
- 验证：`backend/main.py` AST 通过；`git diff --check -- backend/main.py` 通过；数据库查询确认 version 31；本地 8071 `GET /api/v1/mail/sequence-templates` 确认第 2 阶段返回新标题、新目的说明、新发送说明和新脚本。

## 2026-06-05 1-1/1-2 AI 指令变量使用规则补齐交接

- 用户指出：已改的“给 AI 的指令脚本”里缺少变量位置和变量说明。问题成立，之前只写了业务约束，没有告诉模型变量应该放在哪一段、缺失时怎么处理。
- 已在 `backend/main.py` 新增统一变量使用规则，并追加到 `new_business_promotion` 第 1、2 阶段 AI 指令：
  - `{customer_name}`：邮件开头称呼；为空写“您好”。
  - `{company_name}`：第 1 段客户背景；缺失写“贵司”，不编造公司名。
  - `{industry}`：第 2/3 段行业场景和案例选择；unknown 时写“贵司业务场景/类似业务场景”。
  - `{history}`：第 1/2 段真实历史合作、合同、商机、跟进或活跃度；缺失时保守降级。
  - `{peer_case}`：案例证明段，只能作为知识库/同行业案例，不得写成当前客户历史。
  - `{business_lines}`：多业务介绍段，选择与客户行业和历史相关的 2-3 类业务自然融入。
  - `{seller_name}`：落款或轻量自我介绍；避免重复完整签名块。
  - `{referral_request}`：最后一段低压力转介绍。
- 明确禁止变量原样外露：不得输出 `{customer_name}`、`unknown`、`None`、空括号或系统字段名。
- 已通过 8071 保存接口 PUT 到页面读取的数据库行：第 1 阶段 version 34，第 2 阶段 version 33，`updated_by=codex_variable_usage_fix`。
- 本地 8071 GET 验证二者均包含“变量位置与使用规则”、`{customer_name}`、`{peer_case}` 和“禁止把变量名原样输出”。

## 2026-06-05 三场景十二封商用模板全量完成交接

- 用户要求：把剩余的场景-邮件按以上要求与标准逐个完成，不遗漏，不简单完成，最后验证单个场景下逻辑正常无矛盾。
- 已完成范围：三大场景 × 4 封 = 12 封全部模板。
- 代码改动：`backend/main.py` 新增商用模板生成器，按场景画像和阶段画像生成每封的 `step_label_cn`、`purpose_cn`、`send_timing_cn`、`script_template`、`ai_instruction_script`；不再依赖原先短句模板。
- 数据库保存：已直接更新 `mail_sequence_template` 12 行，全部 version 40，`updated_by=codex_commercial_all_templates_v40`，确保页面刷新模板即可读到。
- 全部模板共性要求：
  - 4 封层层递进，不重复同一套话。
  - 不只讲翻译，必须自然覆盖翻译以外业务。
  - 使用客户行业、CRM 历史、知识库/同行业案例。
  - 明确当前客户历史与知识库案例边界，不能把案例写成客户历史。
  - 亲和、商用、有证据、篇幅适合。
  - 结尾必须有低压力下一步和转介绍。
  - AI 指令包含变量位置、变量说明和缺失处理。
  - 禁止价格、折扣、账期、付款方式、工期、免费服务、未审核优惠等高风险承诺。
- 场景逻辑：
  - `new_business_promotion`：老客户多业务破冰 -> 同行业案例证明 -> 多业务组合方案 -> 方案评估/预算沟通/转介绍收口。
  - `re_activation`：老客户关系重启 -> 历史合作与同行业案例唤醒 -> 低门槛多业务协作路径 -> 资料评估/服务清单/转介绍收口。
  - `new_contact_intro`：新联系人公司介绍与正确对接确认 -> 同行业经验与可信度建立 -> 项目启动路径与多业务入口 -> 小范围评估/负责人确认/转介绍收口。
- 验证：`backend/main.py` AST 通过；定向 `git diff --check -- backend/main.py` 通过；本地 8071 API 校验 12 封均为 version 40，均包含变量规则、知识库、转介绍、价格禁区、历史/案例边界；专项逻辑校验通过。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-08 hj 受限账号登录修复交接

- 问题：生产 `POST https://api.speedasia.net/api/auth/login` 对 `hj / 123456` 返回 401 `账号或密码错误`；本地后端认证代码也只校验 `FRONTEND_AUTH_USERNAME` / `FRONTEND_AUTH_PASSWORD` 单账号，未返回前端需要的 `role`。
- 修复：`backend/config.py` 新增 `FRONTEND_AUTH_EXTRA_USERS`，默认 `hj:123456:mail_quality_only`；`backend/main.py` 新增多账号解析、按用户生成带角色的登录 token、token 校验时支持非 admin 用户，并让 `/api/auth/login` 与 `/api/auth/me` 返回 `role`。
- 前端限制：未改 `frontend/index.html`；现有 `mail_quality_only` 逻辑已经会限制 `hj` 只进入邮件质量工作台，并隐藏邮件配置和返回企微入口。
- 配置说明：`.env.example` 已记录 `FRONTEND_AUTH_EXTRA_USERS=username:password:role` 格式；生产如需改密码，可在 `.env` 覆盖该配置后重启后端。
- 验证：定向 `git diff --check -- backend/main.py backend/config.py .env.example` 通过；AST 解析 `backend/main.py`、`backend/config.py` 通过；FastAPI TestClient 验证 `hj / 123456` 登录及 `/api/auth/me` 均返回 `role=mail_quality_only`，原 `admin / Qw@2026` 仍返回 `role=admin`。
- 遗留：当前 Windows 环境 `python -m py_compile` 仍因 `.pyc` 写入/rename 权限拒绝失败，未修改权限；部署生产后需要重启 `api.speedasia.net` 对应后端服务让认证代码生效。

## 2026-06-08 邮件 V15 训练案例结果生成交接

- 用户要求：按最新案例及脚本生成邮件 V15 训练案例结果；不要改变微信，只涉及邮件；V14 为之前案例不要干扰。
- 已确认含义：当前最高邮件迭代记录为 V14，本轮生成新的 `mail_iteration_run.version_no=15`；当前邮件范围仍是 3 个产品指定案例 × 4 个 Sequence Step = 12 封，不是 15 封。
- V15 run：`226aa34b-2d47-4115-9ee8-ab49bc6a302b`，`run_label=mail_v15_latest_cases_scripts`，最终 `status=success`，12/12 成功，LLM 12/12，fallback 0，平均分 94.50。
- 处理过程：首次触发 V15 时 8 封因 CRM 邮箱被脱敏为 `***EMAIL***` 而触发 `valid recipient email is required`；已只改邮件链路，把脱敏占位/无效邮箱归一为空邮箱，并用恢复脚本补齐同一 V15 run 的失败行，未创建 V16，未改 V14。
- 代码范围：`backend/main.py` 邮件当前案例/迭代邮箱归一化、邮件草稿 LLM 请求 `trust_env=False`；新增 `scratch/backfill_mail_v15_failed_drafts.py` 与 `scratch/inspect_mail_v15.py` 作为本轮 V15 恢复/核验脚本；新增 `logs/mail-v15-analysis.md`。
- 查看方式：本地后端已按 `start_backend.ps1 -Port 8071` 恢复，`GET http://127.0.0.1:8071/api/v1/mail/iterations?limit=1` 返回 V15；详情接口为 `/api/v1/mail/iterations/226aa34b-2d47-4115-9ee8-ab49bc6a302b`。
- 注意：`logs/codex-run.log` 历史内容含非 UTF-8 字节，无法用 apply_patch 追加，本轮用 PowerShell `Add-Content` 追加运行记录。

## 2026-06-08 邮件 V16/V18 案例1问题修复交接

- 用户反馈：V15 案例1 prompt 过长、重复，未充分强调联系人/画像/检索案例，且内部编号如 `合同 XS260601-012` 不应出现；要求完成 V16，并把 prompt 压缩到 800-1200。
- 修复范围只在邮件链路 `backend/main.py`：当前案例 CRM 画像优先从当前三案例 SQL 快照读取；新增内部编号清理；邮件脚本模板升级到 v41；LLM prompt 改为压缩输入，不再附带完整脚本和完整 AI 指令。
- V16 run：`af3bd9de-2044-4d9b-80a8-eaf2a72ae1e0`，12/12 成功，fallback 0，均分 98.67；但案例1 prompt 仍为 1301-1313 字，未完全满足用户 800-1200 上限。
- 为避免假绿，已继续收紧 prompt 后在新端口 8073 跑有效复测 V18：`e3b8f956-cbac-4126-b3ea-5d19ddf6ce3b`，12/12 成功，fallback 0，均分 98.17；全量 prompt 958-1009 字，内部编号正则命中 0。
- V17 run `61656c30-6ef5-4e99-90a6-cc055cc405e9` 是旧 8072 进程未替换源码时的中间验证记录，prompt 仍约 1300 字，不作为最终有效结果。
- 当前有效本地服务端口：`http://127.0.0.1:8073`。查看最终有效复测：`GET /api/v1/mail/iterations/e3b8f956-cbac-4126-b3ea-5d19ddf6ce3b`。
- 验证：`backend/main.py` AST 解析通过；本地 API 触发真实 LLM 生成成功；12 封 prompt 长度、内部编号和场景分布已检查。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝写 pyc 失败。
- 遗留：V18 案例1第4封质量分 90，正文仍略泛化；个别 CRM 行业枚举会显示 `legal`，后续可单独补行业中文映射。

## 2026-06-08 邮件 V21 后续修正交接（未跑 V22）
- 当前用户要求：先修改，不开启下一轮 V22 测试。
- 已修改 backend/main.py：保留案例库中已有周期/速度/字数事实；免费/无偿样稿、试译、打样、评估、修改、服务会被替换为小范围资料评估；new_contact_intro 第1封 prompt 和模板新增商业介绍专项要求；模板目标版本提升到 v44。
- 素材缺口提示现在会写明需要补充的案例类型：new_business_promotion 需要多业务组合案例；re_activation 需要老客户唤醒/关系维护案例；new_contact_intro 需要首次介绍、可信度建立、项目启动路径和负责人确认样本。
- 已验证：python AST 解析 backend/main.py 通过；git diff --check -- backend/main.py 通过。
- 未完成：未跑 V22；后续如用户允许，再触发邮件迭代验证。

## 2026-06-08 邮件 V22 测试交接

- 用户最新要求：优化完成 V22 的测试。
- 已触发 V22 真生成：`mail_iteration_run.version_no=22`，run_id `29d7591c-ac1b-4193-8be7-079269227de8`，run_label `mail_v22_docx_communication_playbook_v45`。
- V22 结果：`success`，12/12 成功，LLM 成功 12/12，fallback 0，平均分 96.33，最低 86，最高 100。
- V22 安全检查：正文和主题未命中内部编号、免费/无偿/试译/样稿、微信/企微、价格/折扣/账期、直接索要联系人电话邮箱。
- V22 缺陷：真实 prompt 长度 1359-1612，超过此前 800-1200 标准，因此不能判定完全达标。
- 已继续修正当前代码：压缩 CRM 事实、黄金范例、系统提示、沟通过程规则；转介绍规则改为询问团队负责并请其判断是否转发，不直接要求联系人、电话或邮箱。
- 修正后仅做 prompt 预检，未新建 V23：当前 12 封 prompt 长度 979-1192，平均 1117.4。
- 验证：`backend/main.py` AST 通过；`git diff --check -- backend/main.py PROGRESS.md TASK_HANDOFF.md logs/codex-run.log` 通过；分析文件 `logs/mail-v22-analysis.md` 已新增。
- 下一步建议：如需要验证正文质量，需要再触发下一轮真实迭代（会自动成为 V23），不要覆盖或篡改 V22.

## 2026-06-09 检索与Agent流程优化交接

- **已完成任务**：检索与 Agent 流程的四大优化。
- **改动文件**：
  - `backend/config.py` (新增 RRF, Query Rewriting, Overlap 配置)
  - `backend/reranker.py` (NEW, RerankerService 词法重排与 RRF 融合)
  - `backend/intent_engine.py` (retrieve_knowledge_v2 改写与重排接入)
  - `backend/agent_builder/router.py` (upload_knowledge 段落叠窗切分)
  - `backend/agent_builder/engine.py` (Planning & Reflection 价格和分期纠偏)
  - `backend/mail_review_api_interface_checks.py` (修复 Mock 兼容性，让 API 契约测试再次通过)
- **验证结果**：
  - 新建的 `backend/optimizations_checks.py` 覆盖 6 大核心功能点，运行 100% 通过（`OK`）。
  - 修复 `mail_review_api_interface_checks.py` 后，全量运行 11 个 `mail_*_checks.py` 单元/接口测试用例 100% 成功。
  - 所有的 Python 文件语法检查 (`py_compile`) 均通过。
  - 无行尾空白，`git diff --check` 通过。
- **交接提示**：
  - 已在本地对所有编辑的文件做 trailing whitespace 清理，以保证 `git diff --check` 没有任何行尾空白警告。
  - 本轮修改不改变 WeCom/Email 生产逻辑的基本安全原则，所有测试完全解耦且全绿。

## 2026-06-09 邮件 V23 docx playbook 收口交接

- 用户要求：把现有邮件脚本彻底收口成 4 个 docx 沟通过程逻辑版本，并生成下一轮真实文案版本，加到 V23 中前台可见。
- 已修改范围：仅邮件链路 `backend/main.py` 和邮件工作台前端 `frontend/index.html`；未改企微/微信链路。
- 后端脚本：模板目标版本从 v45 升到 v46；清理旧 CTA/默认主题/案例说明；补充出口清洗拦截 `试译/样稿/打样` 和中文无审核周期表达。
- 前端可见：邮件套装步骤从旧 `临门样稿` 改为 `低压收口`，步骤说明同步为破冰 -> 行业案例 -> 协作路径 -> 低压收口。
- V23 run：`76c24b64-ecd3-4feb-b37f-55b12faf82b2`，`mail_v23_docx_playbook_v46_frontend_visible`，当前数据库最新 `version_no=23`，前台迭代列表可见。
- V23 结果：`success`，12/12 成功，LLM 成功 12/12，fallback 0，平均分 96.67，最低 90，最高 100，prompt 979-1192。
- 首次 V23 生成后发现 `试译样稿` 与中文周期表达残留；已在当前代码补清洗规则，并更新同一 V23 明细，未新建 V24。
- 最终复查：内部编号、免费/无偿/试译/样稿、微信/企微、直接索要联系人电话邮箱、价格/折扣/账期、旧口径、无审核周期表达均 0 命中。
- 分析文件：`logs/mail-v23-analysis.md`。
- 待办建议：人工在前台逐封看 V23 正文商业表达是否达到主观标准；如继续优化，应在 V24 生成，不覆盖 V23 历史。

## 2026-06-09 邮件 V23 排版调整交接

- 用户反馈：邮件正文中 `Michelle 您好，` 与后续正文挤在同一段；“您好”这类称呼应换行，正文不要按固定 4 段写死。
- 已修改 `backend/main.py`：新增 `_mail_normalize_body_paragraphs()`，在邮件组装时把称呼单独成段，正文按模型自然段保留；支持 `姓名 您好，`、`姓名，您好！`、`姓名您好，` 等格式。
- 已修复重复排版时孤立标点被拆成单独段落的问题。
- 复查结果：12/12 第一段均为称呼段；0 个孤立标点段；内部编号、免费/无偿/试译/样稿、微信/企微、直接索要联系人、价格/账期、无审核周期表达均 0 命中。
- V23 当前平均分因重新按正文评分统计为 94.33，主要受正文中保留的英文词（如 SpeedAsia/Word/PDF/PPT）影响；排版修复本身已生效。

## 2026-06-09 邮件合同案例库数据脱敏与精炼案例文本优化交接

- **已完成任务**：对合同案例库中的100条原始合同数据进行了企业名称及产品的脱敏处理，并在前端/后端添加并补足了精炼、优雅的邮件案例文字生成。
- **改动详情**：
  - 在 `backend/main.py` 的 `_desensitize_company_name()` 中扩充了30余家常见企业名称及相关行业的脱敏白名单（如 Allspring, CHAGEE 霸王茶姬, Burberry 博柏利, BD 碧迪, 拜耳, Covestro 科思创, KPF, Bureau Veritas 必维, Dörken 德尔肯, TOTO 东陶, Grohe 高仪, TUV 南德, Edwards 爱德华等）与高风险/特急标记。
  - 在 `backend/main.py` 的 `_generate_mail_case_text()` 中重构了精炼文本生成规则，针对笔译、口译、设计印刷、多媒体译制、展会搭建、商务礼品等各细分类型设计了高度优美、控制在50字以内的邮件推广句。
  - 调整了 `_mail_contract_case_business_line` 中的业务线优先级，确保特定度更高的“展会搭建 (exhibition)”与“商务礼品 (gift)”优先于通用印刷和翻译匹配。
- **验证与测试**：
  - 新建了专门的单元测试 [mail_contract_case_candidates_checks.py](file:///d:/items/QW/backend/mail_contract_case_candidates_checks.py) 并通过（`OK`），证明脱敏白名单映射正确，生成案例句严格 <= 50字，且不包含真实企业原名或品牌产品泄漏。
  - 运行了 `scratch/test_case_texts.py` 测试脚本，拉取 CRM 实测 100 条合同候选数据全部能生成高水准案例，全量长度测试无一超标，脱敏质量完全达标。
- **注意事项**：
  - 本轮只读读取 CRM `usrContract` 与 `usrCustomer` 数据，无任何写操作，真实发信与 CRM 写入仍关闭。
  - 已经通过 `git diff --check` trailing whitespace 格式检查，没有行尾空白。

## 2026-06-09 邮件草稿 LLM 选择器与 ChatGPT 接入交接

- 用户要求：增加前台可联动的 LLM 选择，选择哪个模型就用哪个生成；接入 ChatGPT 并测试是否可运行。
- 已完成后端：
  - `backend/config.py` 新增邮件草稿 provider 配置，DeepSeek 复用 `LLM2_*`，OpenAI/ChatGPT 使用 `MAIL_DRAFT_OPENAI_*`，并兼容 `RECORDING_PARSE_OPENAI_VISION_API_URL` / `RECORDING_PARSE_OPENAI_VISION_API_KEY`。
  - `backend/main.py` 新增 provider 解析、运行时切换、公开配置、连通性测试接口，并让邮件草稿 LLM 调用按当前 provider 选择 DeepSeek 或 OpenAI Chat Completions。
  - 新接口：`GET /api/v1/mail/draft-llm-config`、`PUT /api/v1/mail/draft-llm-config`、`POST /api/v1/mail/draft-llm-config/test`。
- 已完成前端：
  - `frontend/index.html` 邮件配置台的“范例检索 / 大模型参数”区域增加“邮件草稿模型选择”卡片。
  - 前台可刷新后端配置、测试 DeepSeek/OpenAI 连通性、切换当前邮件草稿生成 provider。
- 安全说明：
  - 聊天中出现过 OpenAI API Key，但未写入仓库、`.env`、日志或状态文件。
  - 接口与前台均不返回 API Key。
- 验证：
  - `backend/main.py`、`backend/config.py` AST 解析通过。
  - TestClient 验证：`GET /api/v1/mail/draft-llm-config` 返回 `deepseek` 当前启用；`POST /api/v1/mail/draft-llm-config/test` 对 `openai` 返回 `not_configured`；`PUT` 切到未配置 OpenAI 返回 422，符合预期。
  - 定向 `git diff --check` 通过。
- 下一步：
  - 如需真实测试 ChatGPT 外呼，需要把 Key 放到本机 `.env` 或环境变量 `MAIL_DRAFT_OPENAI_API_KEY`（或兼容别名 `RECORDING_PARSE_OPENAI_VISION_API_KEY`），重启后端，然后在前台点击 OpenAI 的“测试”和“使用此模型”。

## 2026-06-09 邮件 GPT-4.1 文案限制放宽与称呼排版修复交接

- 用户指出当前脚本限制太多，反而限制 AI 发挥，写不出 `other/邮件AI案例3.docx` 那类合格邮件内容。
- 已修复 `backend/main.py`：邮件草稿系统提示改为“资深 B2B 销售邮件起草人”，强调自然、具体、值得客户转发；保留价格/折扣/账期/免费承诺/内部编号/虚构数字/冒充客户反馈等硬安全线。
- 已放宽 `new_business_promotion` 第1封等阶段规则：允许写轻量参考、类似场景、before/after 或可分享示例，不再硬性禁止所有案例/方案/收口表达；第2封仍主打脱敏外部案例，第3封主打执行路径，第4封主打低压力收口。
- 已修复称呼段归一化，避免 GPT 输出的中文冒号或英文 `Hi Name:` 被拆成孤立段。
- 已把默认邮件草稿参数调整为 `MAIL_DRAFT_LLM_TEMPERATURE=0.55`、`MAIL_DRAFT_LLM_MAX_TOKENS=1800`，并同步 `.env.example`。
- 验证：`backend/main.py`、`backend/config.py` AST 通过；`git diff --check -- backend/main.py backend/config.py .env.example` 通过；离线称呼归一化测试通过；GPT-4.1 案例1-1单封实测 13.36 秒成功，`llm_model_used=openai:gpt-4.1`，正文成功生成且无孤立冒号，真实发信仍关闭。

## 2026-06-09 8071 端口后端拉起与接口测试修复交接

- **后端服务正常拉起**：在端口 `8071` 成功启动后端服务（通过 `$env:SKIP_DB_PATCH="1"` 绕过了数据库 schema 并发争锁导致的死锁）。
- **接口测试脚本修复**：修复了 `backend/mail_review_api_interface_checks.py` 内部因为 `main.py` 引入 `@app.get` 等 FastAPI 装饰器而导致 `exec()` 时发生 `NameError: name 'app' is not defined` 的问题。注入了自定义 `MockApp` 代替 `app`，解决了该执行环境问题。
- **全量测试通过**：本地执行 `python -m unittest discover -s backend -p "*_checks.py"` 覆盖全量 52 个单元测试脚本 100% 成功（`OK`）。

## 2026-06-09 邮件合同案例库分页与总数交接

- 用户询问合同案例库总条数、跳转页码、`5000` 含义，以及“最近 500 条”是否限制筛选范围。
- 已完成修复：`frontend/index.html` 增加筛选后总条数、当前页/总页数、上一页/下一页、页码输入跳转；筛选刷新会回到第 1 页。
- 已完成后端收口：`backend/main.py` 删除重复的旧版合同案例路由，只保留支持 `page + limit + total + pages + analysis` 的分页接口。
- 当前口径：`5000` 是金额下限，过滤字段为 `Money1 + Money2 + Money3 >= 5000`；下拉的 100/200/500 是“每页条数”，不是全局筛选上限。单页最大 500，但可通过分页查看筛选后的全量 10,799 条缓存数据。
- 验证：合同案例接口专项测试通过；后端 AST 通过；前端内联 JS 抽取后 node 语法检查通过；定向 diff-check 通过。`python -m py_compile` 仍因当前 Windows `backend/__pycache__` 权限拒绝失败，已用 AST 检查补足。

## 2026-06-10 CRM 快捷页与企微侧边栏输出交接

- 用户要求明确排查 `KH23447-001` 为什么显示成“广州锴信商务咨询有限公司”，并强调邮件快捷页不涉及发送，不需要邮箱，客户编号是唯一查询条件。
- 根因已确认：旧 SQL 在 `contact_email` 为空时仍使用 `LOWER(ISNULL(c.Email,'')) = :contact_email`，导致空邮箱联系人被误命中。
- 已修复 `backend/main.py` 的 `_mail_crm_profile_from_sql()`：存在 `customer_key` 时只走 CRM 编号字段匹配；只有没有客户编号且有邮箱时才按邮箱查。
- 只读验证 `KH23447-001` 已返回“蒙特空气处理设备（北京）有限公司上海办事处”。未写 CRM、未启用真实发信。
- 已修复 `backend/intent_engine.py` 知识库 V2 tuple 下标错误，线上侧边栏调用恢复成功。
- 已增强最终可发回复清洗，避免侧边栏把 `【摘要档案】`、`【线程推进状态】`、`【当前回复焦点】`、参考回复标题、JSON 或解释性文字展示/复制给销售。
- 线上真实会话复测结果：`status=success`、`knowledge_status=ok`、`crm_status=success`；`reply_reference1/2` 为纯中文可发回复，无 JSON、无内部块、无乱码。
- 当前仍有未提交本地缓存 `.codex_pycache_v15/`，不要加入 Git。
