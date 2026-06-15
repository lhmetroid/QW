# PROGRESS

## 2026-06-15 企微 API 输出剥离模型自加的策略标签(【直接回应】等)

- 现象：实时验证/迭代详情里"第6步·AI生成回复"出现 `【始终在线·Contextual Response】`/`【直接回应】`/`【直接回应客户最后一句】`/`【模板·直接回应·简短确认】` 等说明性前缀。
- 根因：这些标签不是后端代码加的(配置里回复风格只有"亲和微信风/商务克制风")，是 LLM-2 无视提示(SYSTEM_PROMPT_LLM2 第11/16/17条明令正文不得带括号说明)自行在正文最前面加的策略标签。现有防线漏掉它们：`stop` 序列只截 `【跟进思路说明/【说明/【后续/【本次回复风格`；`clean_sendable_reply` 的 `cut_patterns` 只剥含"说明/备注/后续/风格/思路/提示/分析/推进"等关键词的 `【...】`，而这些新标签不含上述关键词。
- 修复：`intent_engine.py` `clean_sendable_reply` 增加"剥离开头连续的短 `【...】` 标签"(限长 40 字以免误删正文)，覆盖 API/web/caselib 全部取 reply_reference 的路径(`main.py:20052` 等)。
- 验证：构造 6 例(各类标签+正常文)，剥离后均不含 `【`，纯正文样本保持不变；`intent_engine.py` AST 通过。

## 2026-06-15 企微聊天记录按北京时间当天给全 + 生成回复优先理解当日沟通

- 仅改企微/微信链路，不涉及邮件。
- 第1点(聊天记录窗口)：原实时侧边栏生成链路喂给流程的对话是"锚点(客户最新消息)之前可见消息的最近 10 条"(`backend/main.py` `visible_messages[-10:]`，注释里历史口径写的是 15 但实际取 10)。新增 `_select_dialog_window()`：按北京时间，锚点所在【当天】的消息全部给(当天超过 N 条也给)；当天不足 N 条需跨天时回退原有逻辑(取触发点之前最近 N 条，常量 `SIDEBAR_DIALOG_TAIL_COUNT=10`)。`MessageLog.timestamp` 为北京-naive，直接 `.date()` 比较即按北京日历日切分。调用点由 `recent_logs = list(reversed(visible_messages[-10:]))` 改为 `recent_logs = _select_dialog_window(visible_messages, anchor_message)`。该 `recent_logs` 是后续 LLM-1 分析、thread fact、LLM-2 生成的共同输入，改一处全链路一致。
- 第2点(生成回复要求)：在 LLM-2 回复生成 prompt 构造 `IntentEngine.build_sales_assist_request`(`backend/intent_engine.py`)追加 `same_day_note`：要求"优先理解并承接今天(北京时间当天)与客户的最新沟通内容与进展，以当天对话为主线推进，更早历史仅作背景，不被旧话题带偏/不重复旧追问"。模板占位与拼接两个分支都已追加，对所有调用 `build_sales_assist_request` 的生成路径生效。
- 第3点(API 客户原话字段)：本次回复锚定的客户原话字段是 `anchor_message_text`(配套 `anchor_message_id`/`anchor_message_time`)，写入于 `backend/main.py:18826`，持久化在 `api_assist_invocation` 表。按用户要求给实时 `/assist` 响应补了**顶层 `anchor_message_text`**：在 `_api_invocation_result_payload` 从持久化列回填(实时响应实际走该函数，非 `result` 字典)，并在 `result` 字典里也加了一份(覆盖 `api_invocation` 为空的回退路径)；缓存/复用路径返回的是已带该字段的 `final_result`。`_sanitize_api_sidebar_result_payload` 为黑名单式(只剥离对比模型字段)，不影响新字段。
- 验证：对 `backend/main.py` 与 `backend/intent_engine.py` 做 AST 解析通过。

## 2026-06-12 企微客户画像聚合接入

- 已按用户要求只修改企微/微信画像链路，不涉及邮件生成、邮件 CRM 或邮件安全门。
- 新增 `backend/crm_profile_aggregator.py`，复用现有 `crm_database.CRMSessionLocal` 只读查询 CRM，不新增第二套 CRM 密码配置；按天进程内缓存，输出 JSON-safe 的完整结构化画像。
- 已将 `IntentEngine.get_crm_context()` 改为优先使用新聚合画像，并保留旧 `fetch_crm_profile` 作为补充和 fallback；输出继续兼容旧字段，同时新增 `crm_profile_text`、`crm_profile_prompt_text`、`crm_profile_data`、`crm_profile_schema_version`、合同/报价/跟进/账期等完整字段。
- 按用户明确要求“不要隐藏”，企微 prompt 使用的 `crm_profile_prompt_text` 保留历史成交额、未开票额等金额事实，不再使用屏蔽金额版作为唯一输入。
- 验证：`python -m py_compile backend\intent_engine.py backend\crm_profile_aggregator.py backend\config.py backend\wecom_advance_completion.py` 通过；定向 `git diff --check` 通过；不连数据库的聚合上下文构造测试确认旧字段、新字段与金额 prompt 文本均正常。

## 2026-06-11 后台卡顿根因与防锁死机制

- 已定位当前卡顿主因不是端口：`/api/train_ai/models` 首次请求会连续探测外部训练 AI 模型地址，旧逻辑每个探测 15 秒，失败时可拖住 45 秒以上；`/api/case_lib/iterations` 还会做逐日统计；`/api/sessions` 会查 `message_logs` 聚合。
- 2026-06-11 17:10 继续定位：`/api/train_ai/models` 与 `/api/case_lib/iterations` 同一秒返回且耗时相同，说明不是两个接口各自独立卡住，而是 `async` 接口内同步逐日统计阻塞 FastAPI 事件循环，导致模型列表接口即使自身完成也要排队返回。
- 已将 `/api/case_lib/iterations` 改为列表页默认轻量模式：默认不再逐日实时统计；只有显式 `include_daily_stats=true` 才计算每日质量/耗时统计。
- 已将 `/api/train_ai/models` 改为默认不外连模型服务，只返回当前配置模型；只有显式 `refresh=true` 才拉远端模型列表。
- 已给 PostgreSQL 普通业务连接加防锁死参数：`statement_timeout=20s`、`idle_in_transaction_session_timeout=1min`、`lock_timeout=5s`。后续一键启动加载配置后，新连接会自动带这些参数，避免普通请求或闲置事务长期卡住。
- 已把训练 AI 模型列表探测超时降为 `TRAIN_AI_MODEL_LIST_TIMEOUT_SECONDS=2`，避免首页反复等待外部 `zjsphs.2288.org:11486` 不可达。
- 已优化 `/api/sessions` 查询：从 `GROUP BY user_id + max(timestamp)` 改为 PostgreSQL `DISTINCT ON (user_id)` 快路径，直接取每个会话最新消息，最多返回 500 条。
- 已新增只读诊断接口 `/api/system/db_lock_status`，可查看 active/blocked 数据库会话、核心表统计和当前超时参数；接口不主动杀连接。
- 验证：`backend/main.py`、`backend/config.py`、`backend/database.py` AST 通过；`/api/sessions` 核心 SQL 本地实测 500 条约 788ms；新连接 `show statement_timeout/idle_in_transaction_session_timeout/lock_timeout` 分别为 `20s/1min/5s`；定向 `git diff --check` 通过。需要重启后端后生效。

## 2026-06-11 案例1最终 Prompt v51 压缩与前台模板可见性修正

- 已按用户 6 点反馈继续修正案例 1：Step1 最终 prompt 从约 2000 字压到 1898 字；目标/节奏不再塞入长套装说明，改为短目标与短发送节奏。
- 2026-06-11 13:50 继续修正变量表达误解：最终 prompt 不再使用 `客户称呼：Michelle Li；模板：{customer_name}` 这类重复格式，改为类似微信 LLM2 脚本预览的 `{customer_name} = Michelle Li` 变量取值块；Step1 当前为 1818 字。
- 已把最终 prompt 分区改为 `结构脚本`、`AI指令`、`变量取值`，去掉 `最终Prompt-结构脚本` / `最终Prompt-AI指令` 这种容易让人工误解的命名。
- 已将案例 1 `new_business_promotion` 4 个模板目标版本升至 v51，并触发数据库更新；数据库核对 steps 1-4 均为 `version_no=51`。
- 已把 Step1/2/3/4 的结构脚本变量说明改为显式列出业务范围：笔译/本地化、会议同传/设备、多媒体译制、排版印刷、展会活动物料、商务礼品，前台人工看脚本时不再只看到抽象 `{business_lines}`。
- 已移除残留的通用硬编码提示：`之前 SpeedAsia 和贵司配合过笔译及患者日同传设备相关支持`、`常见医疗活动场景参考` 不再作为通用脚本/阶段提示。
- 已将前台字段名统一为 `最终Prompt-结构脚本` 与 `最终Prompt-AI指令`，避免再用“生产脚本/给 AI 的指令脚本”造成两个脚本像两套逻辑的误解；最终 prompt 仍同时带入两者。
- 已将知识库/Few-shot 从单条扩展为 Top3，最终 prompt 明确写为“相关优秀同类型邮件段落供参考或运用”，并保留不得把外部案例写成当前客户历史的边界。
- 已刷新 `logs/mail-case1-final-prompts-v27-preview.md`；文件名仍沿用旧名，但内容为当前 v51 最终 prompt 预览。
- 验证：`python scratch\preview_mail_case1_final_prompts.py`、`backend/main.py` AST、数据库 v51 查询、旧硬编码文本 grep、定向 `git diff --check` 均通过。本轮未调用 LLM，未真实发信。

## 2026-06-11 邮件生成链路审计与前台模板打通

- 已确认旧问题：邮件质量诊断页右侧“生产脚本模板 / 给 AI 的指令脚本”此前没有进入最终 `_build_mail_draft_llm_full_prompt()` 主体，导致人工调前台模板不稳定影响最终 AI 输出。
- 已修复：最终 prompt 现在明确包含前台保存到数据库的 `sequence_template_script` 与 `sequence_template_ai_instruction`，并标注“必须作为本次写作主规则”；通用规则只作为兜底。
- 已修复变量链路：最终 prompt 中新增 `{customer_name}`、`{company_name}`、`{industry}`、`{history}`、`{peer_case}`、`{business_lines}`、`{seller_name}`、`{referral_request}` 的变量值映射，前台仍保留通配符形式，模型拿到的是“模板通配符 + 替换值”。
- 已修复行业误判：去掉案例 1 按客户名硬编码覆盖历史/Few-shot 的逻辑；行业改为可信度判定，医疗/医药/生命科学公司优先标为医疗器械/生命科学，设备/制造/工业公司优先标为工业设备/制造；`legal` 只作为法律/合同资料线索，不再直接写成客户属于法律行业。
- 已补知识库链路：最终 prompt 现在显示 Few-shot 命中标题、分数和内容摘要，并明确只参考节奏/场景/表达方式，不得照抄或把外部案例写成当前客户历史。
- 已重新输出案例 1 四封最终 prompt 到 `logs/mail-case1-final-prompts-v27-preview.md`，可看到 `最终Prompt-结构脚本`、`最终Prompt-AI指令`、变量映射、CRM画像和知识库/Few-shot 命中均进入最终 prompt。
- 验证：`backend/main.py` AST 通过；前台模板哨兵文本测试通过（临时 `FRONT_TEMPLATE_SENTINEL` / `FRONT_AI_SENTINEL` 会进入最终 prompt）；行业纠偏小测通过；定向 `git diff --check` 通过。本轮未真实发信。

