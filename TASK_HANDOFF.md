# TASK_HANDOFF

## 当前目标

根据《邮件智能回复实现方案.md》和《文件创建要求.md》，建立邮件智能回复独立开发的标准项目状态文件，便于后续多个 AI 工具接力开发。

## 当前任务

Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。

当前小点：Task 42 已完成；`backend/main.py` 已将收件域名防泄密门升级为“竞对域名黑名单 + 客户域名白名单”双校验，新增 `MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST`、`MAIL_CONFIDENTIALITY_CUSTOMER_DOMAIN_WHITELIST_BY_CUSTOMER_KEY`、`_mail_customer_domain_whitelist` 与通用域名匹配 helper；`POST /api/v1/mail/generate-draft` 现会在竞对/风险域名红牌拦截之外，额外要求 `contact_email` 与 `cc_emails` 落在当前客户域名白名单内，否则按 `non_whitelisted_customer_domain` 红牌阻断，继续保持 review-only、不写数据库、不真实发信。下一步进入 Task 43。

## 关键背景

当前项目已有成熟的企微智能回复系统，核心能力包括：

- 企微会话接入
- 旁路强信号识别
- LLM-1 结构化分析
- LLM-2 辅助回复生成
- RAG 知识库
- 前端侧边栏
- 案例库跑批
- 人工评分与质量标准

邮件智能回复是新增方向，不应直接混入企微主链路。

邮件方案聚焦：

- 老客户唤醒
- 新业务推广
- 新接手联系人介绍
- 4 轮 Sequence 邮件套装
- 邮件历史数据采矿
- 邮件黄金 Few-Shot
- 邮件草稿生成
- 销售审核确认
- 三重物理安全门
- 邮件质量诊断与纠偏
- CRM 邮件侧 API 联调

## 当前排除范围

以下内容来自《邮件智能回复实现方案.md》的四期规划，当前暂不进入开发：

- ROI 归因看板
- 小批量真实灰度发信
- 发信人域名信誉保护
- 高斯随机延迟与退信熔断
- 客户生命周期 LTV 流失预警
- 跨国客户本土文化风格 RAG 匹配

这些内容后续可作为四期任务池重新拆解。

## 已完成

