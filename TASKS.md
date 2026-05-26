# TASKS

## 当前大目标

将《邮件智能回复实现方案.md》拆解为可持续开发的独立邮件智能回复实施任务，并建立标准任务状态文件，便于 Codex、Hermes、Claude Code、Antigravity 等工具持续接力开发。

## 当前范围

当前范围覆盖邮件智能回复一期至三期及基础 CRM 联调：

- 阶段一：采矿清洗与销售案例可视化比对证明
- 阶段二：邮件质量诊断与 Few-Shot 本地调教
- 阶段三：可视化配置台与三重安全门对抗
- 阶段四：双系统 API 联调与 CRM 顺畅对接

暂不考虑：

- 四期规划：前瞻性商业化深度优化建议
- ROI Attribution Panel
- 发信人域名信誉保护、随机延迟、退信熔断
- LTV 流失预测主动触发
- 跨文化风格 RAG 过滤器
- 生产环境大规模灰度发信

## 最高优先级约束

- 邮件方案尽量和企微区分，便于各自调整。
- 邮件构建、调试、测试不得影响企微现有使用。
- 邮件 API、配置、数据库、前端入口、任务脚本应独立命名。
- 所有 Mock、样例、推演数据必须明确标注 Mock。

## 任务清单

### P0：文档与边界初始化

- [x] Task 1：创建标准状态文件 `AGENTS.md`、`TASKS.md`、`PROGRESS.md`、`TASK_HANDOFF.md`、`VALIDATION.md`
- [x] Task 1.1：创建运行日志文件 `logs/codex-run.log`、`logs/codex-retry.log`
- [x] Task 1.2：把“恢复、重试、不中断”规则写入 `AGENTS.md`，并前置为最高优先级
- [x] Task 1.3：把 Hermes 短启动指令写入 `AGENTS.md`
- [x] Task 2：梳理邮件智能回复与企微智能回复的模块边界 (已完成隔离设计并在 sync_crm_emails 中规范落地)
- [x] Task 3：确定邮件系统独立目录结构与命名规范 (采用 backend/mail_* 及 backend/sync_* 独立命名)
- [x] Task 4：梳理《邮件智能回复实现方案.md》中当前实施范围，明确四期规划暂不开发 (已在方案与任务体系中彻底物理拆离)
- [x] Task 5：把邮件系统的 P0/P1/P2 开发路线追加到 `项目进展.md`，不得修改历史版本 (已追加入库规范)

### P0：邮件数据采矿与清洗

- [x] Task 6：确认邮件历史数据来源、字段结构、外部 ID、客户邮箱、收发方向、时间字段 (已绑定 SQL Server 增量拉取)
- [x] Task 7：设计邮件采矿断点续传表或中间状态文件 (依托 mail_import_batch 状态标记与批次绑定)
- [x] Task 8：实现邮件 SQL 粗筛规则，排除退信、广告、自动回复、签名、历史引用盖楼 (依托 AUTO_MAIL_PATTERNS)
- [x] Task 9：实现 HTML 邮件正文清洗，剥离 quoted reply、签名、免责声明、营销脚注 (精细化去噪并在 upsert_mail_cleaned 落地)
- [x] Task 10：实现 `useful_score` 初筛逻辑，筛选真实销售高价值回复 (已在数据同步与清洗链路中打底)
- [x] Task 11：输出首批邮件黄金候选切片，并明确标注来源、场景、质量分、脱敏状态 (已成功通过修正 seller 识别逻辑导出 25 封高价值黄金切片种子，完美输出 md/json/csv，已于 2026-05-22 17:42:17 +08:00 导出 25 条脱敏候选到 docs/mail_gold_candidates/latest_{json,csv,md})
- [x] Task 12：建立采矿失败、限流、断网、重试和断点续跑机制 (支持唯一 UID 内存排重高速断点续跑)

### P0：邮件知识库与 Few-Shot 结构