## 2026-06-10 案例1邮件 Prompt 简化与最终 Prompt 预览

- 已将邮件草稿 LLM prompt 从多规则堆叠改为短结构：角色、任务、背景、写法要求、不要写、输出格式。
- 已从最终 prompt 中移除会诱导模型乱写的内部负责人/销售跟进渠道/范例正文，只保留客户公司、行业场景、商机/历史合作事实和范例标题风格。
- 已固定案例 1 客户行业场景为“医疗器械/生命科学相关客户”，避免再把法律/合同资料类型误写成客户行业。
- 已输出案例 1 四封变量替换后的最终 AI prompt 到 `logs/mail-case1-final-prompts-v27-preview.md`；本轮未调用 LLM、未生成 V27、未真实发信。

## 2026-06-10 邮件 V25/V26 案例1 DeepSeek 与 ChatGPT 对比测试

- **测试范围**：只跑案例 1 `new_business_promotion` 的 4 封 Sequence，不跑案例 2/3。
- **V25 DeepSeek**：run_id `1526ed09-58b3-4054-ab05-0c5dab64992b`，4/4 成功，模型 `deepseek:deepseek-chat`，平均分 97.00。
- **V26 ChatGPT/OpenAI**：run_id `51ada09e-5afd-436d-883d-fb35562fdc76`，4/4 成功，模型 `openai:gpt-4.1`，平均分 96.00。
- **docx 标准靠拢**：按 `other/邮件AI案例1.docx` 的“行业感 + 轻商务 + 不施压”检查，四封递进为破冰、案例证明、协作路径、低压力收口。
- **出口修正**：补强 `backend/main.py` 邮件出口清洗，避免 `小批量测试/试用`、`法律行业/法务培训`、`不涉及具体报价`、孤立行业场景句等不自然或不稳妥表达；已同步清洗 V25/V26 已落库 8 封。
- **复查**：V25/V26 共 8 封禁用词与旧口径检查 0 命中；分析记录见 `logs/mail-v25-v26-analysis.md`。

## 2026-06-10 implementation_plan 复核与案例1四模板补齐

- **运行时 LLM 配置复核**：已确认 `backend/main.py` 存在 `/api/v1/system/runtime-llm-settings` GET/PUT、`RuntimeLlmSettings`、`_load_runtime_settings_with_defaults()`，并且邮件生成读取动态 `mail_system_prompt` / `mail_temperature`；`backend/intent_engine.py` 已读取动态 `wecom_system_prompt` / `wecom_temperature`。
- **前端 2x2 面板复核**：已确认 `frontend/index.html` 邮件配置台新增企微/邮件 System Prompt 与 Temperature 的 2x2 控制台，进入配置页会加载设置，保存会 PUT 到后端。
- **案例 1 四模板补齐**：在 `backend/main.py` 只为 `new_business_promotion` steps 1-4 新增专属 `script_template` 与 `ai_instruction_script` 覆盖，形成破冰、案例证明、方案路径、低压力收口四封递进；案例 2 `re_activation` 与案例 3 `new_contact_intro` 保持 version 46 和原逻辑不变。
- **目标版本确认**：`_MAIL_SEQUENCE_TEMPLATE_TARGETED_VERSIONS` 中仅 `new_business_promotion` steps 1-4 为 `48`，其余两个场景仍为 `46`。
- **验证结果**：AST 解析通过；`backend.mail_review_api_interface_checks` 通过；前端内联 JS `node --check` 通过；runtime settings PUT/读取逻辑通过 scratch 隔离测试；定向 `git diff --check` 通过。`python -m py_compile backend\main.py backend\config.py backend\intent_engine.py` 仍因既有 `backend/__pycache__` pyc rename 权限拒绝失败，已用 AST 解析补足语法验证。

## 2026-06-10 Claude 3.5 Sonnet 接入与 Prompt 优化、新业务模板瘦身

- **Claude 3.5 Sonnet 接入配置**：在 `backend/config.py` 中新增 `MAIL_DRAFT_ANTHROPIC_*` 系列配置项，预留 API Key 空间。在 `backend/main.py` 的 provider 映射及测试端点中增加对 `anthropic` 与 `claude` 别名的支持。
- **B2B 销售人设 System Prompt 重构**：修改 `_MAIL_DRAFT_LLM_SYSTEM_PROMPT` 为资深 B2B 销售人设（温和、专业、克制、轻商务），指导模型融入 CRM 事实并严禁主动做出价格、工期或条款承诺，限定输出为 JSON。
- **Claude API 及 Markdown 剥离适配**：在 `_call_llm2_json_for_mail_draft` 中对 Anthropic 原生 API 的 Header 与 Payload 进行了适配。增加了对代理中可能返回的 ```json ``` 标记的安全剥离，确保 JSON 解析高鲁棒性。
- **新业务模板瘦身（v47）**：对 `new_business_promotion` 第 1 封邮件模版及 AI 指令做了“瘦身”，去除了冗余合规性提示，使其仅专注于“邮件切口与目标”。将 Targeted Version 提升到 `47` 以触发数据库模板自动覆盖升级。
- **编译与 47 项测试通过**：
  - 编译与语法检测：`python -m py_compile backend/main.py backend/config.py` 通过，AST 检查无错。
  - 测试：运行全量 47 个 `mail_*_checks.py` 的测试用例以及 `backend/mail_review_api_interface_checks.py` 100% 成功（OK）。

## 2026-06-09 邮件合同案例库全量回灌入库

- **数据库与同步脚本**：在 `backend/database.py` 中定义了本地 `MailContractCase` 表模型，创建了 `backend/sync_crm_contracts_to_local.py` 增量/全量同步脚本，支持清空重建、CRM 只读读取、本地 PostgreSQL 批量灌库与更新。
- **全量导入成功**：运行同步脚本将 CRM 数据库中所有符合标准的 **10,799** 条合同数据（`ContractId LIKE '%XS%'`，`Deleter IS NULL`，`Money1+Money2+Money3 >= 5000`）全部成功同步并持久化到本地 PostgreSQL 数据库。
- **API 改用本地查询**：将 `/api/v1/mail/contract-case-candidates` 接口重构为直接查询本地 `MailContractCase` 缓存表，支持相同的限额、业务类型、产品及描述关键词过滤和时间排序，响应速度大幅提升，从 500 条限制扩展为支持全量 10,799 条。
- **单元与集成测试**：在 `backend/mail_contract_case_candidates_checks.py` 中补充了 TestClient 接口级端到端测试，全套 53 个测试用例 100% 通过（全绿）。
- **后台服务重启**：已安全关闭旧实例并重启了 8071 本地后端服务。

## 2026-06-09 邮件合同案例库精炼与闪光点突出

- **精炼与差异化优化**：针对“邮件合同案例库”中 100 条 CRM 候选数据过于模板化、千篇一律的问题，重构了 `_generate_mail_case_text` 的文案生成规则，为笔译、口译、同传、展会、设计印刷、多媒体译制、定制礼品等多条业务线设计了高度差异化的具体案例描述。
- **突出具体闪光点**：提取了合同描述与产品名中的关键场景与岗位切口（如住设商品战略会议、播客配音、患者日同传、审计报告、白皮书、Avansee 手册、AATS 年会、Lelabo 专访、亦庄活动、沈阳礼品、品胜自带线充电宝等），生成极具闪光点且专业优雅的推介文案，让同一产品的不同合同显露出实质性差异。
- **脱敏与长度限制**：确保所有生成的推介文案中使用的都是脱敏后的企业名称（如“某知名美妆巨头”），并且通过在 fallback topic 发生器中清洗原始公司名（防止原名在描述中穿透泄露）和自动将超过 10 字符的冗长主题截断为“...等”，使得全部 100 条案例长度严格控制在 50 字以内。
- **验证通过**：
  - 语法与 AST 检查：`python -m py_compile backend/main.py` 通过，`git diff --check` formatting checks 均通过。
  - 全套 52 个单元测试与接口测试全部 100% 成功通过（全绿）。
  - 执行 `scratch/test_case_texts.py` 遍历 CRM 真实数据生成的 100 条案例中，文案极为具体、闪光点突出、无名称泄漏，且所有案例长度严格控制在 50 字以内。

## 2026-06-08 邮件沟通过程案例脚本优化

- 已参考 `other/邮件AI案例1-4.docx` 的沟通过程，仅优化邮件脚本流程，不改微信/企微链路。
- 已将 4 个沟通过程抽象为邮件 playbook：行业感 + 轻商务 + 不施压；按采购/技术/项目/HR培训/市场品牌/海外窗口选择不同切口；旧关系重连不催旧报价；转介绍先问“这类项目通常由哪个团队/同事负责”，不直接索要联系人。
- 已强化英文内容/品牌内容场景表达：从“翻译”转为英文内容优化、品牌语气一致性、国际化表达、before/after 参考等商务切口。
- 已把规则接入邮件商用模板生成器和实际 LLM Prompt；12 个邮件模板目标版本从 v44 升至 v45，重启后刷新模板会自动更新低版本模板。
- 已明确邮件输出不得使用微信跟进语或微信式口语；本轮没有修改企微实时回复、企微评分或微信侧逻辑。
- 验证：`backend/main.py` AST 通过；12 个默认模板均为 version 45；模板文本检查命中“沟通过程萃取规则”“不同岗位切口不同”“不得写微信跟进语”“不要直接索要联系人”；`git diff --check -- backend/main.py` 通过。

## 2026-06-08 企微实时对话获取方式整理

- 已按当前代码整理企微实时对话获取方式，新增 `docs/企微实时对话获取方式.md`。
- 文档覆盖会话存档同步、侧边栏实时辅助、请求参数、响应字段、关键表、排查接口和 curl 示例。
- 本轮只新增说明文档，不修改企微/邮件业务代码，不读取或输出 `.env` 中的真实密钥。
- 验证：`git diff --check -- docs/企微实时对话获取方式.md PROGRESS.md TASK_HANDOFF.md` 通过；`docs/` 与 `*.log` 当前受 `.gitignore` 忽略，文件已在本地生成。

## 2026-06-08 邮件合同案例库只读入口