- 已完成 Task 42：在 `backend/main.py` 将 `POST /api/v1/mail/generate-draft` 的收件域名防泄密门升级为“竞对域名黑名单 + 客户域名白名单”双校验；新增 `MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST`、`MAIL_CONFIDENTIALITY_CUSTOMER_DOMAIN_WHITELIST_BY_CUSTOMER_KEY`、`_mail_domain_matches_list` 与 `_mail_customer_domain_whitelist`，并让 `_evaluate_mail_recipient_domain_confidentiality_guardrail` 在保留竞对/风险域名红牌拦截的同时，对 `contact_email` 与 `cc_emails` 执行当前客户域名白名单校验，非白名单域名按 `non_whitelisted_customer_domain` 红牌阻断；`backend/mail_recipient_domain_guardrail_checks.py` 已补充非白名单域名阻断、客户白名单别名放行与竞对黑名单断言；本轮 `codex exec --sandbox workspace-write ...` 因 usage limit 中断后已按规则记录并由当前 Agent 接手完成；`python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log` 通过。
- 已完成 Task 41：在 `backend/main.py` 为 `POST /api/v1/mail/generate-draft` 新增收件人与抄送域名防泄密门；`MailGenerateDraftRequest` 新增可选 `cc_emails`，`_evaluate_mail_recipient_domain_confidentiality_guardrail` 会归一化并校验 `contact_email` 与 `cc_emails` 域名，命中竞对或风险域名时返回红牌硬拦截，响应顶层为 `status=blocked_by_recipient_domain_confidentiality_gate`、`draft_status=blocked`、`real_sending_enabled=false`，`safety_guardrail` 返回 `red_card_code=blocked_by_recipient_domain_confidentiality_gate`、`blocked_by=recipient_domain_confidentiality_guardrail` 与 `block_details`；新增 `backend/mail_recipient_domain_guardrail_checks.py` 定向校验竞对收件人、风险抄送和正常客户域名；`python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。
- 已完成 Task 40：在 `backend/main.py` 接入 `backend/mail_sla_guardrail.py` 的履约工期 SLA 校准门，并新增 `backend/mail_sla_guardrail_checks.py` 定向校验；`POST /api/v1/mail/generate-draft` 现会把 `24 hours`、`1 day`、`next-day delivery`、`tomorrow delivery` 等低于标准 SLA 的承诺物理替换为后端标准交期 `3 business days`，返回 `safety_guardrail.status=yellow_card_sla_calibrated_locked`、黄牌 warning、`block_details` 与锁定审核态；继续保持 review-only、不写数据库、不真实发信；`python3 -m unittest backend/mail_sla_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_sla_guardrail.py backend/mail_sla_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_sla_guardrail.py backend/mail_sla_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。
- 已完成 Task 39：在 `backend/main.py` 扩展 `_mail_pricing_context_unit`、`_mail_pricing_context_currency`、`_mail_explicit_price_mention_type`、`_extract_mail_explicit_price_mentions` 与 `_mail_floor_rule_for_price_mention`，补齐 RMB/CNY/人民币/元/USD/美元/美金/$/￥、per word、每词、每千字/千字符/1k、discount 10%/10% off/8折 等显式价格或折扣表达识别；同时让 `_evaluate_mail_financial_price_floor_guardrail` 跳过 `mention_type=discount`，避免把折扣表达误当作价格底线穿透红牌；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过；抽取冒烟脚本已确认 CNY/USD/per word/每千字/折扣样例均可识别。
- 已完成 Task 38：在 `backend/main.py` 扩展 `MailSafetyGuardrail` 的 `hard_block` / `red_card_code` / `blocked_by` / `block_details` 字段，并新增 `_active_mail_pricing_rules`、`_extract_mail_explicit_price_mentions`、`_mail_floor_rule_for_price_mention`、`_evaluate_mail_financial_price_floor_guardrail` 等 helper；`POST /api/v1/mail/generate-draft` 现会对草稿正文和已解析商业价格执行底价校验，一旦显式价格低于有效 `PricingRule.price_min` 即返回 `status=blocked_by_financial_safety_gate`、`safety_guardrail.status=red_card_hard_block`、`draft_status=blocked`、`real_sending_enabled=false`，并回传 `block_details` 诊断信息；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过；静态断言脚本输出 `task38_static_ok`。
- 已完成 Task 37：在 `backend/main.py` 为 `POST /api/v1/sequence/interrupt` 新增 `MailSequenceInterruptOperationLogEntry`，并将 `MailSequenceInterruptResponse` 顶层扩展为返回 `operation_log_entry`；`_build_mail_sequence_interrupt_response` 现会构造同一份 `operation_log_entry` 预览、在 `audit_preview` 回传该预览，并通过 `logger.info("MAIL_SEQUENCE_INTERRUPT_REVIEW_ONLY ...")` 输出结构化 review-only 中断操作日志；继续保持 `review_only=true`、`real_sending_enabled=false`，未写数据库、未真实删除或锁定草稿、未真实发信；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。
- 已完成 Task 36：在 `backend/main.py` 的 `_build_mail_sequence_interrupt_response` 中，`deleted_pending_drafts_count` / `locked_pending_drafts_count` 已由固定 0 改为按 planned disposition 统计出的 `planned_destroy_count` / `planned_lock_count`，并在 `audit_preview` 返回相同计数、`count_basis=planned_pending_draft_dispositions_only` 和所有真实执行开关为 false；保持 `review_only=true`、`real_sending_enabled=false`，未写库、未真实删除或锁定草稿、未真实发信；`python3 -m py_compile backend/main.py` 通过。
- 已完成 Task 35：在 `backend/main.py` 将 `MailSequenceInterruptRequest.customer_key` 调整为可选，复用既有 `customer_key`、`contact_email`、`recipient_domain` 字段作为中断目标，并新增 `_build_mail_sequence_interrupt_scope` 校验至少一个目标存在；`MailSequenceInterruptResponse` 与 `audit_preview` 显式返回 `interruption_scope`、`interruption_target`、`scope_targets`，支持 customer/domain/contact 单维度与多目标维度预览；保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`、`locked_pending_drafts_count=0`，未写库、未真实删除或锁定草稿、未真实发信；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py logs/codex-run.log` 通过。
- 已完成 Task 34：在 `backend/main.py` 为 `MailSequenceInterruptRequest` 新增 `manual_seal_actor`、`manual_seal_reason`、`operator_id`、`sealed_at`，为 `MailSequenceInterruptResponse` 新增 `manual_seal_trigger`；补齐 `MANUAL_SEAL_INTERRUPT_REASON_ALIASES`、`_normalize_manual_seal_interrupt_reason`、`_build_mail_manual_seal_trigger_preview` 与手动封印事件/原因一致性校验，使 `POST /api/v1/sequence/interrupt` 支持 `interrupt_reason=manual_seal`、`sales_manual_seal`、`manual_sealed_by_sales` 等销售手动封印触发，同时复用 `mail_sequence_strategy` 既有 manual-seal 切断与待发草稿锁定规则；保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`、`locked_pending_drafts_count=0`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。
- 已完成 Task 33：在 `backend/main.py` 为 `MailSequenceInterruptRequest` 新增 `crm_event_type`、`crm_stage`、`previous_crm_stage`、`crm_changed_at`，为 `MailSequenceInterruptResponse` 新增 `crm_state_change_trigger`；补齐 `CRM_STATE_CHANGE_INTERRUPT_REASON_ALIASES`、`_normalize_crm_state_change_interrupt_reason`、`_build_mail_crm_state_change_trigger_preview` 与 CRM 事件/原因一致性校验，使 `POST /api/v1/sequence/interrupt` 支持 `interrupt_reason=crm_state_change` + `crm_event_type=CRM_STAGE_CHANGED_TO_WON`、`won`、`closed_won` 等 CRM 状态变更触发，同时保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`、`locked_pending_drafts_count=0`；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。
- 已完成 Task 32：在 `backend/main.py` 新增 `MailSequenceInterruptRequest`、`MailPendingDraftInterruptPlan`、`MailSequenceInterruptResponse`、`_build_mail_sequence_interrupt_response` 与 `POST /api/v1/sequence/interrupt`；接口接受 `customer_key`、`interrupt_reason`、`operator_name` 及可选事件/联系人/域名/场景/步骤/当前状态/待发草稿状态元数据，复用 `get_mail_sequence_cutoff_rule`、`get_mail_sequence_cutoff_terminal_status`、`should_cutoff_event_physically_stop_sequence`、`resolve_mail_pending_draft_disposition`；响应显式 `review_only=true`、`review_required=true`、`real_sending_enabled=false`，真实 `deleted_pending_drafts_count=0`、`locked_pending_drafts_count=0`，仅返回 `planned_destroy_pending_drafts_count`、`planned_lock_pending_drafts_count` 和处置计划；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py` 通过。
- 已完成 Task 31：在 `backend/main.py` 的 `MailGenerateDraftResponse` 顶层新增并显式返回 `draft_status=drafted`、`review_required=true`、`review_mode=human_review_required`、`real_sending_enabled=false`，让 `POST /api/v1/mail/generate-draft` 的默认输出清楚表达为草稿态、需人工审核、不可真实发送；`safety_guardrail` 继续返回 `locked_for_approval`、`is_locked_for_approval=true`、`real_sending_enabled=false`；未写入数据库，未启用真实发信；`python3 -m py_compile backend/main.py` 通过；定向 `git diff --check` 通过。
- 已完成 Task 30：在 `backend/main.py` 为 `MailDraftIntentProfile` 新增 `commercial_terms` 结构，补齐 `MailDraftResolvedTerm`、`MailDraftCommercialTerms`、`_mail_commercial_placeholder`、`_resolve_mail_price_term`、`_resolve_mail_commercial_terms` 等 helper；`/api/v1/mail/generate-draft` 正文现统一输出价格/工期/折扣/账期的后端物理占位符，且仅当数据库中存在唯一有效 `PricingRule` 时价格才解析为后端规则值；同时新增 `_mail_sanitize_fewshot_reference_for_draft` 对 admitted Few-Shot 中的价格/工期/折扣/账期自由文本做占位符脱敏，避免历史商业条款直接穿透进草稿正文；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py` 通过。
- 已完成 Task 26：在 `backend/main.py` 新增 `MailGenerateDraftRequest`、`MailSafetyGuardrail`、`MailGenerateDraftResponse`、邮件草稿 helper 与 `POST /api/v1/mail/generate-draft`；接口复用 Sequence 策略和 Few-Shot 准入条件，仅生成待审核草稿响应，`real_sending_enabled=false`，不写库、不真实发信；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py` 通过；依赖环境 import smoke 因 WSL 到 PyPI DNS 临时错误未完成。
- 已完成 Task 27：在 `backend/main.py` 确认 `MailGenerateDraftRequest` 请求字段为 `customer_key`、`contact_email`、`scenario`、`suite_step`、`current_seller_name`、`current_seller_signature`，并新增 `extra = "forbid"` 禁止额外字段；未改动生成逻辑，未实现 Task 28+。
- 已完成 Task 28：通过 Codex CLI 审核 `backend/main.py`，确认 `MailGenerateDraftResponse`、`_build_mail_generate_draft_response` 与 `POST /api/v1/mail/generate-draft` 已完整覆盖 `mail_uid`、`final_subject`、`final_body_html`、`retrieved_fewshot_id`、`fewshot_match_score`、`safety_guardrail`；本轮无需新增代码改动。
- 已完成 Task 29：在 `backend/main.py` 新增 `MailDraftIntentProfile`、`MailDraftAssembledContent`、`_build_mail_draft_intent_profile`、`_mail_subject_from_intent_profile`、`_assemble_mail_draft_from_intent_profile`，将 `POST /api/v1/mail/generate-draft` 的内部生成链路改为二阶段：先把请求参数、序列策略与 admitted Few-Shot 汇总为结构化意图/画像，再统一组装 `final_subject` 与 `final_body_html`；保持 `MailGenerateDraftResponse` 响应字段不变，继续只返回 review-only 草稿；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py` 通过。
- 已完成 Task 23：在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceTriggerAnchor`、`MailSequenceStepInterval`、`DEFAULT_MAIL_SEQUENCE_STEP_DELAYS_DAYS`、`DEFAULT_MAIL_SEQUENCE_STEP_CUMULATIVE_MIN_DAYS`、`MAIL_SEQUENCE_STEP_INTERVALS`、`get_mail_sequence_step_interval` 与 `list_mail_sequence_step_intervals`，把 Step1 当天、Step2 7 天、Step3 10 天、Step4 10 天的默认草稿生成间隔沉淀为独立可复用元数据；新增 `docs/mail_sequence_step_intervals.md` 固化触发锚点、累计最小天数与中断优先级边界；三份现有 Sequence 场景文档已补充共享间隔引用。
- 已完成 Task 25：在 `backend/mail_sequence_strategy.py` 新增 `MailPendingDraftDispositionAction`、`MailPendingDraftDispositionRule`、`MAIL_UNSENT_DRAFT_STATUSES`、`MAIL_SENT_OR_TERMINAL_DRAFT_STATUSES`、`MAIL_PENDING_DRAFT_DISPOSITION_RULES`、`normalize_mail_pending_draft_disposition_action`、`get_mail_pending_draft_disposition_rule`、`resolve_mail_pending_draft_disposition`、`list_mail_pending_draft_disposition_rules`，正式固化客户回复/CRM 一般中断默认销毁 `pending`、销毁 `drafted`、锁定 `approved`，CRM 勿扰/联系人失效严格销毁全部未发送草稿，人工封印全量锁定未发送草稿；新增 `docs/mail_pending_draft_disposition.md` 固化执行口径；不实现数据库删除、不锁表、不真实发信，只提供邮件侧可复用规则契约。
- 已完成 Task 24：在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceCutoffEventType`、`MailSequenceInterruptionReason`、`MailSequenceCutoffRule`、`MAIL_SEQUENCE_CUTOFF_RULES`、`MAIL_SEQUENCE_CUTOFF_EVENT_TERMINAL_STATUS`、`normalize_mail_sequence_cutoff_event_type`、`normalize_mail_sequence_interruption_reason`、`get_mail_sequence_cutoff_rule`、`get_mail_sequence_cutoff_terminal_status`、`should_physically_stop_mail_sequence`、`should_cutoff_event_physically_stop_sequence`、`list_mail_sequence_cutoff_rules` 与 `list_mail_sequence_cutoff_rules_for_step`，明确客户邮件回复/同域回复/其他渠道回复、CRM 赢单/丢单/激活商机/投诉/禁止联系/人工跟进/联系人失效，以及销售/运营/主管人工封印时的物理切断规则和终态映射；不实现真实发送、不写入数据库，只提供邮件侧可复用状态机契约。
- 已完成 Task 22：在 `backend/mail_sequence_strategy.py` 新增 `MailSequenceStatus`、`MailSequenceStatusMetadata`、`MAIL_SEQUENCE_STATUSES`/`MAIL_SEQUENCE_TERMINAL_STATUSES`/`MAIL_SEQUENCE_REVIEW_STATUSES`/`MAIL_SEQUENCE_OUTBOUND_STATUSES`，并补齐 `normalize_mail_sequence_status`、`get_mail_sequence_status_metadata`、`list_mail_sequence_statuses_by_category`、`is_known_mail_sequence_status`、`is_terminal_mail_sequence_status` 等复用辅助函数，明确这些状态只服务邮件侧状态机/草稿链路，不开启真实发送。
- 已完成 Task 21：扩展 `backend/mail_sequence_strategy.py`，新增 `new_contact_intro` 场景枚举、共享字段说明、4-step 策略定义、查找函数与列表输出，供后续 Task 22-25、邮件草稿 API 和状态机复用。
- 已新增 `docs/mail_new_contact_intro_sequence.md`，沉淀 Task 21 的 4-step 策略说明、检索边界、CTA 风格、退出条件与后续复用建议。
- 已完成 Task 20：扩展 `backend/mail_sequence_strategy.py`，新增 `new_business_promotion` 场景枚举、共享字段说明、4-step 策略定义、查找函数与列表输出，供后续 Task 21-25、邮件草稿 API 和状态机复用。
- 已新增 `docs/mail_new_business_promotion_sequence.md`，沉淀 Task 20 的 4-step 策略说明、检索边界、CTA 风格、退出条件与后续复用建议。
- 已完成 Task 19：新增 `backend/mail_sequence_strategy.py`，落地 `re_activation` 4 轮策略的数据结构、检索过滤边界、CTA/主题提示、退出条件与后续 API/状态机复用字段。
- 已新增 `docs/mail_re_activation_sequence.md`，沉淀 Task 19 的 4-step 策略说明与 Task 20-25 复用建议。
- 已完成 Task 18：`backend/main.py` 已为 `excellent_reply`/人工反馈候选补齐审核门禁、手工 PATCH 回流同步，以及 promote 后解锁 Few-Shot 的反哺链路。
- 已创建 `AGENTS.md`
- 已创建 `TASKS.md`
- 已创建 `PROGRESS.md`
- 已创建 `TASK_HANDOFF.md`
- 已创建 `VALIDATION.md`
- 已创建 `logs/codex-run.log`
- 已创建 `logs/codex-retry.log`
- 已把邮件与企微隔离写入 `AGENTS.md`
- 已把邮件任务拆成 P0/P1/P2 写入 `TASKS.md`
- 已在 `PROGRESS.md` 记录当前阶段、未完成项和下一步
- 已在 `VALIDATION.md` 写入文档阶段和代码阶段验证标准
- 已把“恢复、重试、不中断”写入 `AGENTS.md` 最高优先级章节
- 已把 Hermes 短启动指令写入 `AGENTS.md`
- 已把 token/rate limit 自动重试、Codex 意外停止恢复、长任务监控、FINAL_REPORT 完成规则写入 `AGENTS.md`
- 已在 `AGENTS.md` 中补充 Windows 路径 `D:\items\QW` 与 WSL 路径 `/mnt/d/items/QW`
- 已明确 Hermes 与 Codex CLI 必须在 WSL 路径 `/mnt/d/items/QW` 下运行
- 已将 `PROGRESS.md` 当前状态推进为 Task 2 待开始
- 已检查 Task 11 相关代码链路：`backend/sync_crm_emails.py` 写入 `mail_raw_unified` 并调用 `raw_comm_service.upsert_mail_cleaned`，`backend/raw_comm_service.py` 清洗正文并写入 `mail_cleaned`，`backend/mail_sync.py` 包含基础邮件同步表创建逻辑。
- 已确认评分字段现状：`useful_score` 稳定存在于 `knowledge_chunk`、`knowledge_candidate`、`email_fragment_asset`；原始邮件清洗表 `mail_cleaned` 当前代码路径未稳定写入 `useful_score`，因此 Task 11 导出脚本会优先读 `mail_cleaned.useful_score`，不存在时用只读启发式计算 `computed_export_score`。
- 已新增 `backend/export_mail_gold_candidates.py`，输出字段覆盖来源、场景、质量分、脱敏状态，并生成 JSON/CSV/Markdown 文件到 `docs/mail_gold_candidates/`。
- 已运行 `python3 -m py_compile backend/export_mail_gold_candidates.py`，语法检查通过。
- 已成功导出首批 25 条邮件黄金候选切片，并验证 `docs/mail_gold_candidates/latest_mail_gold_candidates.json`、`.csv`、`.md` 均存在且非空。
- 已完成 Task 13：新增 `docs/mail_gold_snippet_schema.md`，字段结构对齐当前导出字段，并把 Task 14/15/16 相关字段显式标为预留。
- 已完成 Task 14：在 `docs/mail_gold_snippet_schema.md` 正式定义 `greetings`、`example`、`process`、`constraint`、`quotation` 五类 `snippet_type` 的用途、边界、判定规则、可包含/不可包含内容、示例字段建议、判定优先级与内容安全口径。
- 已完成 Task 15：在 `docs/mail_gold_snippet_schema.md` 正式定义 `re_activation`、`new_business_promotion`、`new_contact_intro` 三大场景，补齐场景目标、触发条件、禁用边界、推荐 `snippet_type` 组合、Sequence Step 1-4 映射，以及 `scenario`/`scenario_label`/`scenario_reason`/`sequence_step_hint` 的字段关系，并明确与 Task 16 过滤字段和后续安全门的边界。
- 已完成 Task 16：在 `docs/mail_gold_snippet_schema.md` 正式定义 `industry`、`country`、`customer_tier`、`product_line`、`payment_risk` 五类检索过滤字段，补齐正式枚举、来源优先级、归一化规则、缺失兜底、检索使用顺序，以及与 `scenario`、`snippet_type`、`sequence_step_hint` 和后续安全门的边界。
- 已完成 Task 17：在 `backend/config.py` 增加 `MAIL_FEWSHOT_MIN_USEFUL_SCORE=0.60`，在 `backend/main.py` 增加邮件 Few-Shot 准入辅助函数和只读接口 `/api/v1/mail/fewshot/retrieve`，并为 `email_fragment_asset` 增加准入索引定义；`docs/mail_gold_snippet_schema.md` 已同步 Task 17 实现口径。