- [x] Task 13：设计邮件黄金切片字段结构 (已完成 `docs/mail_gold_snippet_schema.md`，字段结构对齐 latest 邮件黄金候选导出字段，并明确 Task 14/15/16 预留字段不在本任务实现)
- [x] Task 14：定义邮件切片类型：`greetings`、`example`、`process`、`constraint`、`quotation` (已在 `docs/mail_gold_snippet_schema.md` 正式定义 5 类 `snippet_type` 的用途、边界、判定规则、可包含/不可包含内容、示例字段建议、判定优先级与内容安全口径)
- [x] Task 15：定义邮件切片适用场景：老客户唤醒、新业务推广、新联系人介绍 (已在 `docs/mail_gold_snippet_schema.md` 正式定义 `re_activation`/`new_business_promotion`/`new_contact_intro` 三大场景，补齐适用目标、触发条件、禁用边界、推荐 `snippet_type` 组合、Sequence Step 1-4 映射，以及 `scenario`/`scenario_label`/`scenario_reason`/`sequence_step_hint` 的关系与边界)
- [x] Task 16：定义行业、国家、客户等级、产品线、账期风险等过滤字段 (已在 `docs/mail_gold_snippet_schema.md` 正式定义 `industry`、`country`、`customer_tier`、`product_line`、`payment_risk` 的枚举口径、来源优先级、归一化规则、缺失兜底、检索使用规则，以及与 `scenario`/`snippet_type`/安全门的边界)
- [x] Task 17：实现邮件 Few-Shot 检索准入阈值，默认 `useful_score >= 0.60` (已在 `backend/config.py` 增加 `MAIL_FEWSHOT_MIN_USEFUL_SCORE=0.60`，并通过 `/api/v1/mail/fewshot/retrieve` 对 `email_fragment_asset` 执行准入过滤)
- [x] Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库 (已在 `backend/main.py` 为 `excellent_reply`/人工反馈候选补齐审核门禁、手工 PATCH 回流同步和 promote 后解锁逻辑)

### P0：三大邮件场景与 4 轮 Sequence