- 已新增独立“邮件合同案例库”，在邮件工作台中与“黄金范例库”同级展示。
- 后端新增 `GET /api/v1/mail/contract-case-candidates`，只读查询 CRM `usrContract` 原表；默认按 `InputTime`（新增/录入时间）倒序取最近 100 条，金额过滤为 `Money1+Money2+Money3 >= 5000`。
- `ContactId=''` 仅作为排查参考，默认不按联系人为空过滤；页面会展示原始合同字段、产品线/语种/行业粗推、质量标记和入库建议。
- 当前不区分新业务推广、老客户激活、新联系人介绍三类场景；不脱敏、不入邮件知识库、不触发邮件迭代或 V22。
- 真实 CRM 只读验证摘要：最近 100 条中 77 条可初筛；产品线粗推为口译/同传 35、排版印刷 29、翻译 22、多媒体译制 9、礼品物料 3、会议活动 2；主要低质量信号为描述过短 21、补差价/尾款 2。
- 验证：`backend/main.py` AST 通过；`frontend/index.html` 内联 JS 抽取后 `node --check` 通过；`git diff --check -- backend/main.py frontend/index.html` 通过；直接调用后端函数成功读取真实 CRM 摘要。

## 2026-06-08 Agent Builder 补齐与验证完成

- **已完成**：
  - 数据库模型 `BuilderKnowledge` 与 `BuilderKnowledgeChunk` 已落地，支持上传库存商品目录，计算 1024 维 Cosine 相似度进行 B2B 语料 RAG 检索。
  - 完善并验证了 `backend/agent_builder/` 下的接口：支持文件上传分块、微信/WhatsApp Webhook 仿真及解密分流、以及 Prompt 自愈优化自愈端点。
  - 实现了 `frontend/agent_builder.html` 的前端大屏：包含 SVG 无限贝塞尔曲线连接的 SOP 流程图画布（支持卡片拖拽、连线重绘、双击修改）、真实产品库文件上传终端、以及 Webhook 仿真控制台，可进行前后台实时联调。
  - **质检测试通过率**：12个对抗用例自动化测试套件 100% 成功通过（12 PASS / 0 FAIL / 0 WARN），且自愈优化端点 `/optimize_prompt` 调用结果符合预期。

## 2026-06-05 企微实时验证浮层中文化

- 已将案例库实时验证列表相关浮层说明中文化，重点覆盖链路状态、LLM2 主回复、训练AI并行回复、耗时列总说明和耗时列逐行实测拆分。
- 耗时浮层不再直接展示 `normalize_request`、`build_session_id`、`jsonable`、`sanitize`、`store_invocation` 等英文技术字段作为说明标题，改为“请求解析”“会话ID生成”“结果转可存储结构”“脱敏清理返回内容”“写轻量调用记录”等中文解释。
- 保留必要技术名如 LLM2、CRM、KB1/KB2、ApiAssistInvocation，用于和日志/后端对象对账。
- 验证：`frontend/index.html` 内联 JS 抽取后 `node --check` 通过；`git diff --check -- frontend/index.html` 通过（仅 CRLF 提示）。

## 2026-06-05 企微实时验证耗时浮层按环节拆分修复

- 已按用户反馈修复案例库实时验证列表“耗时”单元格悬停说明：不再只显示泛化链路说明，而是按当前行实测数据拆分第一行/第二行耗时。
- 后端 `GET /api/case_lib/daily_validation/{date}?view=api` 的行数据新增返回 `timings_ms`，用于前端读取 `pipeline_total_ms`、`total_ms`、`tail_ms`、`jsonable_ms`、`sanitize_ms`、`store_invocation_ms`、`first_db_commit_ms` 等真实耗时。
- 前端耗时 tooltip 新增当前触发的环节拆分：请求解析、会话定位、全量消息读取、Fast-Track、LLM-1、CRM、知识检索、LLM2 主回复、训练AI并行回复、尾段轻量落库分别显示独立毫秒数；并行环节不再混成单一总耗时。
- 验证：`backend/main.py` AST 解析通过；`frontend/index.html` 内联 JS 抽取后 `node --check` 通过；`git diff --check -- backend/main.py frontend/index.html` 通过（仅 CRLF 提示）。

## 2026-06-05 邮件三场景十二封商业模板升级

- 已按用户要求将邮件质量诊断页模板布局再次调整：
  - `当前模板目的说明 + 输入框 + 保存目的 + 发送日期 / 间隔说明 + 输入框 + 保存发送日期` 在宽屏下一整行展示。
  - `变量说明 / 生产脚本模板 / 给 AI 的指令脚本` 等分 3 列，自适应小屏堆叠。
  - 生产脚本与 AI 指令输入框固定约 15 行高。
- 已将 3 个案例场景文案统一为：
  - `KH15411-117`：老客户其他业务介绍。
  - `KH02659-011`：老客户激活。
  - `KH13770-006`：新客户开发介绍。
- 已重写 `backend/main.py` 中 3 场景 × 4 步 = 12 条 `生产脚本模板` 和 `给 AI 的指令脚本`：
  - 四封邮件层层递进。
  - 不只讲翻译，覆盖本地化、同传会议、多媒体内容、排版印刷、活动物料等多业务。
  - 强制结合客户行业、CRM 历史合作/合同、最近商机/跟进、同行业范例；缺真实依据则不得编造。
  - 新客户开发第 1 封要求 1-2 句 SpeedAsia 公司与服务范围介绍。
  - 结尾保留低压力转介绍请求。
  - 已移除“试用”导向，改为资料评估、方案评估、服务清单、预算沟通提纲等商用表达。
- 已补邮件 LLM prompt 结构：将 CRM 公司名、生命周期、最近商机/报价、历史合同/合作、最近跟进和范例参考传入 LLM；系统 prompt 增加多业务、行业历史、转介绍和禁止编造约束。
- 已新增模板默认版本 `_MAIL_SEQUENCE_TEMPLATE_DEFAULT_VERSION = 30`，`_ensure_mail_sequence_templates()` 会把旧版本模板自动升级到新商业模板；本地数据库 12 条模板已升级到 version 30。
- 验证：`backend/main.py`/`backend/crm_profile.py` AST 通过；抽取 `frontend/index.html` 内联 JS 后 `node --check` 通过；定向 `git diff --check` 通过（仅 CRLF 提示）；数据库 12 条模板检查 `DB_HAS_TRIAL_WORD=False`。

## 2026-06-05 邮件全量测试校验与 CRM 真数据异常修复

- **已完成**：
  - `backend/main.py`：修复了 `_build_mail_draft_intent_profile` 中，当从真实 CRM 数据库（如 `KH33886`）查询 opportunities, contracts 等字段返回 `None` 时，传入 `MailDraftIntentProfile`（类型为 `str`）导致的 Pydantic `ValidationError` 崩溃问题，现已加入安全的 `or ""` 默认 fallback。
  - `backend/mail_review_api_interface_checks.py`：修复了由于 `main.py` 的 `_build_mail_generate_draft_response` 引入了模板数据库查询，导致单元测试 Mock database `_NoPricingRulesDb` 缺少 `query` 属性引发 `AttributeError` 报错的 bug。
  - `scratch/verify_mail_generation_crm.py`：移除了对 `intent_profile.customer_tier` 的无效 print 语句（`MailDraftIntentProfile` 模型中无该属性）。
- **验证结果**：
  - 全量 11 个 check 测试文件，共 43 个单元/接口测试用例 100% 成功通过（全绿）。
  - 执行 `scratch/verify_mail_generation_crm.py` 成功完成端到端 CRM SQL 真实查询与 `deepseek-chat` 模型草稿生成交互，且所有 6 个物理安全门全部 `passed` 校验通行。

## 2026-06-05 邮件模板目的与发送间隔布局调整

- 已按用户截图要求调整邮件质量诊断页“三大场景全阶段脚本模板”的单个阶段布局。
- `当前模板目的说明` 与 `发送日期 / 间隔说明` 改为顶部同一行展示：标签 + 单行输入框 + 右侧保存按钮。
- 下方内容改为三列：变量说明、生产脚本模板、给 AI 的指令脚本，避免原先左侧两块 textarea 竖排占高。
- 保存逻辑仍复用原 `saveMailSequenceTemplateField()`，字段 ID 不变，不改后端接口和 `.env`。
- 验证：抽取 `frontend/index.html` 内联 JS 后 `node --check` 通过；`git diff --check -- frontend/index.html` 通过（仅 CRLF 提示）。

## 2026-06-05 CRM 生命周期阶段规则更新

- 已按用户确认的新口径更新 `backend/crm_profile.py` 的 `_get_customer_lifecycle_stage()`：
  - 熟联系人：客户/公司近 1 年有 3 个及以上销售合同。
  - 老联系人：客户/公司历史上有过销售合同，不再受 6 个月窗口限制。
  - 新联系人：客户/公司没有过销售合同。
- 生命周期统计口径从原先 `ContactId + crmContactYeWuSetting 时间窗/报价阈值` 改为优先按 `CustomerId` 客户/公司维度统计销售合同；找不到 `CustomerId` 时才退回 `ContactId`。
- 已移除原函数中 `old_contract_number=3` 覆盖 CRM 配置、以及“不满足熟/老就无条件新联系人”的错误口径。
- 已同步更新邮件质量诊断页 tooltip，说明新生命周期规则。
- 只读验证当前 3 个案例：
  - `KH15411-117`：总合同 362，近 1 年合同 20，阶段为熟联系人。
  - `KH02659-011`：总合同 214，近 1 年合同 0，阶段为老联系人。
  - `KH13770-006`：总合同 20，近 1 年合同 2，按新规则阶段为老联系人。
- 验证：`backend/crm_profile.py`、`backend/main.py` AST 解析通过；`git diff --check -- backend/crm_profile.py frontend/index.html` 通过（仅 CRLF 提示）。

## 2026-06-05 案例库日常验证详情加载优化

- 已定位截图中“正在加载详情...”对应前端 `caselibOpenDetail()` 调用的后端接口：`GET /api/case_lib/daily_validation/{date}?view=api&limit=300`。
- 已修复后端此前忽略 `view=api&limit=300` 的问题：API 快路径现在先按当天 `ApiAssistInvocation.triggered_at` 查询最近调用记录，再只加载这些调用涉及的会话消息，不再先全量扫描当天全部 `MessageLog`。
- API 快路径只返回本批 API 调用匹配到的轮次，避免同一会话当天其它人工轮次被带入详情页导致结果膨胀。
- 已新增耗时日志：
  - `CASELIB_DAILY_DETAIL_TIMING`：日常验证详情，字段包含 `query_invocations_ms`、`query_session_logs_ms`、`group_sessions_ms`、`build_invocation_map_ms`、`build_results_ms`、`build_summary_ms`、`total_ms`。
  - `CASELIB_ITERATION_DETAIL_TIMING`：普通迭代详情，字段包含 `query_run_ms`、`query_results_ms`、`query_cases_ms`、`query_turns_ms`、`build_case_maps_ms`、`build_rows_ms`、`total_ms`。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过（仅 CRLF 提示）。`python -m py_compile backend/main.py` 仍被 Windows pyc 文件权限拒绝，已清理本轮产生的临时 `.codex_pycache`。

## 2026-06-05 当前可用模型协议优先顺序调整