## 未完成

- Task 43 尚未开始：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。
- 邮件 API 已完成 Task 26 草稿脚手架、Task 27 请求参数契约、Task 28 响应参数契约、Task 29 二阶段生成、Task 30 商业条款后端占位符装配与 Task 31 草稿态/审核态默认收口。
- 已实现邮件安全门中的财务价格底线门、价格正则扩展、履约工期 SLA 校准门、收件域名防泄密门，以及竞对域名黑名单/客户域名白名单双校验；尚未实现敏感词扫描与统一红黄牌结果结构。
- 未实现邮件前端。

## 已修改文件

- `AGENTS.md`
- `TASKS.md`
- `PROGRESS.md`
- `TASK_HANDOFF.md`
- `VALIDATION.md`
- `logs/codex-run.log`
- `logs/codex-retry.log`
- `backend/export_mail_gold_candidates.py`
- `backend/config.py`
- `backend/database.py`
- `backend/main.py`
- `backend/mail_sequence_strategy.py`
- `backend/mail_sla_guardrail.py`
- `backend/mail_sla_guardrail_checks.py`
- `docs/mail_gold_snippet_schema.md`
- `docs/mail_new_contact_intro_sequence.md`
- `docs/mail_new_business_promotion_sequence.md`
- `docs/mail_re_activation_sequence.md`
- `docs/mail_sequence_step_intervals.md`
- `docs/mail_pending_draft_disposition.md`