- [x] Task 19：落地老客户唤醒 `re_activation` 的 4 轮策略 (已新增 `backend/mail_sequence_strategy.py` 与 `docs/mail_re_activation_sequence.md`，沉淀独立 4 轮策略结构与复用字段)
- [x] Task 20：落地新业务推广 `new_business_promotion` 的 4 轮策略 (已扩展 `backend/mail_sequence_strategy.py` 新增 `new_business_promotion` 场景 4-step 策略、检索过滤边界、CTA/主题提示与查找函数，并新增 `docs/mail_new_business_promotion_sequence.md` 供 Task 21-25 与邮件 API 复用)
- [x] Task 21：落地新接手联系人介绍 `new_contact_intro` 的 4 轮策略 (已扩展 `backend/mail_sequence_strategy.py` 新增 `new_contact_intro` 场景 4-step 策略、交接介绍/背景确认/协作路径/审核下一步边界，并新增 `docs/mail_new_contact_intro_sequence.md` 供 Task 22-25 与邮件 API 复用)
- [x] Task 22：定义 Sequence 状态枚举，如 `pending`、`drafted`、`approved`、`sent`、`replied`、`interrupted`、`blocked` (已在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceStatus`、`MailSequenceStatusMetadata`、分类常量与状态归一化/校验/分类辅助函数，明确邮件侧状态仅供后续状态机与草稿 API 复用，不开启真实发送)
- [x] Task 23：定义 Step 触发间隔，默认 Step1 当天生成，Step2 间隔 7 天，Step3 间隔 10 天，Step4 间隔 10 天 (已在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceStepInterval`、`MAIL_SEQUENCE_STEP_INTERVALS`、`get_mail_sequence_step_interval`/`list_mail_sequence_step_intervals`，并新增 `docs/mail_sequence_step_intervals.md` 固化默认间隔与触发锚点边界)
- [x] Task 24：实现客户回复、CRM 状态变化、人工封印时的状态机物理切断规则 (已在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceCutoffEventType`、`MailSequenceInterruptionReason`、`MailSequenceCutoffRule`、`MAIL_SEQUENCE_CUTOFF_RULES`、`get_mail_sequence_cutoff_terminal_status`、`should_cutoff_event_physically_stop_sequence`、`list_mail_sequence_cutoff_rules` 等复用结构，明确客户回复/CRM 状态变化/人工封印的物理切断口径)
- [x] Task 25：实现待发草稿销毁或锁定规则，避免已回复客户继续收到追问邮件 (已在 `backend/mail_sequence_strategy.py` 新增 `MailPendingDraftDispositionAction`、`MailPendingDraftDispositionRule`、`MAIL_PENDING_DRAFT_DISPOSITION_RULES` 及 `get_mail_pending_draft_disposition_rule` / `resolve_mail_pending_draft_disposition` / `list_mail_pending_draft_disposition_rules`，并新增 `docs/mail_pending_draft_disposition.md` 固化客户回复、CRM 变更、勿扰/联系人失效、人工封印下的 `destroy`/`lock`/`keep` 处置口径)

### P0：邮件草稿生成 API

- [x] Task 26：设计并实现 `POST /api/v1/mail/generate-draft` (已在 `backend/main.py` 新增邮件侧草稿生成脚手架接口，复用 Sequence 策略与 Few-Shot 准入助手，只返回 draft/review 结果，不写库、不真实发信)
- [x] Task 27：请求参数覆盖 `customer_key`、`contact_email`、`scenario`、`suite_step`、`current_seller_name`、`current_seller_signature` (已确认 `MailGenerateDraftRequest` 仅定义这 6 个字段，并通过 `extra = "forbid"` 禁止额外请求字段)
- [x] Task 28：响应参数覆盖 `mail_uid`、`final_subject`、`final_body_html`、`retrieved_fewshot_id`、`fewshot_match_score`、`safety_guardrail` (已核对 `backend/main.py` 中 `MailGenerateDraftResponse`、`_build_mail_generate_draft_response` 与 `POST /api/v1/mail/generate-draft`，响应模型与返回值已完整覆盖上述字段；本轮通过 Codex CLI 审核确认无需额外代码改动)
- [x] Task 29：生成逻辑采用二阶段内容生成：先结构化意图/画像，再组装邮件草稿 (已在 `backend/main.py` 新增 `MailDraftIntentProfile`、`MailDraftAssembledContent`、`_build_mail_draft_intent_profile`、`_mail_subject_from_intent_profile`、`_assemble_mail_draft_from_intent_profile`，邮件草稿生成链路已拆为“结构化意图/画像 -> 组装主题与正文”的二阶段流程，并保持 review-only 响应契约不变)
- [x] Task 30：邮件正文中的价格、工期、折扣、账期必须优先使用后端物理占位符填充 (已在 `backend/main.py` 为 `/api/v1/mail/generate-draft` 新增 `MailDraftCommercialTerms` 与价格/工期/折扣/账期后端占位符装配，正文优先输出后端物理占位符；若仅存在唯一有效 `PricingRule` 则价格可解析为后端规则值；同时对 admitted Few-Shot 引用执行商业条款脱敏，避免历史价格/工期/账期自由文本穿透进草稿正文)
- [x] Task 31：生成结果默认进入草稿和审核，不默认真实发送 (已在 `backend/main.py` 将 `MailGenerateDraftResponse` 顶层显式收口为 `status=drafted`、`draft_status=drafted`、`review_required=true`、`review_mode=human_review_required`、`real_sending_enabled=false`，并保持 `safety_guardrail` 锁定审核与真实发送关闭)

### P0：Sequence 中断 API

- [x] Task 32：设计并实现 `POST /api/v1/sequence/interrupt` (已在 `backend/main.py` 新增邮件侧 review-only 中断 API，复用 `mail_sequence_strategy` 中断/草稿处置规则，仅返回中断与待发草稿处置计划，不写库、不真实删除/锁定、不真实发信)
- [x] Task 33：支持 CRM 状态变更触发中断，如 `CRM_STAGE_CHANGED_TO_WON` (已在 `backend/main.py` 为 `POST /api/v1/sequence/interrupt` 新增 `crm_event_type`/`crm_stage`/`previous_crm_stage`/`crm_changed_at`，支持 `interrupt_reason=crm_state_change` + `crm_event_type=CRM_STAGE_CHANGED_TO_WON` 及 CRM 阶段别名映射，保持 review-only 且不写库、不真实删锁草稿、不真实发信；响应新增 `crm_state_change_trigger` 预览)
- [x] Task 34：支持销售手动强封印 (已在 `backend/main.py` 为 `POST /api/v1/sequence/interrupt` 新增 `manual_seal_actor`/`manual_seal_reason`/`operator_id`/`sealed_at` 请求字段，支持 `interrupt_reason=manual_seal`、`sales_manual_seal`、`manual_sealed_by_sales` 等销售手动封印别名归一到既有 `mail_sequence_strategy` 的 `manual_sealed_by_sales` 规则；响应新增 `manual_seal_trigger` 预览，保持 review-only、不写库、不真实删锁草稿、不真实发信)
- [x] Task 35：支持按客户、域名、联系人维度中断 (已在 `backend/main.py` 将 `POST /api/v1/sequence/interrupt` 收口为至少提供 `customer_key`、`recipient_domain`、`contact_email` 之一；响应与 `audit_preview` 显式返回 `interruption_scope`、`interruption_target`、`scope_targets`，支持客户/域名/联系人及多目标 review-only 中断预览；保持不写库、不真实删除/锁定草稿、不真实发信)
- [x] Task 36：中断后返回被删除或锁定的待发草稿数量 (已在 `backend/main.py` 将 `POST /api/v1/sequence/interrupt` 的 `deleted_pending_drafts_count` 与 `locked_pending_drafts_count` 改为按本次 `pending_draft_dispositions` 计划统计，和 `planned_destroy_pending_drafts_count` / `planned_lock_pending_drafts_count` 保持一致；`audit_preview` 明确这些计数仅来自 review-only 处置计划，不写库、不真实删除或锁定草稿、不真实发信)
- [x] Task 37：中断事件写入邮件安全或操作日志 (已在 `backend/main.py` 为 `POST /api/v1/sequence/interrupt` 新增 `MailSequenceInterruptOperationLogEntry`，响应顶层返回 `operation_log_entry`，`audit_preview` 同步返回同一份操作日志预览，并通过 `logger.info("MAIL_SEQUENCE_INTERRUPT_REVIEW_ONLY ...")` 输出 review-only 中断操作日志；继续保持不写数据库、不真实删除或锁定草稿、不真实发信)

### P0：三重物理安全门

- [x] Task 38：实现财务价格底线门，低于底价红牌硬拦截 (已在 `backend/main.py` 为 `/api/v1/mail/generate-draft` 新增财务价格底线门：扩展 `MailSafetyGuardrail` 的红牌阻断字段、补齐 active pricing rule 读取与显式价格抽取/比对 helper，并在生成草稿时对正文/已解析商业价格执行底价校验；一旦低于有效 `PricingRule.price_min` 即返回 `status=blocked_by_financial_safety_gate`、`safety_guardrail.status=red_card_hard_block`、`draft_status=blocked`、`real_sending_enabled=false`，同时回传 `block_details` 诊断信息)
- [x] Task 39：实现价格正则提取，识别 RMB、元、USD、美元、per word、每千字、折扣等表达 (已在 `backend/main.py` 扩展 `_extract_mail_explicit_price_mentions`、`_mail_pricing_context_unit`、`_mail_pricing_context_currency`、`_mail_explicit_price_mention_type` 与 `_mail_floor_rule_for_price_mention`，补齐 RMB/CNY/人民币/元/USD/美元/美金/$/￥、per word、每词、每千字/千字符/1k、discount/10% off/8折 等识别，并避免把折扣表达误当作底价穿透进行红牌拦截)
- [x] Task 40：实现履约工期 SLA 校准门，低于标准 SLA 时物理拉正并黄牌锁定 (已在 `backend/main.py` 接入 `backend/mail_sla_guardrail.py` 的工期校准门；`POST /api/v1/mail/generate-draft` 现会把 `24 hours`、`1 day`、`next-day delivery` 等低于标准 SLA 的承诺物理替换为 `3 business days`，并返回 `safety_guardrail.status=yellow_card_sla_calibrated_locked`、`block_details`、黄牌 warning 与锁定审核态，继续保持 review-only、不真实发信；新增 `backend/mail_sla_guardrail_checks.py` 定向校验快速工期承诺被物理拉正且真实发信仍关闭)
- [x] Task 41：实现收件域名与抄送域名防泄密门 (已在 `backend/main.py` 为 `POST /api/v1/mail/generate-draft` 新增收件人与抄送域名防泄密门；请求新增可选 `cc_emails`，会同时校验 `contact_email` 与 `cc_emails` 域名，命中竞对或风险域名时返回 `status=blocked_by_recipient_domain_confidentiality_gate`、`safety_guardrail.status=red_card_hard_block`、`draft_status=blocked`、`real_sending_enabled=false` 与阻断诊断；新增 `backend/mail_recipient_domain_guardrail_checks.py` 定向校验 recipient/cc 阻断与正常客户域名放行)
- [x] Task 42：实现竞对域名黑名单与客户域名白名单 (已在 `backend/main.py` 将收件域名防泄密门升级为“竞对域名黑名单 + 客户域名白名单”双校验：新增 `MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST`、`MAIL_CONFIDENTIALITY_CUSTOMER_DOMAIN_WHITELIST_BY_CUSTOMER_KEY`、`_mail_customer_domain_whitelist` 与通用域名匹配 helper；`POST /api/v1/mail/generate-draft` 现会在保留竞对/风险域名红牌拦截的同时，要求 `contact_email` 与 `cc_emails` 落在当前客户域名白名单内，否则按 `non_whitelisted_customer_domain` 红牌阻断；`backend/mail_recipient_domain_guardrail_checks.py` 已补充白名单别名放行、非白名单域名阻断与竞对黑名单断言)
- [x] Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本 (已在 `backend/main.py` 新增 `MAIL_SENSITIVE_CONTENT_RED_CARD_RULES`、`_mail_sensitive_content_mask`、`_mail_sensitive_content_context` 与 `_evaluate_mail_sensitive_content_red_card_guardrail`，对邮件主题、正文和已解析商业条款执行敏感内容扫描；命中内部底价/成本边界、财务个人账户、未公开返点或折扣时，`POST /api/v1/mail/generate-draft` 现会返回 `status=blocked_by_sensitive_content_red_card_gate`、`safety_guardrail.status=red_card_hard_block`、`red_card_code=blocked_by_sensitive_content_red_card_gate`、`draft_status=blocked`、`real_sending_enabled=false` 与脱敏后的 `block_details`；新增 `backend/mail_sensitive_content_guardrail_checks.py` 定向校验红牌拦截、数字脱敏与后端占位符放行)
- [x] Task 44：实现红牌、黄牌、通过三种安全门结果结构 (已在 `backend/main.py` 为 `MailSafetyGuardrail` 新增统一结果结构字段 `result_schema_version`、`overall_outcome`、`gate_results`，并新增 `_mail_safety_gate_result`、`_build_mail_safety_gate_results`、`_mail_safety_overall_outcome`；`POST /api/v1/mail/generate-draft` 现会对收件域名防泄密、工期 SLA、价格底线、敏感内容四类门禁统一返回同形结果项，分别表达 `red_card` / `yellow_card` / `passed`，并在所有红牌/黄牌/通过分支回传一致 schema；新增 `backend/mail_generate_draft_safety_result_checks.py` 定向校验统一结构、总体优先级与三种结果形态；继续保持 review-only、不真实发信)
- [x] Task 45：实现 20 个黑盒对抗测试用例，覆盖价格穿透、交期逼迫、同业钓鱼、占位符绕过 (已新增 `backend/mail_draft_safety_adversarial_checks.py`，20 条黑盒对抗用例覆盖价格底线穿透、紧急 SLA 逼迫、竞对域名钓鱼、占位符绕过；补齐邮件占位符绕过红牌门，真实发信保持关闭)

### P1：邮件质量诊断与人工纠偏面板

- [x] Task 46：设计邮件质量诊断面板独立入口 (已在 `frontend/index.html` 新增顶层“邮件质量诊断”主导航、独立 `app-mail-quality` 页面骨架、`#mail-quality` hash 路由与独立 mail workspace 容器，明确与企微实时链路物理隔离，并为 Task 47-52 预留样本列表/质量评分/人工纠偏/诊断详情区域)
- [x] Task 47：展示草稿 ID、场景、Sequence Step、邮件主题 (已在 `frontend/index.html` 的邮件质量诊断面板补齐 review-only 草稿样本卡片与详情字段，展示 Draft ID、Scenario、Sequence Step、Email Subject，并保持与企微链路物理隔离)
- [x] Task 48：展示 SQL 粗筛、HTML 去噪、CRM 画像、RAG Few-Shot、安全门链路轨迹 (已在 `frontend/index.html` 的邮件质量诊断面板新增 review-only 诊断轨迹卡与详情区五列链路摘要，显式展示 SQL 粗筛、HTML 去噪、CRM 画像、RAG Few-Shot、安全门轨迹，并追加“仅 Mock / 不接企微”隔离标识)
- [x] Task 49：展示 AI 生成版本与运营专家修正版双栏对比 (已在 `frontend/index.html` 的邮件质量诊断面板新增 review-only 双栏对比区，左右分别展示 AI 生成草稿与运营专家修正版，补充差异提示标签，并显式标注 `mock_revision_pair` 与“不保存、不发信、不接企微”的隔离说明)
- [x] Task 50：支持专家编辑后保存为候选高质量切片 (已在 `frontend/index.html` 的邮件质量诊断面板新增 review-only 专家编辑区，支持编辑主题/正文、选择 `snippet_type`/`scenario`/`useful_score`，并通过页面内保存动作生成候选高质量切片预览；明确保持 Mock、仅页面内预览、不写库、不发信、不调用后端、不接企微)
- [x] Task 51：支持点赞、差评、拉黑 Few-Shot、保存并反哺 (已在 `frontend/index.html` 的“邮件质量诊断”面板新增 review-only Mock 反馈区，支持草稿点赞/差评、命中 Few-Shot 拉黑/取消拉黑、保存反馈并生成页面内反哺预览与事件日志；全程仅更新前端页面内状态，不调用 API、不写数据库、不发信、不接企微)
- [x] Task 52：反哺进入黄金库前必须保留人工审核或赢单状态门槛，避免劣质销售习惯污染知识库 (已在 `frontend/index.html` 的邮件质量诊断面板新增“人工批准 / 成单证据”黄金库准入门、blocked/ready 状态文案、Gate Evidence/Gold Library Action 预览字段，以及 `gold_library_gate_blocked` / `feedback_backfeed_ready_for_gold_library` 事件；继续保持 review-only Mock，不调用 API、不写数据库、不发信、不接企微)

### P1：邮件配置管理台

- [x] Task 53：设计邮件全局配置管理入口 (已在 `frontend/index.html` 的独立邮件 workspace 中新增 `质量诊断 / Mail Config` 子导航与 review-only Mock 配置面板骨架，预留 Sequence 间隔、安全门规则、RAG/LLM 参数、配置审计日志、热加载范围五个分区；保持不调用后端、不写数据库、不发信、不接企微)
- [x] Task 54：支持 Sequence 多轮触发间隔配置 (已在 `frontend/index.html` 的 `Mail Config` 面板把 Sequence 区块从静态占位升级为 review-only 可编辑 Mock 配置：支持 3 个邮件场景切换、4 个 Step 延迟天数输入、Task 23 默认值（0/7/10/10 天）回显、anchor/默认说明、dirty-state JSON 预览、恢复当前场景默认，以及明确邮件侧隔离文案；不调用后端、不写数据库、不发信、不影响企微配置)
- [x] Task 55：支持翻译产品线、印刷产品线底价配置 (已在 `frontend/index.html` 的 `Mail Config` 面板新增 review-only `翻译/印刷底价` 分区与快捷入口，提供翻译/印刷 4 条产品线最低价可编辑 Mock 配置、邮件侧独立 `mailTranslationPrintFloorMockState`、安全门策略说明、dirty badge、JSON 预览与恢复默认；不调用后端、不写数据库、不热加载、不影响企微配置或真实发信)
- [x] Task 56：支持大客户加急工期最低阈值配置 (已在 `frontend/index.html` 的 `Mail Config` 面板新增 review-only `大客户加急 SLA` 分区与快捷入口，提供 3 档客户等级的最短提前通知/最短交付周期/人工复核开关可编辑 Mock 配置、邮件侧独立 `mailBigCustomerExpediteSlaMockState`、安全门策略说明、dirty badge、JSON 预览与恢复默认；不调用后端、不写数据库、不热加载、不影响企微配置或真实发信)
- [x] Task 57：支持 RAG 准入阈值与 LLM 温度配置 (已在 `frontend/index.html` 的 `Mail Config` 面板新增 review-only `RAG / LLM 参数` 可编辑 Mock 配置，支持 `rag_admission_threshold` 与 `draft_llm_temperature` 两项参数编辑、dirty badge、恢复默认、参数说明与 JSON 预览，并继续保持不调用后端、不写数据库、不热加载、不发信、不接企微)
- [x] Task 58：支持配置变更审计日志 (已在 `frontend/index.html` 的 `Mail Config` 面板把 `配置审计日志` 区块升级为 review-only 可交互 Mock 审计面板，支持审计视角/分区/审批状态/备注筛选、显示当前邮件配置差异、恢复默认、dirty badge 与 JSON 审计预览，并继续保持不调用后端、不写数据库、不热加载、不发信、不接企微)
- [x] Task 59：配置热加载必须只影响邮件系统，不影响企微配置 (已在 `frontend/index.html` 的 `Mail Config` 面板把 `热加载范围预览` 区块升级为 review-only `邮件配置热加载范围` 面板，新增 `mailConfigHotReloadMockState`、邮件侧候选热加载作用域、企微排除清单、隔离断言、dirty badge、恢复默认与 JSON 预览，明确 `wecom_config_state_impact=none`、`disabled_effects` 与 `mail_only_review_mock` 命名空间；继续保持不调用后端、不写数据库、不触发真实热加载、不发信、不影响企微配置或企微会话状态)

### P1：CRM 邮件侧联调

- [x] Task 60：确认 CRM 客户 Key、联系人邮箱、行业、账期、销售负责人、签名字段 (已新增 `docs/mail_crm_field_contract.md`、`backend/mail_crm_field_contract.py` 与 `backend/mail_crm_field_contract_checks.py`，锁定邮件侧 CRM 字段契约、必填/可选边界、字段别名与企微隔离约束；当前 API 只接收已落地必填字段与 `cc_emails`，`company_industry` / `payment_risk_level` 留待 Task 61/62 接入 CRM 联查与风险审核链路)
- [x] Task 61：实现 CRM 画像联查和域名级 fallback (已在 `backend/main.py` 接入邮件侧 CRM 画像联查，查找键仅限 `customer_key` 与 `contact_email`，明确不把企微 `external_userid` 当作邮件 key；草稿意图画像已合并 `company_industry`、`payment_risk_level` 与客户域名；收件域名白名单支持静态客户域名、CRM 画像域名和 `contact_email` 域名 fallback；新增 `backend/mail_crm_profile_lookup_checks.py` 定向校验)
- [ ] Task 62：实现高欠款风险客户发送前锁定审核
- [ ] Task 63：实现客户回复、微信/电话签单、CRM 阶段变化触发 Sequence 中断
- [ ] Task 64：建立 CRM 联调 Mock 数据，避免一开始依赖生产系统

### P1：验证与质量闭环

- [ ] Task 65：建立邮件系统单元测试与接口测试
- [ ] Task 66：建立邮件草稿质量人工评分标准
- [ ] Task 67：建立邮件安全门拦截率验证报告
- [ ] Task 68：建立 25 条黄金种子切片可视化比对报告
- [ ] Task 69：建立邮件系统运行日志和错误排查指南

### P2：上线前准备

- [ ] Task 70：梳理邮件系统环境变量和部署说明
- [ ] Task 71：补充邮件系统数据脱敏规范
- [ ] Task 72：补充邮件系统回滚方案
- [ ] Task 73：补充邮件系统真实发送开关和灰度前置条件
- [ ] Task 74：准备后续四期规划的任务池，但不进入当前开发

## 当前第一个未完成任务

Task 62：实现高欠款风险客户发送前锁定审核

## 任务执行规则

- 每次只执行第一个未完成任务，完成并验证后更新本文件与日志再结束。
- 每个任务完成后必须更新本文件。
- 不允许跳过未完成任务。
- 如果任务需要拆分，请在本文件中新增子任务。
- 如果遇到 token、rate limit、quota、429、usage limit、temporarily unavailable 或网络临时错误，不要把任务标记失败；本轮如实记录后结束，由 gateway 的 cron 周期（如 every 2m）自动重试，断网不丢任务。
- 任务通过 Hermes gateway + cron 循环驱动：每个 cron tick 是独立隔离会话，只做第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加进展或报错（含时间/任务号/做了什么/成功或失败/下一步）；失败如实写，严禁"假绿"。
- 如果所有任务完成，必须生成 `FINAL_REPORT.md`，并在 `logs/codex-run.log` 末尾追加 `ALL TASKS COMPLETED: 当前时间`。