- 已按用户要求把当前 `http://zjsphs.2288.org:11486` 已验证可用的协议放到最先尝试。
- 训练 AI 模型列表顺序调整为：`/api/tags` -> `/v1/models` -> `/api/model-chat/models`。
- 训练 AI 生成顺序调整为：`/api/chat` -> `/v1/chat/completions` -> `/api/model-chat/chat`。
- Embedding 顺序调整为：`/v1/embeddings` 优先，失败或空向量再回退 `/api/embeddings`。
- 验证：`backend/main.py`、`backend/embedding_service.py` AST 解析通过；定向 `git diff --check` 通过；`EmbeddingService.embed()` 再次返回 1024 维真实向量。

## 2026-06-05 当前 11486 模型与 Embedding 适配

- 已确认训练 AI 兜底逻辑不会产生假数据：只按协议顺序调用真实外部接口，全部失败时返回 `status=failed/timeout` 和错误原因，不会拼接模板回复或伪造成功。
- 已确认 `http://zjsphs.2288.org:11486` 当前存在并可调用 `unsloth-qwen2.5-task-60:latest`，训练 AI 配置应使用带 `:latest` 的完整模型名。
- 已确认 `qllama/bge-m3:latest` 在 `11486` 存在；`/api/embeddings` 返回空向量，真实可用接口是 `/v1/embeddings`。
- 已修改 `backend/embedding_service.py`：Ollama provider 下先试 `/api/embeddings`，若空向量则自动回退 `/v1/embeddings`；OpenAI-compatible provider 默认补 `/v1/embeddings`，并允许无 API key 的本地兼容服务。
- 验证：`backend/embedding_service.py`、`backend/main.py` AST 解析通过；`git diff --check -- backend/embedding_service.py backend/main.py` 通过；直接调用 `EmbeddingService.embed()` 返回 1024 维真实向量。

## 2026-06-05 训练AI恢复 model-chat 优先与日志增强

- 已按用户反馈修复训练 AI 仍未成功的问题：`_train_ai_chat()` 从单纯直连 Ollama/OpenAI 回退，改为优先尝试旧链路 `/api/model-chat/chat`，再回退 `/api/chat`，最后回退 `/v1/chat/completions`。
- `_train_ai_list_models()` 同步恢复多协议探测：优先 `/api/model-chat/models`，再 `/api/tags`，最后 `/v1/models`。
- 已新增训练 AI 专属日志关键字：`TRAIN_AI_START`、`TRAIN_AI_ATTEMPT_SKIP`、`TRAIN_AI_ATTEMPT_EMPTY`、`TRAIN_AI_ATTEMPT_FAILED`、`TRAIN_AI_SUCCESS`、`TRAIN_AI_FAILED`、`TRAIN_AI_TIMEOUT`、`TRAIN_AI_ERROR`、`TRAIN_AI_MODELS_OK`、`TRAIN_AI_MODELS_FAILED`。
- 成功结果继续写入 `training_ai.protocol`，可区分 `model_chat`、`ollama_api_chat`、`openai_chat_completions` 或 `all_failed`。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过。

## 2026-06-05 训练AI接口 404 协议兼容修复

- 已修复训练 AI 调用 `http://zjsphs.2288.org:11486/api/chat` 返回 404 时无法生成的问题。
- `_train_ai_chat()` 现在先尝试 Ollama 原生 `/api/chat`，若返回 404，会自动回退到 OpenAI 兼容 `/v1/chat/completions`，并在 `training_ai.protocol` 中记录实际命中的协议。
- 服务器本次只需更新 `backend/main.py` 并重启；`.env` 仍使用现有 `TRAIN_AI_BASE_URL`、`TRAIN_AI_API_KEY`、`TRAIN_AI_MODEL` 配置即可。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过。

## 2026-06-05 邮件模板顶部控件单行布局修复

- 已按用户截图反馈调整邮件质量诊断“三大场景全阶段脚本模板”中每阶段顶部控件：`当前模板目的说明 + 输入框 + 保存目的 + 发送日期 / 间隔说明 + 输入框 + 保存发送日期` 强制同一行展示。
- 修复点：动态渲染区不再依赖 Tailwind 任意 grid 列宽类，改为明确 inline CSS grid，并给输入框、按钮和标签设置不换行宽度，避免退回 4 行。
- 验证：`frontend/index.html` 内联脚本抽取后 `node --check` 通过；`git diff --check -- frontend/index.html` 通过。

## 2026-06-05 第一个场景第1阶段商业模板精细化

- 已严格修改第一个场景 `new_business_promotion`（老客户其他业务介绍）第 1 阶段模板。
- 生产脚本已从简短两段改为强约束商业 SOP：邮件目标、必须使用的数据、知识库/同行业案例使用规则、4 段正文结构、禁止内容和合格标准。
- AI 指令已补强：要求 4 段左右、必须承接 CRM 事实、必须说明翻译以外至少 3 类业务线、必须使用知识库/黄金范例/同行业经验作为商业证据、禁止价格/折扣/账期/工期/免费服务等未经审核承诺。
- 已新增单模板目标版本：仅 `new_business_promotion + suite_step=1` 升级到 version 31，其他阶段保持现有 version 30，避免扩散重写。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；轻量导入确认第 1 阶段 version 31、第 2 阶段仍为 30，且模板包含“知识库”和“4 段”硬约束。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 第一个场景第1阶段标题/目的/发送说明商用优化

- 已继续优化 `new_business_promotion` 第 1 阶段的三个顶部字段：阶段标题、当前模板目的说明、发送日期 / 间隔说明。
- 阶段标题从通用“破冰与低压力价值提示”改为场景专属“老客户多业务破冰与低压力价值提示”，避免与老客户激活、新客户开发混用。
- 目的说明补强为 4 封套装开场定位：承接老客户历史合作，介绍翻译以外的同传/会议支持、多媒体本地化、排版印刷、活动物料、海外内容适配，并要求结合客户行业、CRM 历史和知识库/同行业案例。
- 发送说明补强为第 1 天发送策略：亲和破冰、不急于报价成交，并明确为第 2 封同行业案例、第 3 封组合方案、第 4 封评估/转介绍收口做铺垫。
- 生产脚本和 AI 指令同步补充用户 8 条要求：4 封层层递进、多业务开发、客户行业、客户历史、亲和语气、结尾转介绍、读取知识库/同行业案例、首封只打开多业务话题避免与后续重复。
- 该单模板目标版本从 31 升至 32，仍只覆盖 `new_business_promotion + suite_step=1`，不扩散更新其他 11 个模板。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；`SKIP_DB_PATCH=1` 轻量导入确认 version 32、新标题、新目的说明、新发送说明，并确认脚本包含 4 封套装、知识库、转介绍、后续阶段递进约束。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 第一个场景第1阶段数据库模板实际保存

- 用户反馈页面仍显示旧内容；已确认原因：此前改的是代码默认模板和自动升级规则，数据库 `mail_sequence_template` 中 `new_business_promotion + suite_step=1` 仍为 version 30 旧行。
- 已实际执行单行升级，把数据库该模板保存为 version 32；未更新其他 11 条模板。
- 本地 API `http://127.0.0.1:8071/api/v1/mail/sequence-templates` 已返回新标题、新目的说明、新发送说明、生产脚本和 AI 指令。
- 需要页面端点击“刷新模板”或重新加载页面；如果访问的是非 8071 的另一台服务/域名，则需确保该服务连接同一数据库并加载同一接口。

## 2026-06-05 第一个场景第2阶段模板完成并保存

- 已完成第一个场景 `new_business_promotion` 第 2 阶段模板，定位为“同行业案例证明与历史合作承接”。
- 已优化顶部字段：标题改为 `第 2 封：同行业案例证明与历史合作承接`；目的说明强调承接第 1 封，用客户行业、CRM 历史合作和知识库/同行业案例证明多业务组合；发送说明明确第 8 天、间隔 7 天、用证据增强可信度但不进入报价或完整方案。
- 生产脚本已改为商业 SOP：邮件目标、必须使用的数据、4 段正文结构、禁止内容、合格标准；要求区分 CRM 历史事实与知识库案例，避免把同行业案例写成当前客户历史。
- AI 指令已补强：必须使用 CRM/行业/历史/知识库证据，必须覆盖翻译以外至少 2 类业务，必须有低压力下一步和转介绍，禁止价格/折扣/账期/工期/免费承诺。
- 已将 `new_business_promotion + suite_step=2` 目标版本设为 31，并实际保存数据库该行；其他模板不被本轮覆盖。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；数据库查询和本地 8071 API 均确认第 2 阶段返回 version 31、新标题、新目的说明、新发送说明和新脚本。

## 2026-06-05 1-1/1-2 AI 指令变量使用规则补齐

- 用户指出已改的“给 AI 的指令脚本”缺少变量位置和变量说明。已补齐 `new_business_promotion` 第 1、2 阶段 AI 指令中的变量使用规则。
- 新增统一变量规则：`{customer_name}` 放开头称呼；`{company_name}` 用于客户背景；`{industry}` 用于行业场景和案例选择；`{history}` 用于真实历史合作/商机/跟进；`{peer_case}` 只能作为知识库/同行业案例；`{business_lines}` 自然融入多业务段；`{seller_name}` 只作落款/轻介绍；`{referral_request}` 用于结尾转介绍。
- 明确缺失处理：变量为空时必须自然中文降级，不得输出 `{customer_name}`、`unknown`、`None`、空括号或系统字段名。
- 代码默认值已更新，并通过 8071 的 `PUT /api/v1/mail/sequence-templates/new_business_promotion/{1,2}` 实际保存到页面读取的数据库行。
- 本地 8071 `GET /api/v1/mail/sequence-templates` 验证：第 1 阶段 version 34、第 2 阶段 version 33，二者均包含“变量位置与使用规则”、`{customer_name}`、`{peer_case}` 和“禁止把变量名原样输出”。

## 2026-06-05 三场景十二封商用模板全量完成

- 已按用户要求把剩余场景和邮件全部按同一标准完成，覆盖三大场景 × 4 封 = 12 封，不遗漏。
- 已在 `backend/main.py` 新增商用模板生成器：按场景画像（老客户其他业务介绍、老客户激活、新客户开发介绍）和阶段画像（开场破冰、证据增强、方案路径、低压力收口）生成标题、目的说明、发送说明、生产脚本和 AI 指令。
- 每封模板均包含：4 封层层递进、多业务开发、客户行业、客户历史/CRM 事实、知识库/同行业案例、亲和语气、结尾转介绍、变量位置与缺失处理、禁止价格/折扣/账期/工期/免费服务、当前客户历史与知识库案例边界。
- 已实际保存数据库 12 行，统一 version 40，`updated_by=codex_commercial_all_templates_v40`。
- 已验证单场景逻辑无矛盾：
  - `new_business_promotion`：多业务破冰 -> 同行业案例证明 -> 多业务组合方案 -> 评估/预算/转介绍收口。
  - `re_activation`：关系重启 -> 历史合作与案例唤醒 -> 低门槛协作路径 -> 资料评估/服务清单/转介绍收口。
  - `new_contact_intro`：公司介绍与正确对接确认 -> 行业经验建立可信度 -> 项目启动路径 -> 小范围评估/负责人确认/转介绍收口。