## 最近中断记录

| 时间 | 类型 | 原因 | 当前任务 | 下一步 |
|---|---|---|---|---|
| 2026-05-26 08:05:35 +0800 | usage limit / 可恢复中断 | `codex exec --sandbox workspace-write ...` 执行 Task 42 时返回 `You've hit your usage limit ... try again at 11:51 AM`；已按规则记录后由当前 Agent 接手完成同一安全任务 | Task 42：实现竞对域名黑名单与客户域名白名单 | 已完成本轮代码修改与验证；下一轮继续 Task 43 |
| 2026-05-22 15:30:52 +08:00 | 权限/执行拦截 | 启动 `codex exec --full-auto ...` 后台任务时返回 `BLOCKED: User denied. Do NOT retry.` | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 需要人工确认是否允许在当前环境放行 Codex CLI 执行；未放行前不要自动重试 |
| 2026-05-22 15:38:23 +08:00 | 规则澄清 | 已确认 `BLOCKED: User denied. Do NOT retry.` 不是 token/rate/network 临时错误，不能自动重试或危险绕过 | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 可由用户在 Hermes 环境放行 `codex exec --full-auto`；若当前 Agent 能安全完成，可记录后继续执行同一任务 |
| 2026-05-22 15:39:26 +08:00 | 权限策略修正 | 用户明确 `--full-auto` 是默认自动执行模式，普通安全任务不要逐次授权 | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 已更新 AGENTS.md，明确普通项目内开发任务默认自动执行；仅高风险清单需要人工确认 |
| 2026-05-22 16:10:11 +08:00 | 环境层阻断 | 用户明确给出 `codex exec --full-auto ...` 启动命令，但 Hermes terminal 仍返回 `BLOCKED: User denied. Do NOT retry.` | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 不自动重试；需要环境层放行，或改由当前 Agent 直接完成 Task 2 |
| 2026-05-22 16:05:57 +08:00 | 命令构造错误 | Hermes 生成 `codex exec --full-auto "$(python -c ...)"`，被环境判定为 `Dangerous Command: script execution via -e/-c flag` | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 不要授权 `python -c` 包装模式；改用直接 `codex exec --full-auto "短任务内容"`，或由当前 Agent 继续安全任务 |
| 2026-05-22 16:45:35 +08:00 | 依赖/网络阻断 | 当前 WSL Python 缺少 `sqlalchemy` 且无 `pip`/`ensurepip`；尝试 `UV_CACHE_DIR=/tmp/uv-cache uv run --with-requirements backend/requirements.txt ...` 时 PyPI DNS 解析失败 | Task 11：输出首批邮件黄金候选切片 | 网络或依赖环境恢复后重跑导出命令；不要把未导出的真实数据伪装为已完成 |
| 2026-05-22 16:58:08 +08:00 | 自动重试已建立 | 已创建本地 cron 任务 `fb402953d033`，按 `every 30m` 自动重试 Task 11 导出，共 5 次 | Task 11：输出首批邮件黄金候选切片 | 等待后续重试结果；成功后需验证 latest JSON/CSV/Markdown 文件并更新状态 |
| 2026-05-22 16:55:56 +08:00 | 监控规则偏差 | Hermes/Codex 前台长时间运行时未按每 5 分钟追加 `logs/codex-run.log` 心跳 | Task 11：输出首批邮件黄金候选切片 | 已补充规则：前台/后台长任务都必须每 5 分钟写心跳；前台无法写时恢复后补记运行时长、最后输出和下一步 |
| 2026-05-22 17:42:17 +08:00 | 恢复完成 | `uv run --with-requirements` 本次成功拉起依赖并完成 Task 11 导出，latest JSON/CSV/Markdown 已生成 | Task 11：输出首批邮件黄金候选切片 | 转入 Task 13：设计邮件黄金切片字段结构 |

