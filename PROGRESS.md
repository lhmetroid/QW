# PROGRESS

## 当前状态

- 当前任务：Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本
- 当前小点：Task 42 已完成；`backend/main.py` 已将收件域名防泄密门升级为“竞对域名黑名单 + 客户域名白名单”双校验，新增 `MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST`、`MAIL_CONFIDENTIALITY_CUSTOMER_DOMAIN_WHITELIST_BY_CUSTOMER_KEY`、`_mail_customer_domain_whitelist` 与通用域名匹配 helper；`POST /api/v1/mail/generate-draft` 现会在竞对/风险域名红牌拦截之外，额外要求 `contact_email` 与 `cc_emails` 落在当前客户域名白名单内，否则按 `non_whitelisted_customer_domain` 红牌阻断，继续保持 review-only、不真实发信。
- 状态：Task 42 已完成，下一步进入 Task 43
- 最近更新时间：2026-05-26 08:09:05 +0800

## 最近完成的小点

| 时间 | 任务 | 小点 | 结果 | 验证 |
|---|---|---|---|---|
| 2026-05-26 08:09:05 +0800 | Task 42 | 实现竞对域名黑名单与客户域名白名单 | 已完成 | `backend/main.py` 已将收件域名防泄密门升级为“竞对域名黑名单 + 客户域名白名单”双校验：新增 `MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST`、`MAIL_CONFIDENTIALITY_CUSTOMER_DOMAIN_WHITELIST_BY_CUSTOMER_KEY`、`_mail_customer_domain_whitelist` 与通用域名匹配 helper；`POST /api/v1/mail/generate-draft` 现会在保留竞对/风险域名红牌拦截的同时，要求 `contact_email` 与 `cc_emails` 落在当前客户域名白名单内，否则按 `non_whitelisted_customer_domain` 红牌阻断；`backend/mail_recipient_domain_guardrail_checks.py` 已补充非白名单域名阻断、客户白名单别名放行与竞对黑名单断言；本轮 Codex CLI 因 usage limit 中断后已按规则记录并由当前 Agent 接手完成；`python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log` 通过。 |
| 2026-05-26 07:50:44 +0800 | Task 41 | 实现收件域名与抄送域名防泄密门 | 已完成 | `backend/main.py` 已新增 `_evaluate_mail_recipient_domain_confidentiality_guardrail`、域名归一化与竞对/风险域名拦截逻辑；`POST /api/v1/mail/generate-draft` 现会同时校验 `contact_email` 与可选 `cc_emails`，命中后返回 `status=blocked_by_recipient_domain_confidentiality_gate`、`safety_guardrail.status=red_card_hard_block`、`red_card_code=blocked_by_recipient_domain_confidentiality_gate`、`draft_status=blocked`、`real_sending_enabled=false` 与 `block_details`；新增 `backend/mail_recipient_domain_guardrail_checks.py` 定向校验竞对收件人、风险抄送和正常客户域名；`python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 07:41:35 +0800 | Task 40 | 实现履约工期 SLA 校准门，低于标准 SLA 时物理拉正并黄牌锁定 | 已完成 | `backend/main.py` 已接入 `backend/mail_sla_guardrail.py` 的工期校准门，并把标准交期默认值收口为后端 `3 business days`；`POST /api/v1/mail/generate-draft` 现会把 `24 hours`、`1 day`、`next-day delivery` 等低于标准 SLA 的承诺物理替换为标准 SLA，并返回 `safety_guardrail.status=yellow_card_sla_calibrated_locked`、黄牌 warning、`block_details` 与锁定审核态；`python3 -m unittest backend/mail_sla_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_sla_guardrail.py backend/mail_sla_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_sla_guardrail.py backend/mail_sla_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 07:31:09 +0800 | Task 39 | 实现价格正则提取，识别 RMB、元、USD、美元、per word、每千字、折扣等表达 | 已完成 | `backend/main.py` 已扩展 `_mail_pricing_context_unit`、`_mail_pricing_context_currency`、`_mail_explicit_price_mention_type`、`_extract_mail_explicit_price_mentions` 与 `_mail_floor_rule_for_price_mention`，补齐 RMB/CNY/人民币/元/USD/美元/美金/$/￥、per word、每词、每千字/千字符/1k、discount 10%/10% off/8折 等识别；`_evaluate_mail_financial_price_floor_guardrail` 现会跳过 `mention_type=discount`，避免把折扣表达误当作底价穿透红牌；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过；抽取冒烟脚本已确认 CNY/USD/per word/每千字/折扣样例均可识别。 |
| 2026-05-26 07:20:01 +0800 | Task 38 | 实现财务价格底线门，低于底价红牌硬拦截 | 已完成 | `backend/main.py` 已为 `MailSafetyGuardrail` 新增 `hard_block` / `red_card_code` / `blocked_by` / `block_details`，补齐 `_active_mail_pricing_rules`、`_extract_mail_explicit_price_mentions`、`_mail_floor_rule_for_price_mention`、`_evaluate_mail_financial_price_floor_guardrail`；`POST /api/v1/mail/generate-draft` 现会对草稿正文与已解析商业价格执行底价校验，命中低于有效 `PricingRule.price_min` 时返回 `status=blocked_by_financial_safety_gate`、`safety_guardrail.status=red_card_hard_block`、`draft_status=blocked`、`real_sending_enabled=false` 与 `block_details`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过；静态断言脚本输出 `task38_static_ok`。 |
| 2026-05-26 07:09:41 +0800 | Task 37 | 中断事件写入邮件安全或操作日志 | 已完成 | `backend/main.py` 已新增 `MailSequenceInterruptOperationLogEntry`；`MailSequenceInterruptResponse` 顶层新增 `operation_log_entry`；`_build_mail_sequence_interrupt_response` 会构造 `operation_log_entry`、在 `audit_preview` 回传同一份日志预览，并通过 `logger.info("MAIL_SEQUENCE_INTERRUPT_REVIEW_ONLY ...")` 输出 review-only 中断操作日志；继续保持 `review_only=true`、`real_sending_enabled=false`、不写数据库、不真实删除或锁定草稿、不真实发信；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 07:00:25 +08:00 | Task 36 | 中断后返回被删除或锁定的待发草稿数量 | 已完成 | `backend/main.py` 已将 `deleted_pending_drafts_count` / `locked_pending_drafts_count` 改为按 planned dispositions 统计，并在 `audit_preview` 返回相同计数、`count_basis=planned_pending_draft_dispositions_only`、`will_write_database=false`、`will_delete_pending_drafts=false`、`will_lock_pending_drafts=false`、`will_send_email=false`；保持 review-only，不写库、不真实删锁草稿、不真实发信；`python3 -m py_compile backend/main.py` 通过。 |
| 2026-05-26 06:54:32 +08:00 | Task 35 | 支持按客户、域名、联系人维度中断 | 已完成 | `backend/main.py` 已将 `MailSequenceInterruptRequest.customer_key` 调整为可选，并校验 `customer_key`、`recipient_domain`、`contact_email` 至少一个存在；新增 `_build_mail_sequence_interrupt_scope`，响应与 `audit_preview` 返回 `interruption_scope`、`interruption_target`、`scope_targets`；继续保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`/`locked_pending_drafts_count=0`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py logs/codex-run.log` 通过。 |
| 2026-05-26 03:00:29 +08:00 | Task 34 | 支持销售手动强封印 | 已完成 | `backend/main.py` 已为 `MailSequenceInterruptRequest` 新增 `manual_seal_actor`、`manual_seal_reason`、`operator_id`、`sealed_at`，为 `MailSequenceInterruptResponse` 新增 `manual_seal_trigger`；`POST /api/v1/sequence/interrupt` 支持 `interrupt_reason=manual_seal`、`sales_manual_seal`、`manual_sealed_by_sales` 等别名，并复用 `mail_sequence_strategy` 的 `manual_sealed_by_sales` 切断规则与人工封印草稿处置规则；保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`/`locked_pending_drafts_count=0`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 02:42:14 +08:00 | Task 33 | 支持 CRM 状态变更触发中断 | 已完成 | `backend/main.py` 已为 `MailSequenceInterruptRequest` 新增 `crm_event_type`、`crm_stage`、`previous_crm_stage`、`crm_changed_at`，并新增 CRM 阶段别名归一化/校验与 `crm_state_change_trigger` 响应预览；`POST /api/v1/sequence/interrupt` 现支持 `interrupt_reason=crm_state_change` + `crm_event_type=CRM_STAGE_CHANGED_TO_WON` 等 CRM 状态变更触发，同时保持 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`/`locked_pending_drafts_count=0`；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 02:30:06 +08:00 | Task 32 | 设计并实现 `POST /api/v1/sequence/interrupt` | 已完成 | `backend/main.py` 已新增 `MailSequenceInterruptRequest`、`MailSequenceInterruptResponse`、中断响应构造 helper 与 `POST /api/v1/sequence/interrupt`；接口复用 `get_mail_sequence_cutoff_rule`、`get_mail_sequence_cutoff_terminal_status`、`should_cutoff_event_physically_stop_sequence`、`resolve_mail_pending_draft_disposition`，返回 `review_only=true`、`real_sending_enabled=false`、真实 `deleted_pending_drafts_count=0`/`locked_pending_drafts_count=0` 与 planned 草稿处置计数；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py` 通过。 |
| 2026-05-26 02:21:30 +08:00 | Task 31 | 生成结果默认进入草稿与审核态且不默认真实发送 | 已完成 | `backend/main.py` 已在 `MailGenerateDraftResponse` 顶层新增并显式返回 `draft_status=drafted`、`review_required=true`、`review_mode=human_review_required`、`real_sending_enabled=false`；`safety_guardrail` 继续返回 `locked_for_approval`、`is_locked_for_approval=true`、`real_sending_enabled=false`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过。 |
| 2026-05-26 02:08:17 +08:00 | Task 30 | 邮件正文商业条款优先走后端物理占位符填充 | 已完成 | `backend/main.py` 已新增 `MailDraftCommercialTerms`、`_mail_commercial_placeholder`、`_resolve_mail_commercial_terms` 与 `admitted_fewshot_content` 商业条款脱敏逻辑；`/api/v1/mail/generate-draft` 正文现优先输出价格/工期/折扣/账期后端占位符，且在仅存在唯一有效 `PricingRule` 时价格可解析为后端规则值；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py` 通过。 |
| 2026-05-26 01:55:23 +08:00 | Task 29 | 将邮件草稿生成重构为二阶段流程 | 已完成 | `backend/main.py` 已新增 `MailDraftIntentProfile`、`MailDraftAssembledContent`、`_build_mail_draft_intent_profile`、`_mail_subject_from_intent_profile`、`_assemble_mail_draft_from_intent_profile`，先把请求/序列策略/Few-Shot 汇总为结构化画像，再统一组装 `final_subject`/`final_body_html`；`python3 -m py_compile backend/main.py` 通过；`git diff --check -- backend/main.py` 通过。 |
| 2026-05-25 23:11:38 +08:00 | Task 28 | 核对 `POST /api/v1/mail/generate-draft` 响应参数契约 | 已完成 | 通过 Codex CLI 审核确认 `backend/main.py` 现有 `MailGenerateDraftResponse`、响应构造器和接口声明已完整覆盖 `mail_uid`、`final_subject`、`final_body_html`、`retrieved_fewshot_id`、`fewshot_match_score`、`safety_guardrail`；无需额外代码改动；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；响应契约脚本校验输出 `task28_contract_ok`。 |
| 2026-05-25 22:54:58 +08:00 | Task 27 | 收紧 `POST /api/v1/mail/generate-draft` 请求参数契约 | 已完成 | `MailGenerateDraftRequest` 保持 6 个约定字段，并新增 `extra = "forbid"` 禁止额外请求字段；未实现 Task 28+；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过。 |
| 2026-05-25 22:45:52 +08:00 | Task 26 | 设计并实现 `POST /api/v1/mail/generate-draft` | 已完成 | `backend/main.py` 已新增 `MailGenerateDraftRequest`、`MailSafetyGuardrail`、`MailGenerateDraftResponse`、邮件草稿 helper 与 `POST /api/v1/mail/generate-draft`；接口复用 Sequence 策略和 Few-Shot 准入条件，仅生成待审核草稿响应，`real_sending_enabled=false`，不写库、不真实发信；`python3 -m py_compile backend/main.py backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/main.py` 通过；`UV_CACHE_DIR=/tmp/uv-cache uv run --with-requirements backend/requirements.txt ...` 冒烟导入因 PyPI DNS 解析 `extract-msg` 失败未执行完成，已记录为网络依赖验证阻断，不影响本轮语法与定向 diff 验证。 |
| 2026-05-25 22:18:43 +08:00 | Task 25 | 实现待发草稿销毁或锁定规则 | 已完成 | `backend/mail_sequence_strategy.py` 已新增 `MailPendingDraftDispositionAction`、`MailPendingDraftDispositionRule`、`MAIL_UNSENT_DRAFT_STATUSES`、`MAIL_SENT_OR_TERMINAL_DRAFT_STATUSES`、`MAIL_PENDING_DRAFT_DISPOSITION_RULES`、`normalize_mail_pending_draft_disposition_action`、`get_mail_pending_draft_disposition_rule`、`resolve_mail_pending_draft_disposition`、`list_mail_pending_draft_disposition_rules`，覆盖客户回复、CRM 一般中断、CRM 勿扰/联系人失效严格销毁、人工封印全锁定四类口径；新增 `docs/mail_pending_draft_disposition.md` 固化规则；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；处置规则冒烟检查输出 `task25_smoke_ok`；定向 `git diff --check -- backend/mail_sequence_strategy.py logs/codex-run.log TASKS.md PROGRESS.md TASK_HANDOFF.md` 通过；`rg -n "[ \	]+$" backend/mail_sequence_strategy.py docs/mail_pending_draft_disposition.md TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log` 未发现新增行尾空白。 |
| 2026-05-25 22:03:40 +08:00 | Task 24 | 定义状态机物理切断规则 | 已完成 | `backend/mail_sequence_strategy.py` 已新增 `MailSequenceCutoffEventType`、`MailSequenceInterruptionReason`、`MailSequenceCutoffRule`、`MAIL_SEQUENCE_CUTOFF_RULES`、`MAIL_SEQUENCE_CUTOFF_EVENT_TERMINAL_STATUS`、`normalize_mail_sequence_interruption_reason`、`get_mail_sequence_cutoff_rule`、`get_mail_sequence_cutoff_terminal_status`、`should_physically_stop_mail_sequence`、`should_cutoff_event_physically_stop_sequence`、`list_mail_sequence_cutoff_rules`、`list_mail_sequence_cutoff_rules_for_step`；覆盖客户邮件回复、同域回复、其他渠道回复、CRM 赢单/丢单/激活商机/投诉/禁止联系/人工跟进/联系人失效，以及销售/运营/主管人工封印；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；物理切断规则冒烟检查输出 `cutoff_rules_ok`；定向 `git diff --check -- backend/mail_sequence_strategy.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 通过 |
| 2026-05-25 21:34:06 +08:00 | Task 23 | 定义 Step 触发间隔 | 已完成 | `backend/mail_sequence_strategy.py` 已新增 `MailSequenceTriggerAnchor`、`MailSequenceStepInterval`、`DEFAULT_MAIL_SEQUENCE_STEP_DELAYS_DAYS`、`DEFAULT_MAIL_SEQUENCE_STEP_CUMULATIVE_MIN_DAYS`、`MAIL_SEQUENCE_STEP_INTERVALS`、`get_mail_sequence_step_interval`、`list_mail_sequence_step_intervals`；新增 `docs/mail_sequence_step_intervals.md`；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；三场景四步骤间隔断言检查输出 `intervals_ok`；定向 `git diff --check -- backend/mail_sequence_strategy.py docs/mail_sequence_step_intervals.md docs/mail_re_activation_sequence.md docs/mail_new_business_promotion_sequence.md docs/mail_new_contact_intro_sequence.md` 通过 |
| 2026-05-25 21:14:25 +08:00 | Task 22 | 定义 Sequence 状态枚举 | 已完成 | `backend/mail_sequence_strategy.py` 已补齐 `MailSequenceStatus`/`MailSequenceStatusMetadata`、`MAIL_SEQUENCE_*_STATUSES` 分类常量、`normalize_mail_sequence_status`、`is_known_mail_sequence_status`、`list_mail_sequence_statuses_by_category` 等辅助函数；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；状态枚举冒烟检查输出 `pending,drafted,approved,sent,replied,interrupted,blocked`；定向 `git diff --check -- backend/mail_sequence_strategy.py` 通过 |
| 2026-05-25 18:23:50 +08:00 | Task 21 | 落地新接手联系人介绍 `new_contact_intro` 的 4 轮策略 | 已完成 | 扩展 `backend/mail_sequence_strategy.py` 新增 `new_contact_intro` 场景与 4-step 检索/禁用边界/退出条件；新增 `docs/mail_new_contact_intro_sequence.md`；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；`get_mail_sequence_step("new_contact_intro", 4)` 导入冒烟检查通过；目标文件定向 `git diff --check` 通过 |
| 2026-05-25 18:12:43 +08:00 | Task 20 | 落地新业务推广 `new_business_promotion` 的 4 轮策略 | 已完成 | 扩展 `backend/mail_sequence_strategy.py` 新增 `new_business_promotion` 场景与 4-step 检索/禁用边界/退出条件；新增 `docs/mail_new_business_promotion_sequence.md`；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；`get_mail_sequence_step("new_business_promotion", 4)` 导入冒烟检查通过；目标文件与状态文件定向 `git diff --check` 通过 |
| 2026-05-25 17:47:30 +08:00 | Task 19 | 落地老客户唤醒 `re_activation` 的 4 轮策略 | 已完成 | 新增 `backend/mail_sequence_strategy.py` 与 `docs/mail_re_activation_sequence.md`；`python3 -m py_compile backend/mail_sequence_strategy.py` 通过；`git diff --check -- backend/mail_sequence_strategy.py docs/mail_re_activation_sequence.md` 通过；导入冒烟检查 `get_mail_sequence_step("re_activation", 4)` 通过 |
| 2026-05-25 16:16:51 +08:00 | Task 17 | 实现邮件 Few-Shot 检索准入阈值 | 已完成 | `python3 -m py_compile backend/main.py backend/database.py backend/config.py` 通过；目标文件定向 `git diff --check` 通过；全仓 `git diff --check` 仍受既有无关文件历史行尾空白影响 |
| 2026-05-25 17:24:55 +08:00 | Task 18 | 实现人工纠偏后的高质量切片反哺逻辑 | 已完成 | `python3 -m py_compile backend/main.py backend/intent_engine.py backend/config.py` 通过；`git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log` 通过；全仓 `git diff --check` 仍受既有无关文件历史行尾空白影响 |
| 2026-05-25 15:29:06 +08:00 | Task 15 | 定义邮件切片适用场景 | 已完成 | `docs/mail_gold_snippet_schema.md` 已正式定义 `re_activation`/`new_business_promotion`/`new_contact_intro`，并补齐场景目标、触发条件、禁用边界、推荐 `snippet_type` 组合、Sequence Step 1-4 映射及字段关系；`git diff --check -- docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log` 通过 |
| 2026-05-25 14:49:00 | Task 14 | 定义邮件切片类型 | 已完成 | `docs/mail_gold_snippet_schema.md` 已正式定义 `greetings`/`example`/`process`/`constraint`/`quotation`，并补齐边界、判定规则、可包含/不可包含内容、优先级与内容安全口径 |
| 2026-05-25 10:11:31 | Task 6-12 | 重新清洗并修复 body_main_text 为空的误伤邮件数据 | 已完成 | 成功修复并重洗 2,838 封空 main_text 记录，完美恢复 429 封 |
| 2026-05-25 10:13:00 | Task 6-12 | 完成 20 年 CRM 全量 57.8 万封往来邮件的大同步抓取 | 已完成 | task-987 同步成功，新增: 465,576 封, 数据库总数: 800,163 封 |
| 2026-05-25 14:20:18 | Task 13 | 设计邮件黄金切片字段结构 | 已完成 | 新增 `docs/mail_gold_snippet_schema.md`，对齐 latest 候选导出字段，并明确 Task 14/15/16 字段仅预留 |
| 2026-05-22 18:40:00 | Task 11 | 修复 'sales' 与 'seller' 数据判断 Bug 并成功导出黄金案例 | 已完成 | 成功过滤脱敏导出 25 条 useful_score >= 0.60 黄金候选切片 |
| 2026-05-22 18:41:00 | Task 6-12 | 启动 20 年 CRM 全量往来邮件大同步与洗涤任务 | 已完成 | 后台 task-987 已全速完成 57.8 万封邮件增量大拉取 |
| 2026-05-22 15:56:08 | Task 6-12 | 修复 PG 绑定参数与批次表字段 Bug | 已完成 | 试跑 10 封数据完美插入并洗涤，0 失败 |
| 2026-05-22 16:01:08 | Task 12 | 引入内存高速排重与每 200 封批量 commit 事务优化 | 已完成 | 去重查询次数降为 1 次，同步吞吐量飙升 100x 至 ~90 封/秒 |
| 2026-05-22 16:05:31 | Task 6-12 | 启动 365 天 11.2 万封 CRM 邮件全量同步与洗涤任务 | 已完成 | 后台 task-855 已成功同步并清洗 19,600+ 封邮件 |
| 2026-05-22 16:45:35 | Task 11 | 检查邮件导出链路、数据表与评分字段，新增黄金候选切片导出脚本 | 部分完成 | `python3 -m py_compile backend/export_mail_gold_candidates.py` 通过；实际导出因缺少 `sqlalchemy` 且 PyPI DNS 失败暂未执行 |
| 2026-05-22 17:42:17 | Task 11 | 执行首批邮件黄金候选导出并验证 latest 输出文件 | 已完成 | `uv run ... export_mail_gold_candidates.py --limit 25 --min-score 0.60` 成功导出 25 条；latest JSON/CSV/MD 均存在且非空 |

## 初始化说明

已完成标准项目状态文件建立，并全面进入阶段一（数据采矿与清洗）的交付阶段。

## 当前目标

全量抓取、洗涤并结构化 CRM 系统中的高价值历史跟进邮件，建立起干净无污染、结构标准、隔离明确的邮件知识库底层基建。

## 已完成

- 已完成邮件与企微系统的物理与逻辑命名空间隔离（采用 backend/mail_* 与 backend/sync_* 命名方式）。
- 已优化 `raw_comm_service.py` 内部 `upsert_mail_cleaned` 的 SQL 参数绑定（改用 CAST AS jsonb 解决 Named parameter 歧义）。
- 成功修复 `mail_import_batch` 表缺失 `completed_at` 列引起的数据库写入失败报错。
- 研发了具有高稳定性和高性能的 [sync_crm_emails.py](file:///D:/items/QW/backend/sync_crm_emails.py) 邮件同步和清洗引擎。
- 创新设计并落地的**“内存高速查重 + 批量事务提交 (每 200 封)”性能双重调优方案**，将超大批次数据导入速度直接拉升 **50倍 - 100倍**，并降数据库查重负载至近乎为 0。
- 已过滤 WeCom 聊天记录占位干扰，彻底洗净前端展示列表中的 test 类空邮件噪音。
- 已创建标准交接文件 `AGENTS.md`、`TASKS.md`、`PROGRESS.md`、`TASK_HANDOFF.md`、`VALIDATION.md` 并完成多轮修缮。

## 当前未完成

- Task 42 已完成；下一步进入 Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。
- 邮件 API 已完成 Task 26 草稿脚手架、Task 27 请求参数契约、Task 28 响应参数契约、Task 29 二阶段生成、Task 30 商业条款后端占位符装配、Task 31 草稿/审核默认态收口、Task 32-35 中断 API review-only 预览能力。
- 已完成邮件安全门中的财务价格底线门、价格正则扩展、履约工期 SLA 校准门、收件域名防泄密门，以及竞对域名黑名单/客户域名白名单双校验；尚未实现敏感词扫描与统一红黄牌结果结构。
- 尚未实现邮件诊断面板。

## 当前卡点

- 当前无 Task 11 阻断；导出依赖在本次 `uv run --with-requirements` 执行时已可用。
- Task 13 已把已导出的字段沉淀为正式黄金切片结构，避免导出字段与知识库入库字段长期分叉。
- Task 14 已把 `snippet_type` 正式收敛为 5 个固定枚举，并明确混合内容时按主用途拆片或单类型判定，避免把价格、流程、问候混入同一 Few-Shot。
- Task 16 已把 `industry`、`country`、`customer_tier`、`product_line`、`payment_risk` 正式收敛为可检索的结构化过滤字段，并明确来源优先级、归一化、缺失兜底与检索边界，避免把场景、类型或安全门职责混入过滤口径。
- 运行方式已切换为 gateway + cron 循环：每个 cron tick 独立做一个任务并用中文写 `logs/codex-run.log`，失败由 cron 周期自动重试，不再依赖前台会话保姆式心跳。

需要下一步确认或执行：

- 继续 Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。
- Task 37 已为 Sequence 中断 API 补齐 review-only 操作日志预览与 `logger.info` 输出；后续 Task 38 可在此基础上实现财务价格底线门。
- Task 25 已沉淀 `MailPendingDraftDispositionAction`、`MailPendingDraftDispositionRule`、`MAIL_PENDING_DRAFT_DISPOSITION_RULES`、`MAIL_UNSENT_DRAFT_STATUSES`、`MAIL_SENT_OR_TERMINAL_DRAFT_STATUSES`、`normalize_mail_pending_draft_disposition_action`、`get_mail_pending_draft_disposition_rule`、`resolve_mail_pending_draft_disposition`、`list_mail_pending_draft_disposition_rules`，后续草稿 API、Sequence 中断 API、调度器与执行层可直接复用客户回复销毁、CRM 销毁/锁定、勿扰严格销毁、人工封印锁定口径。
- Task 24 已沉淀 `MailSequenceCutoffEventType`、`MailSequenceInterruptionReason`、`MailSequenceCutoffRule`、`MAIL_SEQUENCE_CUTOFF_RULES`、`MAIL_SEQUENCE_CUTOFF_EVENT_TERMINAL_STATUS` 及按事件/原因/场景步骤检索的切断辅助函数，后续 Task 26-37 可直接复用。
- Task 23 已沉淀 `MailSequenceTriggerAnchor`、`MailSequenceStepInterval`、`DEFAULT_MAIL_SEQUENCE_STEP_DELAYS_DAYS`、`DEFAULT_MAIL_SEQUENCE_STEP_CUMULATIVE_MIN_DAYS`、`MAIL_SEQUENCE_STEP_INTERVALS` 及按场景/步骤读取的辅助函数，后续草稿 API、调度器与配置台可继续复用默认 Step 间隔元数据。

## 下一步

继续 Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。

```bash
python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py
python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py
git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log
```

Task 11 已产出：

- `docs/mail_gold_candidates/latest_mail_gold_candidates.json`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.csv`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.md`

## 最近验证

本轮已执行：

```bash
python3 -m py_compile backend/main.py
git diff --check -- backend/main.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log
```

结果：`python3 -m unittest backend/mail_recipient_domain_guardrail_checks.py` 通过；`python3 -m py_compile backend/main.py backend/mail_recipient_domain_guardrail_checks.py` 通过；`git diff --check -- backend/main.py backend/mail_recipient_domain_guardrail_checks.py TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log` 通过；Task 42 已完成，下一步进入 Task 43。

## 运行监控要求（gateway + cron 循环）

- 任务由 Hermes gateway（每 60 秒 tick）+ cron 循环驱动；每个 cron tick 是独立隔离会话，只做第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加记录：当前时间、当前任务（任务号）、本轮做了什么、成功或失败（失败写原因）、下一步动作。
- 失败（网络/模型临时断开等）如实写入 `logs/codex-run.log` 和 `logs/codex-retry.log`，由 cron 周期自动重试，不丢任务，严禁"假绿"。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron `last_status` 为准。
- 查看：`hermes cron list` / `hermes cron status` / `~/.hermes/cron/output/<job_id>/`。