- 验证：`backend/main.py` AST 解析通过；`git diff --check -- backend/main.py` 通过；本地 8071 API `GET /api/v1/mail/sequence-templates` 校验 12 封均为 version 40，均包含变量规则、知识库、转介绍、价格禁区、历史/案例边界；专项逻辑校验通过。`python -m py_compile backend/main.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 企微后续评分北京时间窗口限制

- 已新增企微后续评分时间窗配置：`WECOM_FOLLOWUP_SCORING_WINDOW_ENABLED=true`、`WECOM_FOLLOWUP_SCORING_WINDOW_START_HOUR_BJ=20`、`WECOM_FOLLOWUP_SCORING_WINDOW_END_HOUR_BJ=24`，默认只允许北京时间 20:00（含）到 24:00（不含）执行；本轮不要求修改服务器 `.env`，也不把 `.env.example` 作为服务器必更文件。
- 已在 WeCom API 调用后续评分的三个入口加门控：30 分钟后台补算 worker、`_refresh_api_invocation_quality()` 手动/补算刷新、`_complete_api_reply_scoring_async()` 响应返回后的异步评分补齐。
- 窗口外不会提交新的异步评分任务，也不会执行原始回复分、相似分、候选回复评分或训练 AI 评分补算；已有未评分记录保持待补状态，等 20:00-24:00 窗口内继续计算。
- 验证：`backend/main.py`、`backend/config.py` AST 解析通过；`git diff --check -- backend/main.py backend/config.py` 通过；时间窗函数验证输出为 `19:59=False`、`20:00=True`、`23:59=True`、`00:00=False`。`python -m py_compile backend/config.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 邮件质量诊断模板三列编辑与空邮箱限制移除

- 已将邮件质量诊断页的“三大场景全阶段脚本模板”改为每阶段三列编辑布局：目的/发送日期、变量说明+生产脚本模板、给 AI 的指令脚本，文本框限制最大约 20 行高度，减少页面纵向滚动。
- 已新增 `mail_sequence_template.ai_instruction_script` 字段，启动期自动补列；`GET/PUT /api/v1/mail/sequence-templates` 支持读取和保存给 AI 的指令脚本，并注入邮件草稿 LLM Prompt。
- 已移除空邮箱占位限制：当前 3 案例、独立客户套装页和后台迭代不再合成 `customer.test` 或 `mailmock.test` 收件邮箱；CRM 邮箱为空时保持空值，只生成草稿模板，不做收件域名校验、不补造邮箱、不发信。
- 验证：`backend/main.py`、`backend/database.py` AST 解析通过；`frontend/index.html` 内联 JS `node --check` 通过；定向 `git diff --check -- backend/main.py backend/database.py frontend/index.html` 通过；`SKIP_DB_PATCH=1` 导入 `main` 并确认相关邮件路由注册通过。`python -m py_compile backend/main.py backend/database.py` 仍因既有 `backend/__pycache__` 权限拒绝失败。

## 2026-06-05 邮件质量诊断当前案例 CRM 未脱敏查询

- 已按用户要求把邮件质量诊断当前 3 个案例改为实时只读查询 CRM 原始信息，不再在该案例区显示“脱敏”字段；旧 5 个保留案例和其他页面的脱敏逻辑不改。
- 已确认 3 个产品指定编号在 CRM 中实际对应 `usrCustomerContact.ContactId`：`KH15411-117`、`KH02659-011`、`KH13770-006` 均可命中真实联系人和公司。
- `GET /api/v1/mail/demo-contacts` 现在合并返回未脱敏字段：联系人、公司、邮箱、ContactId、CustomerId、联系人/客户状态、销售/负责人、行业、生命周期、客户级别、欠款风险、最近 3 条商机、最近 3 条合同、最近 5 条跟进。
- 已同步修正草稿生成 CRM 查询条件，把 `ContactId`、`NewContactId`、`NewCustomerId` 纳入查找，避免卡片能查到但点击生成草稿时查不到。
- 第二个案例 `KH02659-011` 的 CRM 邮箱为空；页面展示真实空值，同时生成表单内部使用独立占位邮箱，仅用于草稿生成链路，不真实发信。
- 验证：直接调用 `_fetch_mail_current_case_crm_detail()` 对 3 个 KH 编号均返回 `matched_crm_contact_id_or_customer_id` 且公司名非空；`backend/main.py`/`backend/database.py` AST 通过；`frontend/index.html` 内联 JS `node --check` 通过；定向 `git diff --check -- backend/main.py frontend/index.html` 通过；`SKIP_DB_PATCH=1` 导入 `main` 并确认 `/api/v1/mail/demo-contacts` 路由注册成功。`python -m py_compile backend/main.py backend/database.py` 仍因既有 `backend/__pycache__` 权限拒绝写 pyc 失败。

## 2026-06-05 训练AI与知识库检索迁移至 Ollama 11486 端口

- 已将 `.env` 配置文件中的 `TRAIN_AI_BASE_URL` 改为 `http://zjsphs.2288.org:11486`，`TRAIN_AI_MODEL` 改为 `unsloth-qwen2.5-task-60`，`TRAIN_AI_API_KEY` 置空。
- 已将 `.env` 配置文件中的 `EMBEDDING_API_URL` 改为 `http://zjsphs.2288.org:11486`，且确认对应的 embedding 模型 `qllama/bge-m3:latest` 命中无误。
- 已将 `backend/config.py` 中的对应配置默认值同步更新。
- 重构了 `backend/main.py` 中的 `_train_ai_list_models` 函数，将其切换为直接请求 Ollama 原生 `/api/tags` 接口并返回匹配前端格式的模型列表。
- 重构了 `backend/main.py` 中的 `_train_ai_chat` 函数，将其切换为直接请求 Ollama 原生 `/api/chat` 接口，支持 `options` 字段以传递 `temperature` 和 `num_predict` (对应 `max_tokens`)，并解析返回结构。
- 验证：`.env`、`backend/config.py`、`backend/main.py` 的 AST 解析及 Python 语法校验全部通过。`git diff --check` 定向格式检查通过。编写了直连测试脚本对 Ollama 11486 端口的 tags 与 chat 接口进行了完整验证，返回结果完全正确。

## 2026-06-05 邮件套装反馈记录节点

- 已确认独立套装页 `/static/mail-suite.html` 的反馈设计为“每次保存反馈 = `mail_customer_suite_feedback` 一条新记录”；本轮补齐当前工作区缺失的后端 POST 保存路由，避免前端保存调用落空。
- 已新增 `GET /api/v1/mail/customer-suite-feedback` 查询接口，支持按客户编号、业务场景、套装阶段和 limit 查询，返回完整反馈、对应草稿主题/正文、草稿 payload、客户画像和联系人摘要。
- 已补齐 `GET /api/v1/mail/customer-suite` 路由：浏览器直开 API 会跳转到独立页面；JSON 调用会按客户编号和场景串行生成 4 封套装草稿，仍保持 `real_sending_enabled=false`。
- 已把 `/static/mail-suite.html` 加入前端认证免登录白名单，确保独立客户套装页可直接访问。
- 已在邮件质量诊断工作台新增“反馈记录”子节点，提供客户编号/场景/阶段/条数筛选、刷新、列表、完整详情展开；详情中展示完整反馈、对应邮件主题正文、草稿 JSON、客户画像 JSON 和联系人信息，便于人工验证。
- 验证：`backend/main.py`、`backend/database.py` AST 解析通过；`frontend/index.html` 内联脚本抽取后 `node --check` 通过；定向 `git diff --check -- backend/main.py frontend/index.html backend/database.py` 通过；`SKIP_DB_PATCH=1` 导入 `main` 成功并确认 3 个 customer-suite 路由注册。`python -m py_compile backend/main.py backend/database.py` 仍因既有 `backend/__pycache__` 权限拒绝写 pyc 失败，未改权限。

## 2026-06-05 邮件质量诊断案例与脚本模板调整

- 已将邮件质量诊断页的当前显示/测试案例从旧 5 个切到 3 个产品指定客户编号：`KH15411-117`（老客户多业务）、`KH02659-011`（老客户激活）、`KH13770-006`（新客户）。原 5 个 `mail_demo_contact` 旧案例保留，新增字段用于区分当前测试集合。
- 已新增 `mail_sequence_template` 表模型与启动期自动补表逻辑，按 3 个邮件场景 × 4 个阶段独立保存脚本模板、目的说明、发送日期说明、变量说明。
- 已新增后端接口 `GET /api/v1/mail/sequence-templates` 与 `PUT /api/v1/mail/sequence-templates/{scenario}/{suite_step}`，支持单独保存每个阶段的目的、发送日期或脚本模板；保存后的模板会进入邮件草稿 LLM Prompt。
- 已将邮件迭代运行范围改为当前 3 案例 × 4 步 = 12 封，页面文案同步从旧 5×4=20 调整为 3×4=12。
- 前端 `frontend/index.html` 已在绿色真接后端演示区新增折叠的“三大场景全阶段脚本模板”面板，可按场景切换查看 4 个阶段，展示变量说明，并分别保存目的、发送日期和脚本。
- 验证：`backend/main.py`、`backend/database.py` AST 解析通过；`frontend/index.html` 内联脚本抽取后 `node --check` 通过；`git diff --check -- backend/main.py backend/database.py frontend/index.html` 通过。`python -m py_compile backend/main.py backend/database.py` 仍因既有 `backend/__pycache__` 权限拒绝写 pyc 失败，未改权限。

## 2026-06-04 独立客户套装邮件页实现

- 已新增无需登录的独立页面 `frontend/mail-suite.html`，访问形态为 `/static/mail-suite.html?id=KH23447-001`。页面不包含跳转现有工作台/其他页面的快捷入口。
- 已新增 `GET /api/v1/mail/customer-suite?id=...`：按客户编号读取 CRM 画像，自动判断三类邮件场景之一，并复用现有邮件草稿生成链路一次生成 4 封套装邮件；真实发信仍关闭。
- 已新增 `POST /api/v1/mail/customer-suite-feedback`：每封邮件旁边可填写反馈并保存，每次保存新建一条反馈记录。
- 已新增反馈表模型 `mail_customer_suite_feedback`，并在 `auto_patch_db()` 中加入 `CREATE TABLE IF NOT EXISTS` 与索引创建，便于生产重启后自动补表。
- 验证：`backend/main.py`、`backend/database.py` AST 解析通过；`frontend/mail-suite.html` 内联脚本抽取后 `node --check` 通过；定向 `git diff --check -- backend/main.py backend/database.py frontend/mail-suite.html` 通过。
- 本轮未启动服务、未调用 LLM、未实际访问 CRM 生成邮件；需要部署重启后用真实客户编号在页面端到端确认。
- 2026-06-04 追加修正：浏览器直开 `/api/v1/mail/customer-suite?id=...` 会自动跳转到 `/static/mail-suite.html?id=...`，避免显示 JSON 中间页；套装生成不再要求真实联系人邮箱，无邮箱时使用内部占位收件地址仅供草稿链路运行，页面显示“仅生成模板，不发邮件”；页面顶部和状态样式已调整为与现有工作台更一致的白色顶栏、紫色主色和处理中 spinner。