## Token / Rate Limit 记录

| 时间 | 错误类型 | 错误内容 | 重试次数 | 下一次重试 | 是否恢复 |
|---|---|---|---|---|---|
| 2026-05-26 08:05:35 +0800 | usage limit | `codex exec --sandbox workspace-write ...` 执行 Task 42 时返回 `You've hit your usage limit ... try again at 11:51 AM` | 1 | 无（本轮已由当前 Agent 接手完成同一安全任务） | 是 |
| 2026-05-22 16:45:35 +08:00 | 网络临时错误 | `uv` 安装项目声明依赖时访问 `https://pypi.org/simple/openpyxl/` 失败：`Temporary failure in name resolution` | 1 | 2026-05-22 17:29 +08:00（cron `fb402953d033`） | 否 |
| 2026-05-22 17:42:17 +08:00 | 恢复成功 | 同一导出命令本次成功安装/解析声明依赖并完成 25 条脱敏候选导出 | 2 | 无 | 是 |
| 2026-05-26 02:50:49 +08:00 | 网络临时错误 | Task 33 复审时 `backend/main.py` 直接导入冒烟先因当前 WSL 缺少 `sqlalchemy` 失败；随后 `uv run --with-requirements backend/requirements.txt ...` 拉取声明依赖时访问 PyPI 的 `psycopg` DNS 解析失败 | 1 | 下一个 cron tick 或网络恢复后 | 否 |

## 运行环境与网络待解决（2026-05-22 补充）

### Hermes 监督引擎已配置（gateway 常驻服务）

- 已确认 Hermes 长任务持续运行的引擎是 **gateway 后台 ticker（每 60 秒 tick 一次）**，聊天会话本身不是调度器；此前 cron 不触发的根因是 gateway 未运行。
- 已执行 `hermes gateway install`，gateway 作为 systemd 用户服务 `hermes-gateway.service` 运行：`enabled`（登录/开机自启）+ `active`，单元自带 `Restart=always`，`Linger=yes`（注销后存活）。
- 已设 `HERMES_CRON_TIMEOUT=0`、`HERMES_AGENT_TIMEOUT=0`（写入 `~/.hermes/.env` 与服务单元 `Environment=`，已在 live 进程确认生效），长 codex 任务不再被 600s 不活动超时杀掉。
- 已实测：gateway 配好后 cron 每 2 分钟自动触发；`fb402953d033`（Task 11 重试）于本轮自动触发并完成 Task 11 导出。
- 用户在 Hermes 聊天框用 `/cron add "every Nm" "..."` 建可恢复长任务即可无人值守接力；物理限制：`wsl --shutdown` 或关机后 gateway 停，需 VPS/云才能真正 7×24。

### 网络待解决问题