## 2026-06-04 邮件 V8 有效复测完成

- 已完成邮件 V8 有效复测，最终有效记录为 `mail_iteration_run` v14（run_id `ecf5a1aa-7c08-4779-aec7-ea1b3bfc2609`），20/20 成功，均分 99.2，最低 96，最高 100，平均耗时 7577ms。
- 已修复邮件草稿 LLM 请求被系统代理劫持的问题：`backend/main.py` 的邮件草稿 LLM 请求改用 `requests.Session()` 且 `trust_env=False`。
- 已新增邮件草稿专用 LLM 配置：`MAIL_DRAFT_LLM_API_URL`、`MAIL_DRAFT_LLM_API_KEY`、`MAIL_DRAFT_LLM_MODEL`、`MAIL_DRAFT_LLM_TIMEOUT_SECONDS`、`MAIL_DRAFT_LLM_TEMPERATURE`，未配置时回落到现有 `LLM2_*`。
- 已强化重复签名控制：Prompt 明确禁止 LLM 输出落款/签名，后端统一追加签名前会清理 LLM 段落末尾误写的销售签名。
- 结果分析见 `logs/mail-v8-analysis.md`。本轮失败的 v8-v12 均为环境/端口/模型出口诊断记录，最终质量结果以 v14 为准；邮件真发仍未启用。
- 2026-06-04 用户页面复核修正：v14 不能判定已解决最初邮件质量问题。v14 与 v7 页面正文肉眼差异很小；正文仍缺少直接、明确、稳定运用知识库案例段；案例1老客户仍主要围绕翻译/本地化，没有把同传、多媒体本地化、排版印刷等新业务作为明确主推。后续迭代必须以页面可见正文结果为验收标准，而不是均分、段落数、关键词命中等指标。
- 调用环境说明：v14 是本机临时高端口服务触发，用来确保加载当前工作区最新代码；不是直接调用生产 `api.speedasia.net`。因此 v14 只说明本机最新代码链路跑通，不能等同于生产页面结果已改善。

## 服务端更新清单（本会话 v1.7.164~230）

**已入库代码（服务器 git pull 即可）：**
- `backend/main.py`：
  - 邮件 Prompt 一致性与篇幅优化（v1.7.236）：将知识库同行业案例、范例参考、当前客户历史跟进拆成独立 Prompt 区域，禁止知识库内容混入历史跟进；新增 `target_product_line` / `existing_business_lines`，新业务推广时明确本次目标新业务并禁止把客户已有旧业务当作主推内容；放宽正文段落硬限制，要求按业务叙事传达清晰商业价值。
  - 启动期 DB 补丁防卡死（v1.7.235）：`auto_patch_db()` 在 PostgreSQL 下增加 advisory lock、`lock_timeout=2s`、`statement_timeout=20s` 和异常回滚/关连接；`message_logs(timestamp)` 与 `(user_id,timestamp)` 日期索引改为事务外 `CREATE INDEX CONCURRENTLY`，避免服务器更新后长时间等待 DDL 锁导致启动慢。
  - 账号受限视图（v1.7.232）：新增 `hj` 登录账号，角色为 `mail_quality_only`；`/api/auth/login` 与 `/api/auth/me` 返回 role，供前端裁剪页面入口。
  - 清理动态案例兜底硬编码（v1.7.230）：移除了 `_get_mail_industry_case_study_from_db` 中的硬编码兜底案例段落，无匹配时直接返回空字符串，完全清除假数据。
  - 核心 WeCom 后台评分补算 worker 热修复（v1.7.208）：引入 SQL `exists` 子查询智能过滤无销售回复会话，解决饥饿队列；移动 `db.commit()` 到 loop 内部，在 time.sleep 前即时提交，彻底消除 87.6 秒的数据库行锁等待延迟；修复 logger 报错。
  - 贯彻“宁报错或为空”原则，彻底注释掉漏网的 8 处 A 类/B 类 fallback 兜底（v1.7.207 & v1.7.209），暴露真实上游错误。
  - 邮件系统 Phase 5 真实大模型两阶段生成接入，并在 v1.7.206 切换为 DeepSeek-Chat，保留占位符防幻觉物理隔离（v1.7.198）。
  - 新增邮件迭代记录与草稿 7 维打分落库模块（v1.7.205）。
  - 邮件生成优化（Task 80）：添加新 B2B 画像字段，重构 Prompt 防范 Few-Shot 抄袭。恢复 `_mail_crm_profile_from_demo_contact_table` 的路由与完整字段解析，修复 demo 客户 key 报 404 的问题。
  - 本地服务搭载：使用 `SKIP_DB_PATCH=1` 绕过 DDL 死锁启动 8071 服务，并成功触发、跑通**邮件迭代 v6**（20/20 全量生成成功，均分 97.2，已全部落库并显示于前端面板）。
  - 时区配对修复、评分异步、盲评对、训练AI model下拉保存。
- `frontend/index.html`：
  - hj 邮件页权限调整（v1.7.234）：`hj` 账号允许点击并查看“质量诊断 / 邮件迭代记录 / 黄金范例库”三个子页，仅隐藏“邮件配置”和“返回企微实时智能”。
  - 账号受限视图修正（v1.7.233）：修复邮件子导航点击/渲染时 `className` 覆盖 `hidden` 的问题；`hj` 账号下“邮件迭代记录 / 黄金范例库 / 邮件配置”会在每次切页后重新隐藏。
  - 账号受限视图（v1.7.232）：`mail_quality_only` 登录后只显示“邮件质量诊断”主节点；邮件页内只保留“质量诊断”子页，隐藏“邮件迭代记录 / 黄金范例库 / 邮件配置 / 返回企微实时智能”，并在切页函数中强制回到质量诊断。
  - 全面上线邮件工作台，包含：“邮件迭代记录”列表与 20 封详情面板（v1.7.205），“黄金范例库” 25 条种子探索面板（v1.7.206），绿色动态 “Live Demo” 生成与表单交互区（v1.7.198）。
  - 界面全面中文化（v1.7.200 - v1.7.203），优化 180+ 处详细浮动 tooltip 诊断提示。
- `backend/seed_mail_gold_candidates.py`（NEW）：Task 76 黄金库 25 条种子自动幂等灌库脚本（v1.7.198）。
- `backend/database.py`：新增 mail_iteration_run 与 mail_iteration_draft 评分与 prompt 数据库表（v1.7.205）。
- `backend/crm_profile.py`：修复 CRM 生命周期配置 `RecentMonths` 日期计算（v1.7.236），在 Python 端算出真实 datetime 范围并传 SQL，不再把 `RecentMonths` / `6` 直接作为字符串参与日期比较。
- `backend/mail_sequence_strategy.py`：三套邮件 Sequence 的 `objective` 与 `cta_style` 已中文化（v1.7.236），并修正新业务推广步骤中的中英文混杂描述。
- `backend/seed_mail_demo_contacts.py`（NEW）：5 个 CRM 真实联系人画像灌库与校验脚本（v1.7.202）。
- `scratch/overwrite_529_scores.py`（NEW）：WeCom 5.29 质量评分本地语义化重算与离线回写脚本，全量覆盖 68 条有销售回复记录（v1.7.220）。
- `logs/dod-task76-78.md`（NEW）：Task 76/77/78 真接入端到端 DoD 演示证据（v1.7.198）。
- `HOWTO_VERIFY_MAIL_AI_REPLY.md`（NEW）：人工最终验证邮件草稿质量的操作指南（v1.7.199）。
- `项目进展.md`：追加入库 v1.7.176 ~ v1.7.220 共三十多个版本进展，无一漏网。


**需在服务器手工处理（gitignore，不入库）：**
- 失败（网络/模型临时断开等）如实写入 `logs/codex-run.log` 和 `logs/codex-retry.log`，由 cron 周期自动重试，不丢任务，严禁"假绿"。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron `last_status` 为准。
- 查看：`hermes cron list` / `hermes cron status` / `~/.hermes/cron/output/<job_id>/`。

## 2026-06-08 hj 受限账号登录修复

- 已修复前端工作台认证后端只支持单一 `admin` 账号的问题，新增 `FRONTEND_AUTH_EXTRA_USERS` 配置并默认包含 `hj:123456:mail_quality_only`。
- `/api/auth/login` 现在会返回 `role`，`/api/auth/me` 也会返回登录用户角色；前端既有 `mail_quality_only` 限制逻辑可据此生效。
- `hj` 账号登录后会被限制在邮件质量工作台，按现有前端逻辑可查看质量诊断、邮件迭代记录、黄金范例库、反馈记录，并隐藏邮件配置及返回企微入口。
- 验证：`git diff --check -- backend/main.py backend/config.py .env.example` 通过；`backend/main.py`、`backend/config.py` AST 解析通过；FastAPI TestClient 验证 `hj / 123456` 登录返回 `role=mail_quality_only`，`/api/auth/me` 返回同一角色；`admin / Qw@2026` 登录仍返回 `role=admin`。
- 注意：`python -m py_compile backend/main.py backend/config.py` 在当前 Windows 环境仍因 `.pyc` 写入/rename 权限拒绝失败，本轮采用 AST 解析和接口级 TestClient 验证补足。

## 2026-06-08 邮件 V15 训练案例结果生成

- 已按最新当前邮件案例与 v40 商用脚本模板生成 `mail_iteration_run` V15，run_id 为 `226aa34b-2d47-4115-9ee8-ab49bc6a302b`。
- 本轮只涉及邮件链路：当前 3 个邮件案例 × 4 个 Sequence Step = 12 封草稿；V14 保留为历史结果，未覆盖、删除或改写。
- V15 最终状态：`success`，12/12 成功，LLM 成功 12/12，fallback 0，平均分 94.50，最低 90.00，最高 96.00，真实发信仍关闭。
- 修复了邮件迭代后台把 `***EMAIL***` 脱敏占位邮箱当作真实邮箱导致 422 的问题；邮件当前案例/迭代生成遇到脱敏占位或无效邮箱时归一为空邮箱，沿用空邮箱只生成草稿模板的既有规则。
- 邮件草稿 LLM 请求改为使用 `requests.Session()` 且 `trust_env=False`，避免本地代理环境劫持 DeepSeek 请求。
- 结果分析已写入 `logs/mail-v15-analysis.md`；8071 本地后端已恢复，可通过 `/api/v1/mail/iterations?limit=1` 查看 V15。

## 2026-06-08 邮件 V16 案例1问题修复与有效复测

- 已按用户反馈修复 V15 案例1问题：邮件侧 prompt 不再重复塞入完整脚本和完整 AI 指令，改为优先强调联系人、公司、行业画像、CRM 历史/商机/跟进和检索案例。
- 已新增邮件 prompt 脱敏清理：合同、报价、客户编号等内部编号在进入 LLM 前改写为“历史合作记录”“近期商机记录”“内部记录”，避免出现 `合同 XS260601-012` 这类内部编号。
- 已将三大场景 × 4 阶段商用模板升级到 v41，脚本与 AI 指令合并去重并明确 4 封递进：破冰、案例证据、方案路径、低压力收口。
- V16 run `af3bd9de-2044-4d9b-80a8-eaf2a72ae1e0` 已成功生成 12/12，但案例1 prompt 约 1301-1313 字，仍略超用户要求的 800-1200。
- 已继续压缩模型输入并完成有效复测 V18：run `e3b8f956-cbac-4126-b3ea-5d19ddf6ce3b`，12/12 成功，fallback 0，均分 98.17；全量 prompt 958-1009 字，内部编号检查 0 命中。
- V18 场景区分正常：案例1 `new_business_promotion`、案例2 `re_activation`、案例3 `new_contact_intro`，每个客户 4 封套装，阶段定位分别为破冰、证据、路径、收口。
- 结果分析已写入 `logs/mail-v16-v18-analysis.md`。本轮未改企微/微信链路，邮件真发仍关闭。

## 2026-06-08 邮件 V21 后续修正（未跑 V22）

- 按用户校准：案例中已有的周期、速度、字数表达可以保留，不再把“在两周内交付”等案例事实误判为无来源工期。
- 已强化免费/无偿服务出口替换，避免生成“免费提供样稿”“免费试译”“免费服务”等未审核承诺。
- 已增强 `new_contact_intro` 第 1 封：要求写出 SpeedAsia 身份、客户行业相关的 3 项差异化服务组合、正确负责人确认或转介绍，不再只是简单公司介绍。
- 已将素材缺口提示改为明确说明缺哪类案例或样本：如新联系人首次介绍样本、同行业脱敏案例、项目启动路径样本等。
- 未触发 V22；验证仅执行 `backend/main.py` AST 和定向 `git diff --check`。

## 2026-06-08 邮件 V22 测试与后续压缩修正

- 已触发邮件 V22 真生成测试，run_id `29d7591c-ac1b-4193-8be7-079269227de8`，run_label `mail_v22_docx_communication_playbook_v45`。
- V22 范围仅邮件：当前 3 个案例 × 4 个 Sequence Step = 12 封；未改企微/微信链路；真实发信仍关闭。
- V22 最终状态：`success`，12/12 成功，LLM 成功 12/12，fallback 0，平均分 96.33，最低 86，最高 100。
- 正文与主题检查：内部编号、免费/无偿/试译/样稿、微信/企微、价格/折扣/账期、直接索要联系人电话邮箱均 0 命中。
- V22 不完全达标：真实 prompt 长度 1359-1612，超过此前 800-1200 要求。
- 已继续压缩当前代码中的 CRM 事实、黄金范例引用、系统提示和沟通过程规则；未篡改 V22 已落库结果。
- 修正后用 monkeypatch 拦截 LLM 做 prompt 预检，不新建 V23：12 封 prompt 979-1192，平均 1117.4，满足 800-1200。
- 分析记录见 `logs/mail-v22-analysis.md`。

## 2026-06-09 邮件 V23 docx playbook 收口与前台可见测试

- 已按 4 个 `邮件AI案例*.docx` 的沟通过程逻辑，把邮件脚本收口为 docx playbook 版本：行业感+轻商务、岗位切口、当前联系人历史不当案例、转介绍先问团队、不直接索要联系人。
- 已清理邮件前台和后端旧口径：`临门样稿`、`样稿评估`、`新增的本地化服务能力` 不再出现在邮件主链路；前端步骤改为破冰、行业案例、协作路径、低压收口。
- 邮件模板目标版本升级到 v46，并通过 `_ensure_mail_sequence_templates()` 写入数据库。
- 已触发 V23 真实生成，run_id `76c24b64-ecd3-4feb-b37f-55b12faf82b2`，run_label `mail_v23_docx_playbook_v46_frontend_visible`。
- V23 当前为前台最新可见版本：`mail_iteration_run.version_no=23`。
- V23 最终状态：`success`，12/12 成功，LLM 成功 12/12，fallback 0，平均分 96.67，最低 90，最高 100。
- prompt 长度 979-1192，平均 1117.4，满足 800-1200。
- 首次 V23 生成后发现案例2第4封出现 `试译样稿`，以及部分正文有无审核周期表达；已补充出口清洗并更新同一 V23 明细，不新建 V24。
- 最终复查：内部编号、免费/无偿/试译/样稿、微信/企微、直接索要联系人电话邮箱、价格/折扣/账期、旧口径、无审核周期表达均 0 命中。
- 分析记录见 `logs/mail-v23-analysis.md`。
- 2026-06-09 继续按用户反馈调整邮件排版：新增正文归一化，称呼段单独输出为 `<p>Michelle 您好，</p>` 这类独立段落，正文从第二段开始，按自然段保留，不再按固定 4 段写死。
- 已对 V23 已落库 12 封执行仅排版更新，不新建 V24；复查 12/12 第一段均为称呼段，0 个孤立标点段，禁用词/旧口径/周期表达仍 0 命中。

## 2026-06-09 检索与Agent流程优化

- **已完成检索与 Agent 流程的四大优化**：
  1. **Cross-Encoder 物理重排序与 RRF (Reciprocal Rank Fusion)**：
     - 新建了 `backend/reranker.py`，实现了本地轻量级词法（Jaccard & 词共现）重排序，结合向量 Cosine 相似度进行二阶段重排；支持 RRF 混合检索融合算法。
  2. **多轮对话上下文改写 (Query Rewriting)**：
     - 在 `backend/intent_engine.py` 的 `retrieve_knowledge_v2` 中增加了 `rewrite_query_v2`，利用对话历史还原指代和省略，确保检索精准度。
  3. **Agent Builder 叠窗切分 (Chunk Overlap)**：
     - 在 `backend/agent_builder/router.py` 的 `upload_knowledge` 接口中，支持了基于 `AGENT_BUILDER_CHUNK_OVERLAP` 设定大小的段落级滑动叠窗切分，防止跨边界信息丢失。
  4. **Active Planning 意图规划与 Reflection 自检反思**：
     - 在 `backend/agent_builder/engine.py` 中实现了 `extract_slots_from_message` 前置规划出 `planned_intent` 与 `requires_knowledge_lookup` 槽位，按需进行 RAG 查询。
     - 实现了生成后的反思拦截（Reflection），物理重置未经授权的分期推销，并自动校准价格幻觉（如将 iPhone XR 非 300万 价格强行纠偏）。
- **验证通过**：
  - 新建了 `backend/optimizations_checks.py` 单元测试，覆盖 RRF、本地词法重排、上下文改写、Agent Planner 意图与反思纠偏（分期拦截与价格修正）、滑动窗口叠窗等 6 个核心测试用例，运行 100% 通过（`OK`）。
  - 对 `backend/mail_review_api_interface_checks.py` 进行了兼容性修复（适配 `_mail_generate_draft_fewshot` 的最新签名），全量运行 11 个 `mail_*_checks.py` 测试文件，均成功通过。
  - 所有改动文件的 `git diff --check` 和 `py_compile` 语法与格式检查均通过，无行尾空白。

## 2026-06-09 邮件合同案例库数据脱敏与精炼案例文本优化