| 问题 | 现象 | 待办 |
|---|---|---|
| WSL→PyPI 的 DNS 间歇异常 | `getent hosts pypi.org` 曾解析到保留测试段 `198.18.x.x`；16:45 uv 装依赖失败（`Temporary failure in name resolution`），17:42 又恢复成功 —— 不稳定 | DNS 稳定期可在 WSL 装依赖；否则改走 Windows Python（sqlalchemy 2.0.44，已验证可跑出 25 条） |
| Hermes/Codex 模型后端间歇断连 | 调 `https://chatgpt.com/backend-api/codex` 出现 `APIConnectionError`、`stale 300s ... Killing connection` | 网络稳定期重试；codex 实测此刻可连通（`codex exec` 返回 PROOF_OK，exit 0） |
| cron 状态"假绿" | 任务内部失败时 `jobs.json` 的 `last_status` 仍可能写 `ok` | 以实际产出文件 + `~/.hermes/cron/output/<job_id>/` 执行记录为准，不依赖 `last_status` |

## 建议下一步

继续 Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。

```bash
python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py
python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py
git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log
```

Task 11 完成后可复查：

1. `docs/mail_gold_candidates/latest_mail_gold_candidates.json`
2. `docs/mail_gold_candidates/latest_mail_gold_candidates.csv`
3. `docs/mail_gold_candidates/latest_mail_gold_candidates.md`

Task 34 已完成：`backend/main.py` 现已为邮件侧 `POST /api/v1/sequence/interrupt` 补齐销售手动强封印 review-only 支持，可接受 `interrupt_reason=manual_seal`、`sales_manual_seal`、`manual_sealed_by_sales` 等调用，并返回 `manual_seal_trigger` 预览；后续 Task 35/36/37 仍需补齐按客户/域名/联系人维度中断、真实待发草稿删除或锁定数量、以及邮件安全/操作日志写入。

## 重要约束

- 不要删除或改写 `项目进展.md` 既有历史内容。
- 不要把邮件 Sequence 状态写入企微会话状态机。
- 不要让邮件测试阻塞企微 8071 后端现有使用。
- 不要默认开启真实邮件发送。
- 不要把 Mock 数据描述为真实生产数据。
- 不要暴露真实客户敏感信息、API Key、数据库密码或内部底价。
- `codex exec --sandbox workspace-write` 是默认自动执行模式（旧 `--full-auto` 已废弃，等价）；项目内普通读写、测试、lint、build、代码生成脚本不应逐次请求授权。
- `BLOCKED: User denied. Do NOT retry.` 对普通安全任务而言属于环境未放行自动执行，不得自动重试，不得用危险参数绕过；用户放行后应继续同一任务。
- 如果 Codex CLI 委派被拒绝，但任务可由当前 Agent 安全完成，可以记录阻断原因后继续同一个任务，仍需运行验证并更新状态文件。
- Git 提交、推送远程仓库、创建 Git tag、发布 release、普通数据库写入不需要额外人工确认。
- 数据库迁移、清库、批量更新、批量删除仍需停止并请求人工确认。
- `backend/requirements.txt` 中已声明的依赖属于项目已知依赖，可自动安装。WSL Python 缺依赖且 PyPI DNS 不稳时，可改走 Windows Python（已验证 sqlalchemy 2.0.44 可跑）或 `uv run --with-requirements backend/requirements.txt python ...`。
- Codex CLI 启动命令必须直接使用 `codex exec --sandbox workspace-write "任务内容"`；不要用 `python -c`、`node -e`、`eval`、`$()`、反引号或 heredoc 动态拼接命令。
- 运行方式为 gateway + cron 循环：每个 cron tick 独立只做第一个未完成任务，用中文写 `logs/codex-run.log`（成功与失败都写，严禁"假绿"）；失败由 cron 周期（间隔 2 分钟）自动重试，不丢任务。不再要求单次会话内每 5 分钟心跳。

## 恢复提示词建议（gateway + cron 循环版）

前提：gateway 已配为常驻服务（systemd 用户服务，开机/登录自启），`HERMES_CRON_TIMEOUT=0`/`HERMES_AGENT_TIMEOUT=0` 已 drop-in 固化。无人值守长任务**在 WSL 终端**用 `hermes cron create` 建立（必须带 `--workdir`，聊天框 `/cron add` 不认 `--workdir` 会跑错目录）：

```bash
hermes cron create "every 2m" '请加载 codex skill。当前目录是 Git 项目，通过 Codex CLI 执行任务，不要控制 Windows 的 Codex 插件或桌面版。读取 TASK_HANDOFF.md、TASKS.md、PROGRESS.md、VALIDATION.md 和 git diff，只继续第一个未完成任务。硬性顺序：先在 logs/codex-run.log 用中文写一条 START(时间/任务号/将做什么)，再开始干；完成后先按 VALIDATION.md 验证，再更新 TASKS.md/PROGRESS.md/TASK_HANDOFF.md，最后在 logs/codex-run.log 用中文写一条 DONE(成功或失败/验证结果/下一步)。START 和 DONE 两条日志不可省略，报错另写 logs/codex-retry.log。写任何文件只写真实内容，严禁在行首加 行号| 前缀(如 12|)，更新前先读真实内容、更新后自检首行不是数字加竖线。若 TASKS.md 全部完成则生成 FINAL_REPORT.md 并在 logs/codex-run.log 末尾追加 ALL TASKS COMPLETED 加当前时间，然后停止；不要再新建其他 cron 任务。' --workdir /mnt/d/items/QW --deliver local
```

建完 `hermes cron list` 确认 `Workdir: /mnt/d/items/QW`、`Schedule: every 2m`，再 `hermes cron run <ID>` 立即开跑。

每个 cron tick 的执行口径：
1. 只处理 TASKS.md 第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
2. 调用 Codex CLI 用 `codex exec --sandbox workspace-write "短任务内容"`，不要用 python -c/node -e/eval/$()/反引号/heredoc 拼接。
3. 硬性顺序：先在 logs/codex-run.log 用中文写一条 START（时间/任务号/将做什么），再开始干；最后写一条 DONE（成功或失败/验证结果/下一步）。START 和 DONE 不可省略；报错另写 logs/codex-retry.log；失败如实写，严禁"假绿"。
4. 任务完成后先按 VALIDATION.md 验证，再更新 TASKS.md/PROGRESS.md/TASK_HANDOFF.md，最后才写 DONE。
5. 遇到 token/rate limit/429/网络临时错误：本轮记录后结束，由 cron 周期自动重试，不放弃任务。
6. 遇到登录失败、需人工授权、危险命令、删除大量文件、生产配置、密钥、数据库迁移/清库/批量更新/批量删除：停止并写入 TASK_HANDOFF.md，不自动继续。
7. TASKS.md 全部完成则生成 FINAL_REPORT.md，并在 logs/codex-run.log 末尾追加 ALL TASKS COMPLETED 加当前时间，然后停止；不要再新建其他 cron 任务。

查看/停止：`hermes cron list`、`hermes cron status`、`~/.hermes/cron/output/<job_id>/`；完成确认后 `hermes cron remove <job_id>`。