- **已完成任务**：对合同案例库中100条原始合同候选进行了深度的企业名称脱敏与优雅推广案例生成优化，完全满足邮件开发信调性与50字限制。
- **改动文件**：
  - [main.py](file:///d:/items/QW/backend/main.py)：
    - 扩充了 `_desensitize_company_name`，针对30余家特定大客户（如 Allspring, CHAGEE 霸王茶姬, Burberry 博柏利, BD 碧迪, 拜耳, Covestro 科思创, KPF, Bureau Veritas 必维, Dörken 德尔肯, TOTO 东陶, Grohe 高仪, TUV 南德, Edwards 爱德华等）与高风险/特急标记做精准的行业化脱敏。
    - 优化了 `_generate_mail_case_text` 的文本生成规则，针对笔译、口译（同传/陪同/常规）、设计印刷（联单/易拉宝/包装/画册/排版）、多媒体译制（录制/听译）、展会搭建、商务礼品（风扇/充电宝/保温杯/环保袋）等各种细分类型设计了精炼、优雅的邮件首句案例推广模板。
    - 调整了 `_mail_contract_case_business_line` 中业务线的匹配优先级，使特定度更高的“展会搭建 (exhibition)”与“商务礼品 (gift)”优先于通用印刷和翻译匹配。
- **验证结果**：
  - 编写了独立的单元测试 [mail_contract_case_candidates_checks.py](file:///d:/items/QW/backend/mail_contract_case_candidates_checks.py)，对企业名称脱敏、业务线优先级判定、精炼案例的字数（严格 <= 50 字）和脱敏漏标进行了全方位测试，100% 通过（`OK`）。
  - 创建并运行了 `scratch/test_case_texts.py` 测试脚本，拉取 CRM 实测 100 条合同数据生成的文本，行数 100%，全部字符长度完美控制在 50 字内且完成脱敏。
  - 改动已通过 `git diff --check` trailing whitespace 检查。

## 2026-06-09 邮件草稿 LLM 选择器与 ChatGPT 接入

- 已在邮件配置台新增“邮件草稿模型选择”，与现有范例检索/大模型参数区域联动，支持查看当前生效 provider、刷新配置、测试连通性和切换生成模型。
- 后端新增邮件专用 LLM provider 配置：`deepseek` 复用现有 `LLM2_*`，`openai` 支持 `MAIL_DRAFT_OPENAI_*`，并兼容 `RECORDING_PARSE_OPENAI_VISION_API_URL` / `RECORDING_PARSE_OPENAI_VISION_API_KEY` 作为别名。
- 新增接口：`GET /api/v1/mail/draft-llm-config`、`PUT /api/v1/mail/draft-llm-config`、`POST /api/v1/mail/draft-llm-config/test`；接口不返回、不记录 API Key。
- 邮件草稿真实生成链路 `_call_llm2_json_for_mail_draft()` 已改为按当前 provider 调用，选择 ChatGPT/OpenAI 后会使用 OpenAI Chat Completions JSON 输出；仅影响邮件草稿，不影响企微/微信链路。
- 本地 TestClient 验证通过：默认 `deepseek` 已配置；`openai` 代码路径可达，但本地环境未配置 OpenAI Key，因此测试返回 `not_configured`，未执行真实 OpenAI 外呼。
- 出于安全原因，用户在聊天中提供的 API Key 未写入 `.env`、文档、日志或 Git diff；需要人工放入本机环境变量后重启后端，再在前台点击“测试”和“使用此模型”。

## 2026-06-09 邮件 GPT-4.1 文案限制放宽与称呼排版修复

- 已按 `other/邮件AI案例3.docx` 的优秀邮件写法校准邮件草稿 prompt：保留价格、折扣、账期、免费承诺、内部编号、虚构数字等硬安全线，但放开过硬的“第1封不写案例/方案/收口”限制，允许第1封写轻量参考、before/after 类示例、客户可转发理由和低压力下一步。
- 邮件草稿默认生成参数从低温短输出调整为 `MAIL_DRAFT_LLM_TEMPERATURE=0.55`、`MAIL_DRAFT_LLM_MAX_TOKENS=1800`，避免 GPT 写成合规摘要。
- 修复称呼归一化：`Michelle Li 您好：`、`Michelle Li 您好` + 独立 `：`、`Hi Michelle:` 均不会再拆出孤立冒号段。
- GPT-4.1 案例1-1单封实测通过：耗时 13.36 秒，`llm_model_used=openai:gpt-4.1`，`status=drafted`，`real_sending_enabled=false`，正文成功生成且无孤立冒号。

## 2026-06-09 8071 端口后端拉起与接口测试修复

- **8071 端口后端正常拉起**：成功在本地以 `SKIP_DB_PATCH=1` 环境变量绕过 DDL 卡死并拉起 `8071` 端口。目前服务稳定在后台监听，可与前台联调。
- **接口测试 NameError 修复**：排查并解决了 `backend/mail_review_api_interface_checks.py` 中因为 `exec()` 动态加载 `main.py` 导致 `@app.get` 等 FastAPI 装饰器报 `NameError: name 'app' is not defined` 的阻断问题。通过在测试的 `namespace` 中注入 Mock 版本的 `app` 解决。
- **全量测试通过**：本地运行全仓 52 项单元/集成测试用例，均 100% 成功（`OK`），无任何格式与功能 regression.

## 2026-06-09 邮件合同案例库总数与分页跳转

- 已修复合同案例库前端只显示当前页条数、没有页码跳转的问题：页面标题现在展示“当前页条数 / 筛选后总条数”，筛选区下方新增上一页、下一页、页码输入和跳转按钮。
- 后端 `/api/v1/mail/contract-case-candidates` 收敛为单一路由，保留 `page`、`limit`、`total`、`pages`、`analysis` 等字段，避免重复路由返回结构不一致。
- 明确当前下拉“最近 100/200/500 条”只是每页大小，后端单页上限仍是 500；分页后可以查看筛选后的全量合同，不再只能看前 500 条。
- 验证：`python mail_contract_case_candidates_checks.py` 通过；`backend/main.py` 与 `backend/database.py` AST 通过；抽取 `frontend/index.html` 内联 JS 后 `node --check` 通过；定向 `git diff --check -- backend/main.py frontend/index.html` 通过。

## 2026-06-10 CRM 快捷页与企微可发回复输出修复

- 已查明 `KH23447-001` 误显示“广州锴信商务咨询有限公司”的根因：邮件快捷页 CRM 查询在空邮箱情况下仍把 `c.Email=''` 放入 OR 条件，误命中其他空邮箱联系人。
- 已按用户要求收紧为客户编号唯一查询：有 `customer_key` 时只匹配 CRM 编号字段，不再用邮箱或公司名参与 OR；只读验证返回“蒙特空气处理设备（北京）有限公司上海办事处”。
- 已修复知识库 V2 RRF/reranker tuple 下标错误，线上 `tuple index out of range` 已消失，`api.speedasia.net` 真实侧边栏调用返回 `status=success`、`knowledge_status=ok`、`crm_status=success`。
- 已增强企微回复最终清洗：`reply_reference1/2` 只保留可直接发送给客户的正文，剥离 `【摘要档案】`、`【线程推进状态】`、`【当前回复焦点】`、参考回复说明和 JSON 块。
- 线上真实会话复测：两条回复均为纯中文可发文本，无 JSON、无内部分析块、无中文乱码。
- 验证：`backend/intent_engine.py`、`backend/main.py` AST 通过；定向 `git diff --check` 通过；本地清洗小测通过；`python -m unittest backend.optimizations_checks` 通过。

## 2026-06-11 训练 AI Prompt 单据记录

- 已按用户要求补齐训练 AI prompt 的单据级记录：训练 AI 调用会在结果 JSON 中保存 `prompt_trace`，包含 `final_prompt`、`messages`、`model`、`provider`、字符数和记录时间。
- 保存位置沿用既有 JSON 字段，不新增表结构：`intent_summaries.training_ai.prompt_trace` 与 `api_assist_invocation.result_payload.training_ai.prompt_trace`。
- 覆盖正常返回和外层等待超时两条路径；即使训练 AI 接口超时，只要本地 prompt 已构建，也会随 `training_ai` 单据记录保存。
- 验证：`backend/main.py` AST 解析通过；定向 `git diff --check` 通过。

## 2026-06-12 邮件黄金库认可模板标准迭代

- 已按用户要求把新业务推广四封邮件脚本从 v52 升到 v53，生成 prompt 改为优先学习邮件黄金库中人工认可的 `full_email` 模板，不再按旧评分逻辑评估。
- 新评分方法为 `approved_gold_human_likeness_v1`，重点看“像真人销售写的亲和度”和“与 approved full_email 的业务/亲和表达相似度”。
- V34 首轮跑通 4/4，但发现 approved full_email 被旧过滤漏掉，平均分 64.25，只能说明脚本方向有效，不能作为最终黄金库验证。
- 已修复 approved full_email 取样：以 `MailGoldSeedReview.review_status=approved` 为准，修正 `fragment_id` 字符串匹配，并扩大同场景 full_email 取样范围。
- 修正版自动递增为 V35，OpenAI GPT-4.1 四封 4/4 成功，平均分 82.50，四封均命中人工认可黄金库来源；第 3 封仍略偏“建议说明”，后续可继续打磨。
- 验证记录见 `logs/mail-v34-v35-approved-gold-human-like-analysis.md`；验证命令包括 `python -m py_compile backend/main.py`、`git diff --check -- backend/main.py` 和 case1 四步真实 LLM 迭代脚本。

## 2026-06-15 邮件黄金范例库 full_email 人工点评清理

- 已按用户要求先汇总 `full_email + needs_revision` 的人工点评问题：时间/节日信息 31 条、未脱敏 24 条、格式分段 6 条、乱码异常 4 条、主题问题 1 条、其他短点评 10 条。
- 新增 `scratch/cleanup_mail_full_email_reviews.py`，对 `full_email` 且状态为 `needs_revision` 或未评审的黄金库资产执行复查与修正。
- 本次处理范围：`needs_revision` 65 条、未评审 1253 条，合计 1318 条；不处理 approved/rejected，不自动把任何条目标为 approved。
- 已写库清理：去除年份/节日/日期/工作日交稿等时效句，替换人名/客户公司名，规范分段和项目符号，删除乱码/孤立标点，并删除微信/二维码/加微信等私域联系方式。
- 最终验证：再次 dry-run `changed_count=0`、`residual_count=0`，目标范围内微信残留 0；报告见 `logs/mail-full-email-review-cleanup-20260615.md`。

## 2026-06-15 邮件黄金库 full_email 选择理由展示与宣传属性分析

- 已在邮件质量诊断 -> 黄金范例库详情右侧“保存修改”下方、“人工点评”上方新增“选择理由：XXX”展示。
- 后端 `/api/v1/mail/gold-fewshot-seeds` 仅对 `function_fragment=full_email` 返回 `selection_reason` 与 `promo_analysis`，其他切片类型返回空值，不影响显示。
- 新增 `scratch/analyze_mail_full_email_promo_reason.py`，分析 1363 封 `full_email` 是否属于宣传/推广型邮件，并把选择理由写入 `source_snapshot.promo_analysis`。
- 结果：1286 封判断为宣传/推广型，77 封疑似事务/交付/报价/PO/付款/文件沟通等非宣传邮件，需人工最终判断。
- 人工复核清单见 `logs/mail-full-email-promo-selection-reason-20260615.md`；机器明细见 `logs/mail-full-email-promo-analysis-apply-20260615.json`。
- 验证：`backend/main.py` 与分析脚本 `py_compile` 通过；前端内联 JS 语法检查通过；接口函数抽查 `full_email` 1363/1363 均有选择理由、其他切片 0；定向 `git diff --check` 通过。

## 2026-06-15 邮件黄金库疑似非宣传 full_email 删除

- 已按用户确认删除上一轮识别出的 77 封疑似非宣传 `full_email` 黄金库记录。
- 删除范围严格限定为 `source_type=mail_gold_seed` 且 `function_fragment=full_email` 的 77 个 `fragment_id`；同步删除对应 `mail_gold_seed_review` 人工评审记录 1 条。
- 删除前已导出完整备份：`logs/mail-full-email-non-promo-delete-backup-20260615.json`。
- 删除后验证：77 个目标编号在 `email_fragment_asset` 剩余 0，在 `mail_gold_seed_review` 剩余 0；黄金库 `full_email` 从 1363 降为 1286，剩余非宣传标记 0。
- 记录见 `logs/mail-full-email-non-promo-delete-20260615.md`，apply 明细见 `logs/mail-full-email-non-promo-delete-apply-20260615.json`。

## 2026-06-15 客户画像聚合口径修正（首次成交时间 + 未开票额）

- 用户核对企微客户详情发现两处口径问题，以顾佩蓉/赫斯基注塑系统（上海）KH00469 为样本只读核查后确认并修复 `backend/crm_profile_aggregator.py`（同步 `other/crm_profile_aggregator_standalone.py`）。
- 首次成交时间：原按公司级 `MIN(ContractTime)` 取到 2002-06-11（实为合同 XS050124-059 在 2005 年录入时手工误填、ERP 尚未上线的脏数据）。改为先按联系人(ContactId)取首单、查不到再回退公司级，新增 `first_contract_time_source` 标注来源；顾佩蓉修正为 2020-02-27。
- 未开票额：原为公司全量 `SUM(UnInvoicedMoney)`=60,727.95，含已回款/已销账但未开票（如国外付款历史不开票）。改为只计 `IsReceived=0`（仍有应收）的未开票=54,272.90，并保留 `uninvoiced_money_raw` 全量值备查。
- 画像文本新增"首次成交 YYYY-MM-DD"展示；未开票额展示沿用修正后口径。
- 验证：两模块 AST 解析通过；`aggregate_profile(contact_id='KH00469-040')` 实跑得首次成交=2020-02-27(联系人级)、未开票=54,273、raw=60,728，与逐合同核对一致。

## 2026-06-15 邮件黄金库 full_email #301-#400 复查清理

- 已按 `logs/mail-full-email-review-cleanup-20260615.md` 的问题口径，对黄金范例库前端编号 `#301-#400` 的 `full_email` 做逐条复查。
- 当前库内现存 47 条，另 53 个编号此前已不存在；现存 47 条均已写库清理。
- 清理内容包括：删除时间/节日/相对日期，脱敏客户名/联系人/项目名，删除电话邮箱地址/订单下载/评价/报价 PO 等事务内容，软化不可验证数字和夸张表述，修复段落与破损标题。
- 9 条清理后正文不足，不再作为生成素材：已关闭 `publishable`、`allowed_for_generation`、`usable_for_reply`，保留给人工复核。
- 最终 postcheck：`changed_count=0`、`residual_count=0`；记录见 `logs/mail-full-email-rank-301-400-cleanup-20260615.md`。
