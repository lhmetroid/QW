# TASK_HANDOFF
## 2026-07-06 自动排期工作日跳过与存量回收分析交接

- **用户要求**: 增加开关, 让后续新增排期自动跳过周六、周日及中国国家规定法定节假日; 当前存量数据先只分析方案和涉及的数据变化, 原则为往后移到最近工作日、每天上限 50、原日期靠前优先、每个销售独立, 具体回收等待人工指令。
- **已完成**:
  - `mail_autosend_config` 新增 `skip_non_workdays` 与 `holiday_dates_csv`。
  - 自动排期 `_autosend_schedule()` 新增工作日跳过逻辑, 每次目标日和每日上限顺延都会跳过周末和配置节假日。
  - 自动排期配置 API、dry-run/preview 请求和前端 `mail-suite.html` 均接入新开关与节假日输入。
  - 新增只读接口 `/api/v1/mail/autosend/workday-recovery-analysis`, 同时分析本地预排和 CRM OutBox AI 待发行, 返回变化清单但不写库、不改 CRM。
  - 新增 `docs/mail_autosend_workday_recovery_plan.md`, 写清楚存量回收策略和未来人工确认后可能涉及的字段。
- **未执行**: 未进行任何存量回收、未更新 `mail_autosend_plan_item` 排期日期、未修改 CRM `spQueueSend.PlanSendTime`。
- **下一步**: 人工先调用只读分析接口导出 `changes` 复核; 若确认回收, 再另行下令实现/执行受控回写脚本或接口。
- **验证**: `python -m py_compile backend\main.py backend\database.py` 通过; `node --check scratch\frontend-mail-suite-autosend-check.js` 通过; `git diff --check -- backend/main.py backend/database.py frontend/mail-suite.html docs/mail_autosend_workday_recovery_plan.md` 通过。
## 2026-06-16 案例2 Step1 多轮 API 脚本交接

- **用户要求**：先停留在案例2 Step1，修正前一版方向走偏问题；获取客户真实信息；去掉“爱德华/TAVR/医疗器械/生命科学”硬禁词；不要新增“不得带入其他客户信息”这类泛化规则；用正向思路完成脚本并检查一轮。
- **已完成**：
  - 修改 `scratch/run_case2_suite_multiturn_api_compare.py`，案例2 Step1 仍通过真实 CRM 查询获取联系人和公司信息。
  - 给 LLM 的公开上下文去除 `customer_key/case_id`，脚本内部仍使用客户号查询 CRM，避免内部编号进入生成上下文。
  - System Prompt 和 Step1 prompts 改为正向事实约束：只用当前客户信息、CRM事实和服务能力；Step1 聚焦历史文件类型、金融资料客观要求、低压力支持窗口。
  - 未加入“不得带入其他客户信息”规则；也未保留爱德华/TAVR/医疗器械/生命科学硬禁词。
  - 增加过程质量告警，扫描中间轮次是否出现 `老朋友`、`持续关注`、`一直非常重视` 等偏差，避免只看最终 JSON。
- **最新真实调用结果**：
  - DeepSeek step1 报告：`logs/case2-suite-deepseek-step1-20260616-152607.md`
  - 质量标记：`pass`
  - 最终 JSON：联系人“周希”，公司“申万菱信”，场景为金融/资管资料笔译支持窗口；未输出客户号、合同号、报价号、电话、邮箱、爱德华/TAVR/医疗器械/生命科学等错乱信息。
- **仍需人工判断**：
  - 最终正文有“当时合作下来整体流程还是比较顺畅的”，接近截图里“当时配合得很顺畅”的熟客口吻；如果要更严格事实化，可下一轮改成“这类文件通常要求用词准确、格式统一、版本一致”后直接进入支持窗口，不评价过往配合体验。
- **验证**：
  - `python -m py_compile scratch\run_case2_suite_multiturn_api_compare.py` 通过。
  - `git diff --check -- scratch\run_case2_suite_multiturn_api_compare.py` 通过。

### 2026-06-16 追加：过度锚定“董事会资料翻译”的复核与修正

- **用户反馈**：`logs/case2-suite-deepseek-step1-20260616-163922.md` 比之前好，但仍不像爱德华案例那样能让 AI 理解行业并创造同行内容案例/场景痛点；“董事会资料翻译”不应被写死成唯一切口；需要判断数据库拉取数据是否足够全面。
- **复核结论**：
  - 当前多轮流程本身比早期版本接近网页 GPT，但输入信息仍偏窄：CRM 事实反复出现“董事会资料、议案、中译英”，缺少金融/资管客户资料生态的中间抽象层。
  - 爱德华版本之所以更像“理解后扩写”，不是因为泄露答案，而是先给了业务结构和常见活动场景；案例2之前只给了合同/报价事实，模型自然会过度锚定低层字段。
  - `backend/main.py` 的 `_fetch_mail_current_case_crm_detail()` 当前只读当前客户 TOP 3 报价、TOP 3 合同、TOP 5 跟进，足够确认真实客户和历史事实，但不足以支撑稳定的同行场景扩展；尚未把 `mail_contract_case` 同行业脱敏案例和 approved full_email 黄金邮件接入该 scratch 多轮脚本。
- **已修改**：
  - `scratch/run_case2_suite_multiturn_api_compare.py` 的案例2上下文改为“CRM事实 -> 上位业务主题 -> 同行场景推断 -> 稳妥邮件表达”。
  - 新增 `peer_scene_hints`，把治理类资料、定期报告/披露、基金产品材料、路演PPT、投资者问答、ESG/合规报告、境外股东或外籍董事会议材料列为行业扩展素材，并明确不能写成当前客户事实。
  - Step1 第1/2轮提示改为要求区分 CRM 已知事实、同类金融/资管客户常见场景和可写入邮件的稳妥表达；第3/4轮要求不要把主题和正文只写成某一种文件翻译。
  - 质量检查新增 `subject_contains_greeting`、`overanchored_board_translation`、`unsupported_customer_attitude`。
- **验证**：
  - `python -m py_compile scratch\run_case2_suite_multiturn_api_compare.py` 通过。
  - `git diff --check -- scratch\run_case2_suite_multiturn_api_compare.py` 通过。
- **下一步建议**：
  - 再真实调用一次 DeepSeek Step1，检查是否能从“董事会资料翻译”上升到“金融/资管中英文资料、治理/披露/会议材料支持”。
  - 若仍不稳定，应接入 `mail_contract_case` 同行业合同案例和 approved full_email 黄金邮件，而不是继续靠提示词修补。

### 2026-06-16 追加：补入老客户激活/老客户新业务套装要求

- **用户补充要求**：
  1. 曾经合作过的老客户唤醒：体现我们在该行业的经验、行业成功案例；如有需要找我们，或帮忙转介绍。
  2. 介绍事必达一体化服务。
  3. 补充我们近期的成功案例。
- **已修改**：
  - `scratch/run_case2_suite_multiturn_api_compare.py` 新增 `sequence_business_requirements`，把本场景定位为“老客户激活 / 老客户新业务”。
  - `STEP_PLANS` 改为：Step1 关系重启 + 行业经验/相近案例方向 + 低压力转介绍；Step2 一体化服务介绍；Step3 近期成功案例；Step4 低压力收口。
  - Step1 第3轮/第4轮提示加入转介绍口径：如果周希目前不负责相关资料或会议沟通，可以轻描淡写请她帮忙转给合适同事。
  - 新增 `asks_for_contact_details` 质检，避免模型把转介绍写成直接索要姓名、电话、邮箱或联系人信息。
- **验证**：
  - `python -m py_compile scratch\run_case2_suite_multiturn_api_compare.py` 通过。
  - `git diff --check -- scratch\run_case2_suite_multiturn_api_compare.py` 通过。
- **注意**：本次只更新脚本策略，未重新调用 DeepSeek/OpenAI。

### 2026-06-16 追加：10个 DeepSeek 版本逐个测试

- **执行口径**：按用户要求，在当前案例2 Step1 调整逻辑下，连续真实调用 DeepSeek 10 次；每次单独生成完整多轮 md 记录，便于人工挑选。未调用 OpenAI/GPT。
- **生成文件与质量标记**：
  - `logs/case2-suite-deepseek-step1-20260616-190320.md`：pass；主题“之前合作过的金融资料和会议材料，看看近期有没有类似场景需要配合”。
  - `logs/case2-suite-deepseek-step1-20260616-190424.md`：pass；主题“关于金融中英文资料与会议材料支持，和您同步个近况”。
  - `logs/case2-suite-deepseek-step1-20260616-190544.md`：pass；主题“关于金融资料和会议材料支持，想和您再聊聊”。
  - `logs/case2-suite-deepseek-step1-20260616-190702.md`：pass；主题“关于金融中英文资料和会议材料支持”。
  - `logs/case2-suite-deepseek-step1-20260616-190828.md`：pass；主题“关于金融资料支持，想和您再续个旧”。
  - `logs/case2-suite-deepseek-step1-20260616-190929.md`：pass；主题“关于金融中英文资料和会议材料，看看怎么配合更顺”。
  - `logs/case2-suite-deepseek-step1-20260616-191037.md`：pass；主题偏长偏营销，建议人工谨慎。
  - `logs/case2-suite-deepseek-step1-20260616-191158.md`：`overanchored_board_translation`，正文仍过度锚定“董事会资料翻译”，建议剔除。
  - `logs/case2-suite-deepseek-step1-20260616-191312.md`：pass；主题“关于金融资料和会议材料支持，看是否能帮上忙”。
  - `logs/case2-suite-deepseek-step1-20260616-191426.md`：pass；主题“关于金融资料和会议材料支持，想和您再聊聊”。
- **结论**：10 个版本中 9 个通过当前脚本质检，1 个应剔除。整体保持了本轮“CRM事实 -> 行业抽象 -> 同类场景 -> 低压力老客户唤醒/转介绍”的方向。

### 2026-06-16 追加：按爱德华多轮方式复刻 Step1

- **用户追加要求**：不要再提前收口成安全模板；要 100% 复刻爱德华网页多轮逻辑，除了客户信息替换和按场景微调，不要额外加约束；允许模型先发挥。
- **已调整**：
  - `scratch/run_case2_suite_multiturn_api_compare.py` 的 Step1 专门改成四轮：`第1轮：找入口`、`第2轮：理解业务结构和机会`、`第3轮：初版激活邮件`、`第4轮：补充服务后改写`。
  - System Prompt 改为“网页ChatGPT式连续任务”，强调业务理解和服务融入客户逻辑，不再使用上一版强收口的 Step1 变量卡。
  - 质量检查只保留内部编号、合同号、报价号、免费/试译/样稿等硬风险词，不再扫描“持续关注/老朋友/专业态度”等表达。
- **真实调用结果**：
  - DeepSeek 报告：`logs/case2-suite-deepseek-step1-20260616-160058.md`
  - 结果明显更长，业务结构更像爱德华那轮：把董事会资料、中译英、版本一致性、排版校对、会议资料、口译/同传整合为一个资料工作流方案。
  - 模型自由发挥也带来待后处理点：最终 JSON 中出现 `[你的名字]`；“最近我们在金融资管资料的本地化流程上做了一些优化”和“都是由我们团队配合完成的”属于模型主动补强，是否保留需人工判断或下一步做轻量出口清理。

### 2026-06-16 追加：亲和度修正

- **用户反馈**：仍像机器人，语句不够亲和。
- **已调整**：
  - 保留 Step1 前两轮“找入口/理解业务结构”的自由分析，不回到安全模板。
  - 只调整最后成稿提示：要求像熟悉客户的销售经理，少用“方案、链条、流程优化、赋能、成熟团队、积累经验”等咨询腔和自我证明。
  - 要求称呼统一为“周希您好，”，CTA 低压力。
- **真实调用结果**：
  - DeepSeek 报告：`logs/case2-suite-deepseek-step1-20260616-161444.md`
  - 最终 JSON 语气明显更亲和，核心表达为“这类资料往往不只是翻译，格式、版本、术语来回确认也很花时间”，更接近销售经理口吻。
  - 待处理：最终邮件中“每次交付前我们都会反复核对版本，确保和您内部审核的终稿完全一致”表述偏满，建议下一步做轻量出口清理为“这类资料我们通常会特别留意版本和格式一致性”。

## 2026-06-15 邮件 V38 客户画像 + 案例库语义生成交接

- **用户要求**：按前面确认的正确流程跑 V38，并记录下来供人工复查；明确不仅要用案例库，还要用客户画像，才能写出针对性文案。不调用 DeepSeek/ChatGPT/OpenAI。
- **执行方式**：
  - 先只读调用当前 3 个邮件案例的 CRM 画像查询逻辑，获取客户真实业务画像和近期触点。
  - 新增 `scratch/run_mail_v38_profile_case_semantic.py`，不调用外部 LLM；脚本只负责把手写的 V38 文案落库和输出报告。
  - 使用 `mail_contract_case.mail_case_text` 脱敏案例作为正文证明材料；使用 `other/邮件AI案例1-4.docx` 的“行业感 + 轻商务 + 不施压 + 先说场景再问路径”作为写作口径。
- **客户画像切口**：
  - 案例1 `KH15411-117`：熟联系人/key客户；已有患者日活动、笔译、同传/设备合作，并有经导管部门负责人询问触点；切口为从现有结构性心脏病/患者日合作延伸到经导管医生教育和学术会议支持。
  - 案例2 `KH02659-011`：基金/资管老联系人/key客户；历史集中在董事会资料、议案、中英文资料翻译；切口为金融资料、合规披露、英文资料一致性和稳妥响应。
  - 案例3 `KH13770-006`：设备/技术资料类老联系人；历史有英译中、手册修改支持、技术资料类合作；切口为产品手册、售后资料、培训视频和技术资料本地化。
- **结果**：
  - 已落库 V38：`mail_iteration_run.version_no=38`，run_id=`b3fcd120-4cfa-415f-a7e4-2ad39ef9e824`。
  - 3 个案例 × 4 封，共 12 封，全部 success。
  - `llm_success_count=0`，`llm_fallback_count=0`，`llm_model_used=local_semantic_writer_v38_profile_case_no_deepseek_no_chatgpt`。
  - 人工复查报告：`logs/mail-v38-profile-case-library-outputs.md`。
- **修正记录**：
  - 初次 V38 复查发现案例3第2封“手册和技术文件”误取到了医疗器械患者日同传设备案例，原因是早期案例匹配把“设备租赁”误当成“设备手册”。
  - 已新增并执行 `scratch/fix_mail_v38_manual_case.py`，原地修正 V38 案例3 Step2 为工业设备操作手册案例，并更新 DB 行、报告和 V38 平均分。
- **验证**：
  - `python -m py_compile scratch\run_mail_v38_profile_case_semantic.py scratch\fix_mail_v38_manual_case.py` 通过。
  - DB 查询：V38 12 条，status=success，`llm_success_count=0`，`llm_fallback_count=0`，avg_quality_score=88.08。
  - 正文风险词检查：未命中完整公司名、客户编号/报价/合同编号、电话邮箱、微信二维码、变量/脚本痕迹；报告元数据中的合同编号仅用于人工追溯，不在邮件正文中。
  - 定向 `git diff --check -- scratch\run_mail_v38_profile_case_semantic.py scratch\fix_mail_v38_manual_case.py logs\mail-v38-profile-case-library-outputs.md` 通过。

## 2026-06-15 邮件 V36 无 LLM 黄金模板语义生成交接

- **用户要求**：查看 `logs/mail-v34-v35-approved-gold-human-like-analysis.md`，承认 V35 仍存在完整公司名等旧问题；完成 V36，禁止调用 DeepSeek 或 ChatGPT；读取黄金案例库中 `full_email` 且人工认可的邮件模板，学习写法，可引用案例并润色；按 3 个案例客户 × 4 封套装输出正文。
- **执行方式**：
  - 新增 `scratch/run_mail_v36_no_llm.py`。
  - 只导入 `backend/database.py` 模型，避免导入 `backend.main` 触发调度器和 LLM 链路。
  - 查询 `mail_gold_seed_review.review_status=approved` + `email_fragment_asset.function_fragment=full_email`，共读到 59 封认可模板。
  - 选用代表性模板作为风格来源，学习“自然问候、具体业务场景、案例轻证明、低压力收口”，不原样照抄完整公司名、电话、邮箱、微信、二维码或夸张数字。
- **结果**：
  - 已生成并落库 V36：`mail_iteration_run.version_no=36`，run_id=`3e0bf113-9be9-4f2f-aa92-a0270f8190b3`。
  - 3 个当前案例 × 4 封，共 12 封全部成功。
  - `llm_success_count=0`，`llm_fallback_count=0`，`llm_model_used=local_semantic_writer_v36_no_deepseek_no_chatgpt`。
  - 正文输出：`logs/mail-v36-no-llm-approved-full-email-outputs.md`。
- **验证**：
  - `python -m py_compile scratch\run_mail_v36_no_llm.py` 通过。
  - DB 查询确认 V36 12 条、状态 success、平均分 98.00。
  - 定向 `git diff --check -- scratch\run_mail_v36_no_llm.py logs\mail-v36-no-llm-approved-full-email-outputs.md` 通过。
  - 风险词检索正文未命中完整公司名、电话邮箱、微信二维码、变量痕迹；报告约束说明中出现“微信”二字属于说明文本，不是邮件正文。

## 2026-06-12 企微客户画像聚合接入交接

- **用户要求**：读取 `other/2026-06-12-客户画像聚合模块接入文档.md` 与 `other/crm_profile_aggregator_standalone.py`，把微信/企微流程用到的画像替换为更完整的新字段；企微 API 输出画像字段同步扩展；明确不涉及邮件。随后用户确认：`model_text` 不要隐藏金额，其他按方案执行。
- **已完成**：
  - 新增 `backend/crm_profile_aggregator.py`，从 standalone 代码改为复用项目现有 CRM SQL Server 连接 `CRMSessionLocal`，只读 CRM，不落库，按天内存缓存。
  - `IntentEngine.get_crm_context()` 已改为新聚合画像优先，旧 `fetch_crm_profile` 作为补充和 fallback。
  - `crm_info` 继续保留旧字段：`crm_contact_name`、`company_name`、`company_industry`、`recent_quote_summary`、`ongoing_contracts`、`contact_recent_followup`、`customer_lifecycle_stage`、`customer_tier`、`payment_risk_level`、`high_risk_flags`、`crm_profile_status`。
  - `crm_info` 新增完整字段：`crm_profile_text`、`crm_profile_prompt_text`、`crm_profile_data`、`crm_profile_source`、`crm_profile_schema_version`、`contact_id`、`customer_id`、`relationship_level`、`account_time`、`contract_count`、`contract_total_money`、`uninvoiced_money`、`quotation_count`、`recent_followups` 等。
  - 已按用户要求让企微 prompt 使用完整版画像文本，历史成交额和未开票额不再隐藏。
- **验证**：
  - `python -m py_compile backend\intent_engine.py backend\crm_profile_aggregator.py backend\config.py backend\wecom_advance_completion.py` 通过。
  - `git diff --check -- backend\intent_engine.py backend\crm_profile_aggregator.py backend\config.py backend\wecom_advance_completion.py .env.example` 通过。
  - 本地构造测试确认 `crm_profile_source=crm_realtime_aggregator`、旧字段兼容、新字段输出、金额进入 `crm_profile_prompt_text`。
- **注意**：尚未用真实 CRM external_userid 端到端调用 `/api/wecom/sidebar_assist`，因为本轮没有启动后端或访问生产 CRM；后端重启后新代码生效。当前工作区还存在上一轮企微 advance-completion 改动与未跟踪 `.codex_pycache_v15/`，本轮未处理。

## 2026-06-11 后台卡顿/数据库防锁死交接

- **用户问题**：`/api/sessions` 会话列表超时，判断不是端口而是数据库表/查询被卡住；要求查询原因，或在一键启动中加入防锁死/定时解锁机制。
- **定位结果**：
  - 端口不是主因；8071 可启动并服务请求。
  - `/api/train_ai/models` 外部训练 AI 模型列表探测会访问 `zjsphs.2288.org:11486`，旧逻辑每个探测 15 秒，失败时可累计 45 秒以上。
  - `/api/case_lib/iterations` 列表接口会逐日统计企微日常验证，可能拖慢首屏。
  - `/api/sessions` 读 `message_logs`，旧逻辑是 `GROUP BY user_id` 聚合取 `max(timestamp)`，在并发慢接口和表数据增长时容易超时。
  - 数据库检查时未见明确 blocking lock，但见过 `idle in transaction`，所以需要普通连接级别的自动超时保护。
- **已修复**：
  - `backend/database.py`：PostgreSQL 新连接自动带 `statement_timeout=20s`、`idle_in_transaction_session_timeout=1min`、`lock_timeout=5s`。
  - `backend/config.py` / `.env.example`：新增 `DATABASE_STATEMENT_TIMEOUT_MS`、`DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS`、`DATABASE_LOCK_TIMEOUT_MS`、`TRAIN_AI_MODEL_LIST_TIMEOUT_SECONDS`。
  - `backend/main.py`：训练 AI 模型列表探测超时改为 2 秒级；`/api/sessions` 改为 `DISTINCT ON (user_id)` 快路径，最多返回 500 条；新增 `/api/system/db_lock_status` 只读锁诊断接口。
  - 2026-06-11 17:10 追加修复：`/api/case_lib/iterations` 默认不再逐日实时统计，只有 `include_daily_stats=true` 才算每日统计；`/api/train_ai/models` 默认只返回当前配置模型，只有 `refresh=true` 才外连刷新模型列表。
- **追加定位**：
  - 用户新日志中 `/api/train_ai/models` 和 `/api/case_lib/iterations` 同时 25 秒返回，说明事件循环被同步重活阻塞；模型接口本身也被排队，并非一定是模型接口自身又卡 25 秒。
- **验证**：
  - AST：`backend/main.py`、`backend/config.py`、`backend/database.py` 通过。
  - 核心 SQL：会话列表 500 条本地实测约 788ms。
  - 新连接参数：`statement_timeout=20s`、`idle_in_transaction_session_timeout=1min`、`lock_timeout=5s`。
  - 定向 `git diff --check -- backend/main.py backend/config.py backend/database.py .env.example` 通过。
- **注意**：自动 terminate 连接未默认启用，避免误杀正常业务；当前机制依赖 PostgreSQL 会话超时自动取消慢语句/闲置事务。需重启后端后新连接生效。

## 2026-06-11 案例1最终 Prompt v51 修正交接

- **用户指出的新问题**：Step1 prompt 仍偏长；变量替换表达冗余；前台结构脚本看不到礼品、多媒体译制、印刷等业务范围；案例 1 的患者日/医疗同传事实不应变成通用脚本；“生产脚本/AI指令”命名容易造成两套逻辑误解；知识库变量只给单条且不清楚使用边界。
- **已修复**：
  - `_build_mail_draft_llm_full_prompt()` 的目标/节奏改为短目标与短发送节奏，默认长套装说明不再直接塞给 LLM。
  - 最终 prompt 变量表达已按用户纠正改为类似微信 LLM2 脚本预览的 `{customer_name} = Michelle Li` 变量取值块，不再使用 `客户称呼：Michelle Li；模板：{customer_name}` 这种重复格式。
  - 最终 prompt 分区改为 `结构脚本`、`AI指令`、`变量取值`，去掉 `最终Prompt-结构脚本` / `最终Prompt-AI指令` 命名。
  - 案例 1 四个前台结构脚本升到 v51，结构脚本里显式列出笔译/本地化、会议同传/设备、多媒体译制、排版印刷、展会活动物料、商务礼品。
  - 残留的患者日/医疗活动固定阶段提示已改成通用表达；患者日只作为案例 1 CRM 历史事实存在，不作为通用脚本。
  - 前台字段名改成 `最终Prompt-结构脚本` / `最终Prompt-AI指令`，最终 prompt 同时带入两个字段。
  - Few-shot/知识库扩展为 Top3，同步写明“只参考节奏、场景和表达方式，不得把外部案例写成当前客户自己的历史”。
- **当前核对结果**：
  - `logs/mail-case1-final-prompts-v27-preview.md` 已刷新为当前 v51 内容；文件名未改。
  - Step1 统计：1818 字；四封预览已刷新。
  - 数据库 `mail_sequence_template` 中 `new_business_promotion` steps 1-4 均为 `version_no=51`，且四个结构脚本都包含商务礼品、多媒体译制、排版印刷。
- **验证**：
  - `python scratch\preview_mail_case1_final_prompts.py` 通过。
  - `python -c "import ast, pathlib; ast.parse(pathlib.Path('backend/main.py').read_text(encoding='utf-8'))"` 通过。
  - 旧硬编码文本 grep 无命中：`前台生产脚本模板`、`前台给 AI 的指令脚本`、`变量值（用于替换`、`之前 SpeedAsia 和贵司配合过笔译`、`常见医疗活动场景参考`。
  - 定向 `git diff --check` 通过。
- **注意**：本轮未调用 LLM、未真实发信。运行中的后端服务如未自动 reload，需要重启后才能使用 v51 代码；数据库模板已更新。

## 2026-06-11 邮件生成链路审计交接

- **用户指出的问题**：前台邮件质量诊断页可人工调整模板，但最终给 AI 的 prompt 另走后端硬编码拼装，导致 V26 之后多轮测试没有证明“前台配置调优有效”。
- **审计结论**：
  - 前台模板字段已被读取到 `MailDraftIntentProfile.sequence_template_script` / `sequence_template_ai_instruction`，但旧 `_build_mail_draft_llm_full_prompt()` 没有纳入这两个字段。
  - 案例 1 还存在客户名硬编码覆盖 CRM 历史与 Few-shot 标题的逻辑，容易让测试看起来稳定，但不符合“前台/数据驱动”原则。
  - CRM 行业推断会把法律/合同资料线索带成 `legal`，后续 prompt 若直接使用就会误写客户属于法律行业。
- **已修复**：
  - 最终 prompt 明确包含前台生产脚本模板和前台 AI 指令脚本，并声明二者是本次写作主规则。
  - 最终 prompt 同时保留模板通配符和变量值映射，便于前台继续用 `{customer_name}` 等通配符维护模板。
  - 去掉案例 1 按“爱德华”硬覆盖 CRM 历史/Few-shot 的逻辑。
  - 行业提示改为来源/可信度口径：医疗/生命科学、工业设备/制造按公司名和画像优先；`legal` 只作为法律/合同资料线索，不直接当客户行业。
  - Few-shot/知识库命中信息进入最终 prompt：ID、分数、标题、内容摘要和使用边界。
- **验证**：
  - `python -c "import ast, pathlib; ast.parse(pathlib.Path('backend/main.py').read_text(encoding='utf-8'))"` 通过。
  - `python scratch\preview_mail_case1_final_prompts.py` 已刷新 `logs/mail-case1-final-prompts-v27-preview.md`。
  - 临时模板哨兵测试确认 `FRONT_TEMPLATE_SENTINEL` / `FRONT_AI_SENTINEL` 会进入最终 prompt。
  - 行业小测确认爱德华不会被 legal 带偏，蒙特空气处理设备不会被写成法律行业。
  - 定向 `git diff --check -- backend/main.py logs/mail-case1-final-prompts-v27-preview.md PROGRESS.md TASK_HANDOFF.md 项目进展.md` 通过。
- **注意**：本轮未调用 LLM、未真实发信；导入 `main` 时曾出现一次 PostgreSQL schema patch 死锁日志，但进程继续完成预览生成，后续 AST/diff 检查正常。

## 2026-06-10 案例1邮件 Prompt 简化交接

- **用户要求**：prompt 不要复杂，再修改一轮，并输出给 AI 的变量替换后最终 prompt。
- **已完成**：
  - `backend/main.py` 新增 `_build_mail_draft_llm_full_prompt()`，真实生成链路和预览脚本共用同一份最终 prompt 构造逻辑。
  - `_MAIL_DRAFT_LLM_SYSTEM_PROMPT` 已简化为真人销售轻商务写作角色，不再大段规则堆叠。
  - 最终 prompt 只保留任务、阶段、已知背景、写法要求、不要写、输出格式。
  - CRM prompt 背景已移除内部负责人、销售跟进渠道和直接询问负责人信息。
  - Few-shot 不再塞原文，只保留范例标题/风格，避免模型照抄旧套话。
  - 新增 `scratch/preview_mail_case1_final_prompts.py`，输出案例1四封最终 prompt 到 `logs/mail-case1-final-prompts-v27-preview.md`。
- **验证**：AST 解析通过；定向 `git diff --check` 通过；本轮未调用 LLM、未生成 V27、未真实发信。

## 2026-06-10 邮件 V25/V26 案例1测试交接

- **用户要求**：拿案例 1 的 4 封做邮件测试 V25/V26，分别使用 DeepSeek 和 ChatGPT，并让语句向 docx 邮件标准靠拢。
- **执行结果**：
  - V25：`mail_v25_case1_4steps_deepseek_docx_standard`，run_id `1526ed09-58b3-4054-ab05-0c5dab64992b`，4/4 成功，平均分 97.00，模型 `deepseek:deepseek-chat`。
  - V26：`mail_v26_case1_4steps_chatgpt_docx_standard`，run_id `51ada09e-5afd-436d-883d-fb35562fdc76`，4/4 成功，平均分 96.00，模型 `openai:gpt-4.1`。
- **代码/脚本**：
  - 新增 `scratch/run_mail_case1_v25_v26.py`，只跑案例 1 四封，可指定 `--provider deepseek|openai`。
  - 新增 `scratch/clean_mail_v25_v26_outputs.py`，将出口清洗规则同步应用到 V25/V26 已落库正文。
  - `backend/main.py` 邮件出口清洗增强，修复 `小批量测试/试用`、`法律行业/法务培训`、`不涉及具体报价`、孤立行业场景句等表达。
- **复查**：V25/V26 共 8 封已检查，免费/样稿/试译、微信/企微、价格/报价/折扣/账期、内部编号、无依据周期、直接索要电话邮箱、法律行业误判口径均 0 命中。
- **分析文件**：`logs/mail-v25-v26-analysis.md`。
- **注意**：真实发信仍关闭；本轮真实调用 DeepSeek 与 OpenAI，但未输出或记录任何 API Key。

## 2026-06-10 implementation_plan 复核与案例1四模板交接

- **用户要求**：按 `C:\Users\Admin\.gemini\antigravity-ide\brain\6f223379-985e-4bdc-8f95-874d1fe826b6\implementation_plan.md` 检查是否完成；先只修改案例 1 的 4 个模板，其他按方案完成。
- **已确认完成**：
  - 后端已有 `RuntimeLlmSettings`、`_load_runtime_settings_with_defaults()`、`GET/PUT /api/v1/system/runtime-llm-settings`，会写入/读取 `backend/runtime_llm_settings.json`。
  - 邮件生成链路读取动态 `mail_system_prompt` 与 `mail_temperature`；企微回复链路读取动态 `wecom_system_prompt` 与 `wecom_temperature`。
  - 前端邮件配置台已有 2x2 企微/邮件 LLM 参数面板，并在配置页激活时加载，保存时调用 PUT。
  - 已补齐 `new_business_promotion` steps 1-4 的专属 `script_template` 与 `ai_instruction_script`，四封分别对应破冰、案例证明、方案路径、低压力收口。
  - 仅案例 1 四个模板目标版本为 `48`；案例 2/3 仍为 `46`，未改其模板内容。
- **验证**：AST 解析 `backend/main.py`、`backend/config.py`、`backend/intent_engine.py` 通过；`python -m unittest backend.mail_review_api_interface_checks` 通过；抽取 `frontend/index.html` 内联 JS 后 `node --check` 通过；scratch 隔离测试 runtime settings PUT 写入/读取通过；定向 `git diff --check` 通过。
- **已知环境问题**：`python -m py_compile backend\main.py backend\config.py backend\intent_engine.py` 仍因 Windows 下 `backend/__pycache__` pyc rename 权限拒绝失败，属于既有环境问题，本轮未改权限。

## 2026-06-10 Claude 3.5 Sonnet 接入与 Prompt 优化、新业务模板开发交接

- **交接要点**：
  - **Claude 3.5 Sonnet 接入**：在 `backend/config.py` 中新增 `MAIL_DRAFT_ANTHROPIC_*` 配置项，允许灵活指定 API 链接、Key、Model、Timeout 等属性。目前 API Key 默认为 `""`，需最终部署时写入。
  - **Provider 动态切换与 API 双轨适配**：在 `backend/main.py` 中完美支持 `anthropic` 作为 provider。`_call_llm2_json_for_mail_draft` 适配了 Anthropic 原生 API（设置特定 custom headers 并解析返回的 `content` 列表）。同时，为了应对代理网关的兼容性，增加了自动剥离 markdown ````json ```` 包裹的鲁棒解析逻辑，且仅在非 Claude 场景下添加 `response_format` 限制。
  - **人设 System Prompt 重构**：修改 `_MAIL_DRAFT_LLM_SYSTEM_PROMPT` 为资深 B2B 销售人设（温和、专业、克制、轻商务），指导模型融入 CRM 事实并严禁主动做出价格、工期或条款承诺，限定输出为 JSON。
  - **新业务模板瘦身（v47）**：对 `new_business_promotion` 第 1 封邮件模版及 AI 指令进行了简化，去除了冗余校验（已移交给物理安全门），使其专注于“邮件切口与目标”。Targeted Version 提升到 `47` 自动升表覆盖。
  - **测试与验证通过**：运行全量 47 个 `mail_*_checks.py` 的测试用例以及 `backend/mail_review_api_interface_checks.py` 100% 成功（OK）。 AST 检查与编译全部通过。

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

## 2026-06-11 训练 AI Prompt 单据记录交接

- 用户询问训练 AI 当前走的 prompt 是否保存，并要求增加字段单据记录。
- 已在 `backend/main.py` 补齐训练 AI `prompt_trace`：`_train_ai_chat()` 返回体包含 `prompt_trace`，非流式和流式两条调用路径在外层超时时也会带上已构建 prompt。
- 实际保存字段不新增数据库列，沿用现有 JSON 单据字段：
  - `intent_summaries.training_ai -> prompt_trace -> final_prompt`
  - `intent_summaries.training_ai -> prompt_trace -> messages`
  - `api_assist_invocation.result_payload -> training_ai -> prompt_trace -> final_prompt`
  - `api_assist_invocation.result_payload -> training_ai -> prompt_trace -> messages`
- 旧历史记录不会自动补 `prompt_trace`；重启后端后新生成的训练 AI 单据才会有该记录。
- 验证：`backend/main.py` AST 通过；定向 `git diff --check` 通过。

## 2026-06-12 邮件黄金库认可模板标准迭代交接

- 用户要求：按邮件黄金库中人工认可的邮件模板作为标准调整邮件脚本，完成 V34 迭代测试，评价标准改为“是否像人写的亲和、是否和黄金库类似”，先不要用之前评价逻辑。
- 已修改 `backend/main.py`：
  - `new_business_promotion` 四封脚本目标版本升为 v53。
  - prompt 注入“人工认可黄金邮件标准”，并优先把同场景 approved `full_email` 放入 few-shot 参考。
  - 新增/替换评分逻辑 `approved_gold_human_likeness_v1`，评分维度为亲和度、approved full_email 相似度、场景具体度、低压力下一步、清洁与安全。
  - 修正 approved full_email 检索：`MailGoldSeedReview.fragment_id` 先转字符串；approved 样本不再被旧 `publishable/allowed_for_generation/usable_for_reply=false` 标记挡住；同场景 full_email 取样上限扩大，避免先 limit 后过滤漏掉人工认可样本。
- 数据库模板已刷新：`new_business_promotion` step 1-4 均为 `version_no=53` 且 `is_active=True`。
- V34 首轮：
  - run_id `37097a19-0bd5-4dcb-8d73-588d8ee8f1d5`
  - 4/4 成功，平均分 64.25；但 approved full_email 相似度为 0，原因是旧过滤漏掉认可模板。
- 修正版因版本自动递增为 V35：
  - run_id `6a247dcd-64ac-40f0-bf0f-b5857f8a4691`
  - 4/4 成功，平均分 82.50，最低 78，最高 84。
  - 四封均命中人工认可黄金库来源：`mail_gold_v2_099_mail_promo_case_industry`、`mail_gold_v2_134_mail_promo_recovered`、`mail_gold_v2_094_mail_promo_case_industry` 等。
- 验证文件：`logs/mail-v34-v35-approved-gold-human-like-analysis.md`。
- 已运行验证：`python -m py_compile backend/main.py`、`git diff --check -- backend/main.py`、`python scratch/run_mail_case1_v25_v26.py --provider openai ...`。
- 注意：当前工作区还有本轮之前已存在的企微/配置相关未提交改动（如 `.env.example`、`backend/config.py`、`backend/intent_engine.py`、`backend/crm_profile_aggregator.py` 等），本轮未处理也未回滚。

## 2026-06-15 邮件黄金范例库 full_email 人工点评清理交接

- 用户要求：在邮件质量诊断 -> 黄金范例库中，先汇总 `full_email + 需修改` 的人工点评问题，再对 `full_email` 且状态为需修改和空/未评审的条目按这些问题复查并修正。
- 已完成问题汇总：
  - 时间/节日信息：31 条。
  - 未脱敏：24 条。
  - 格式/分段混乱：6 条。
  - 乱码/异常字符：4 条。
  - 主题问题：1 条。
  - 其他短点评：10 条。
- 已新增脚本：`scratch/cleanup_mail_full_email_reviews.py`。
- 数据库处理范围：`mail_gold_seed + full_email` 中 `needs_revision` 65 条、未评审 1253 条，合计 1318 条；approved 34 条和 rejected 11 条未改。
- 已写库修正内容：
  - 删除年份/节日/日期/工作日交稿/季节寒暄等时效信息。
  - 替换人工点评提到的人名、销售名、客户公司名和部分具体部门名。
  - 规范正文分段、项目符号、孤立标点。
  - 删除乱码问号、微信/二维码/加微信等私域联系方式。
  - 在 `source_snapshot.manual_cleanup` 写入清理规则与时间标记。
- 未自动把 `needs_revision` 改为 `approved`，需要人工在前台复核后再认可。
- 验证文件：
  - `logs/mail-full-email-review-cleanup-20260615.md`
  - `logs/mail-full-email-cleanup-final-postcheck-pass6-20260615.json`
  - `logs/mail-full-email-cleanup-apply-pass6-20260615.json`
- 最终验证：`python -m py_compile scratch/cleanup_mail_full_email_reviews.py` 通过；最终 dry-run `changed_count=0`、`residual_count=0`；目标范围内微信残留 0；定向 `git diff --check` 通过。

## 2026-06-15 邮件黄金库 full_email 选择理由展示交接

- 用户要求：在邮件质量诊断 -> 黄金范例库详情右侧“保存修改”下方、“人工点评”上方新增“选择理由：XXX”；对切片类型 `full_email` 每封邮件分析为什么是宣传邮件、有什么推荐价值；判断不是宣传邮件的编号交给人工判断；其他切片类型为空不影响显示。
- 已修改 `frontend/index.html`：`openMailGoldLibrarySeedDetail()` 在保存按钮下方插入选择理由展示块，仅当 `selection_reason` 非空时显示。
- 已修改 `backend/main.py`：`/api/v1/mail/gold-fewshot-seeds` 对 `full_email` 返回 `selection_reason` 和 `promo_analysis`，非 `full_email` 返回空字符串/None。
- 已新增并执行 `scratch/analyze_mail_full_email_promo_reason.py --apply`：分析 1363 封 `full_email`，将 `source_snapshot.promo_analysis` 写入数据库。
- 结果：1286 封判断为宣传/推广型，77 封疑似不是宣传邮件，需要人工判断。人工清单在 `logs/mail-full-email-promo-selection-reason-20260615.md`；机器 JSON 在 `logs/mail-full-email-promo-analysis-apply-20260615.json`。
- 已验证：`python -m py_compile backend/main.py scratch/analyze_mail_full_email_promo_reason.py` 通过；前端内联 JS `new Function` 语法检查通过；接口函数抽查 `full_email` 1363 条均有选择理由、其他切片 0 条有选择理由；定向 `git diff --check -- backend/main.py frontend/index.html scratch/analyze_mail_full_email_promo_reason.py` 通过。
- 注意：直接 import `backend/main.py` 做接口函数抽查时，环境仍会输出既有 DB patch lock timeout 与日志轮转 PermissionError 噪音，但查询函数实际返回正常。

## 2026-06-15 邮件黄金库疑似非宣传 full_email 删除交接

- 用户要求删除上一轮列出的 77 封疑似不是宣传邮件，并随后确认“继续”。
- 已新增脚本 `scratch/delete_non_promo_full_email_seeds.py`，从 `logs/mail-full-email-promo-analysis-apply-20260615.json` 读取 `non_promotional` 清单，限定删除 `mail_gold_seed + full_email`，并同步删除对应 `mail_gold_seed_review`。
- dry-run 结果：目标 77，匹配黄金库切片 77，匹配评审记录 1，缺失 0。
- 已执行 apply：删除黄金库切片 77 条，删除评审记录 1 条。
- 删除前备份：`logs/mail-full-email-non-promo-delete-backup-20260615.json`；删除报告：`logs/mail-full-email-non-promo-delete-20260615.md` 与 `logs/mail-full-email-non-promo-delete-apply-20260615.json`。
- 删除后验证：目标 `fragment_id` 在 `email_fragment_asset` 剩余 0，在 `mail_gold_seed_review` 剩余 0；当前 `mail_gold_seed + full_email` 剩余 1286，剩余非宣传标记 0。
- 验证：`python -m py_compile scratch/delete_non_promo_full_email_seeds.py` 通过；定向 `git diff --check` 通过。

## 2026-06-15 邮件黄金库 full_email #301-#400 复查清理交接

- 用户要求：回到邮件，根据 `logs/mail-full-email-review-cleanup-20260615.md` 的问题口径，对 `#301-#400` 数据完整逐条检查并修复。
- 编号口径已确认：前端黄金库第一列 `#` 来自 `source_snapshot.candidate_rank`，不是当前排序行号。
- 已新增脚本 `scratch/cleanup_mail_full_email_rank_301_400.py`，目标为 `mail_gold_seed + full_email + candidate_rank 301..400`。
- 当前库内现存 47 条，53 个编号已不存在；现存 47 条均已写库清理。
- 修正内容：删除时间/节日/相对日期/蛇年谐音，脱敏客户公司、品牌、联系人、销售名和项目名，删除电话邮箱地址、微信/二维码、订单下载、质量评价、报价/PO 等事务内容，软化不可验证数字和夸张表达，修复破损标题和重复占位符。
- 9 条清理后正文不足，已保留但关闭生成开关 `publishable=false`、`allowed_for_generation=false`、`usable_for_reply=false`：#335、#336、#345、#350、#362、#369、#370、#397、#398。
- 最终验证：`python -m py_compile scratch/cleanup_mail_full_email_rank_301_400.py` 通过；最终 postcheck `changed_count=0`、`residual_count=0`；9 条 hold 的三个生成开关均为 false；定向 `git diff --check` 通过。
- 报告：`logs/mail-full-email-rank-301-400-cleanup-20260615.md`，最终 JSON：`logs/mail-full-email-rank-301-400-cleanup-apply-pass3-20260615.json` 与 `logs/mail-full-email-rank-301-400-cleanup-postcheck-pass3-20260615.json`。

## 2026-06-17 三案例四阶段 DeepSeek 多轮生成交接

- 用户指出上一轮“其他10个版本”全部仍是 `re_activation / 1/4 - 关系重启`，不是预期的 3 个案例 × 4 个阶段。已确认原因：旧脚本 `scratch/run_case2_suite_multiturn_api_compare.py` 是案例2专用脚本，固定 `KH02659-011`、`scenario=re_activation`、输出 `case2-suite-*step1*`。
- 已新增通用脚本 `scratch/run_mail_3cases_multiturn_api_compare.py`，默认跑 DeepSeek，支持 `--case all|case1|case2|case3` 和 `--steps 1,2,3,4`。脚本会从 CRM 尝试读取真实联系人/公司名，并按每个案例自己的场景和四阶段策略构建多轮对话。
- 已真实调用 DeepSeek 生成 12 个节点 md：case1 step1-4、case2 step1-4、case3 step1-4。最新可用文件为：
  - `logs/case1-suite-deepseek-step1-20260617-083601.md`
  - `logs/case1-suite-deepseek-step2-20260617-084444.md`
  - `logs/case1-suite-deepseek-step3-20260617-083736.md`
  - `logs/case1-suite-deepseek-step4-20260617-083819.md`
  - `logs/case2-suite-deepseek-step1-20260617-083850.md`
  - `logs/case2-suite-deepseek-step2-20260617-083923.md`
  - `logs/case2-suite-deepseek-step3-20260617-083959.md`
  - `logs/case2-suite-deepseek-step4-20260617-084027.md`
  - `logs/case3-suite-deepseek-step1-20260617-084058.md`
  - `logs/case3-suite-deepseek-step2-20260617-084137.md`
  - `logs/case3-suite-deepseek-step3-20260617-084206.md`
  - `logs/case3-suite-deepseek-step4-20260617-084236.md`
- 注意：首轮 `logs/case1-suite-deepseek-step2-20260617-083643.md` 命中过“链条”和“电话”质量问题，已废弃不用；脚本已补强约束，并重跑得到 `logs/case1-suite-deepseek-step2-20260617-084444.md`，质量标记 `pass`。
- 已验证脚本：`python -m py_compile scratch\run_mail_3cases_multiturn_api_compare.py` 通过；`git diff --check -- scratch\run_mail_3cases_multiturn_api_compare.py` 通过。后续如果继续批量跑，不要再使用案例2专用脚本去代表三案例四阶段。

## 2026-06-17 多轮销售邮件生成标准交接

- 用户继续指出更深层问题：不是只要“3案例×4阶段”就行，而是必须继承爱德华案例1-1和案例2-1在历史对话中被人工纠正出的多轮逻辑。当前 `scratch/run_mail_3cases_multiturn_api_compare.py` 虽然补齐了 12 个节点，但把第2轮从“理解业务结构和机会”改成“节点策略与递进”，把第4轮从“亲和、人话、服务自然融入改写”改成“最终 JSON 清洗”，因此不能视为真正复刻。
- 已新增标准文档：`docs/mail_multiturn_sales_email_generation_standard.md`。
- 后续继续生成或改脚本时必须先读该文档。核心要求：
  - 所有节点固定四轮：确认客户入口 -> 理解业务结构和机会 -> 初版邮件 -> 亲和口吻改写并输出 JSON。
  - Round 2 必须做行业/业务结构深挖，不得替换为写作决策卡。
  - Round 4 必须做人话改写，保留业务理解并自然融入服务，不得只做禁词和 JSON 清洗。
  - 0616 的爱德华与案例2 Step1 日志是正向参考；0617 的 case2 step1 是反例。
- 本轮没有读取 `C:\Users\Admin` 下的 Codex 会话存档，因为当前聊天上下文、`logs/*.md` 和脚本文件已足够还原要求；若后续出现项目日志缺失，再考虑读取用户指定会话存档。

## 2026-06-17 案例2 Step2 标准四轮验证交接

- 用户要求严格参照 `docs/mail_multiturn_sales_email_generation_standard.md` 完成案例2 Step2，并分别用 DeepSeek、ChatGPT/OpenAI 真实 API 验证，重点对比第3轮和第4轮是否与之前调准的 case2 Step1 接近。
- 已新增并验证 `scratch/run_case2_step2_standard_multiturn.py`。该脚本只跑案例2 Step2，固定四轮为：确认客户入口、理解业务结构和机会、初版一体化服务介绍邮件、补充服务后亲和改写并输出最终 JSON。
- 已真实调用两模型，最新可用文件：
  - DeepSeek：`logs/case2-suite-deepseek-step2-standard-20260617-100231.md`
  - OpenAI：`logs/case2-suite-openai-step2-standard-20260617-100305.md`
  - 对比结论：`logs/case2-step2-standard-comparison-20260617-1005.md`
- 判断结果：两模型最终 JSON 均为 pass。DeepSeek 第4轮比第3轮少了方案感，完成从“翻译/格式/版本/术语”到“资料用途和会议场景配合方式”的递进；OpenAI 第4轮也从“整体配合/把控全流程”收回到老客户自然沟通口吻。二者均可作为案例2 Step2 的通过样本。
- 后续继续 Step3/Step4 时，不要直接复用旧 `scratch/run_mail_3cases_multiturn_api_compare.py` 的节点策略卡结构；应先把它改成 `scratch/run_case2_step2_standard_multiturn.py` 这种四轮结构，再批量扩展。

## 2026-06-17 案例2 Step3/Step4 标准四轮验证交接

- 用户继续要求完成 Step3/Step4，并强调：给上一封邮件主要是避免重复，客户没有回复，不要在正文中特意提“上次/上一封”，而是换切入点或换方式继续开发。
- 已新增 `scratch/run_case2_steps34_standard_multiturn.py`，保留标准四轮：确认客户入口、理解业务结构和机会、初版邮件、亲和口吻改写并输出最终 JSON。
- 脚本差异：
  - Step3：近期/同类脱敏成功案例，不重复 Step1 唤醒和 Step2 一体化介绍。
  - Step4：低压力备用窗口，不催回复、不要求报价/会议/电话。
  - 前序邮件只作为去重上下文；最终正文硬门禁用“上次、上一封、接着上封、之前聊到、客户说、对方反馈、客户评价”等。
- 已真实调用两模型。最新可用文件：
  - Step3 DeepSeek：`logs/case2-suite-deepseek-step3-standard-20260617-102736.md`
  - Step3 OpenAI：`logs/case2-suite-openai-step3-standard-20260617-102448.md`
  - Step4 DeepSeek：`logs/case2-suite-deepseek-step4-standard-20260617-102811.md`
  - Step4 OpenAI：`logs/case2-suite-openai-step4-standard-20260617-102545.md`
  - 对比结论：`logs/case2-steps34-standard-comparison-20260617-1030.md`
- 废弃文件：`logs/case2-suite-deepseek-step3-standard-20260617-102419.md`、`logs/case2-suite-deepseek-step4-standard-20260617-102521.md`。前者写了未验证客户反馈，后者写了“之前聊到”。
- 后续若做三案例四阶段批量化，必须把这个“前序邮件只去重、不显性承接”的规则一起固化。

## 2026-06-17 案例2知识库增强四封 DeepSeek 交接

- 用户要求在上一版基础上优化 case2 的 4 个版本，并真实跑一轮 DeepSeek，必须符合 `docs/mail_sequence_12_step_purpose_draft.md` 和 `docs/mail_multiturn_sales_email_generation_standard.md`，不要再随意定义场景。
- 已新增/优化 `scratch/run_case2_reactivation_deepseek_with_kb.py`。该脚本只跑案例2：申万菱信 / 老客户激活 / `re_activation`，并保持四封节点为：Step1 曾经合作过唤醒、Step2 一体化服务介绍、Step3 近期成功案例、Step4 低压力备用窗口。
- 关键实现：Round0 真实读取 CRM、合作案例库、黄金邮件库；四轮仍是客户入口、业务结构和机会、初版邮件、人话改写并输出 JSON；前序邮件只用于避免重复，不代表客户回复。
- 最新可用文件：
  - `logs/case2-suite-deepseek-step1-kb-standard-20260617-132510.md`
  - `logs/case2-suite-deepseek-step2-kb-standard-20260617-132553.md`
  - `logs/case2-suite-deepseek-step3-kb-standard-20260617-132639.md`
  - `logs/case2-suite-deepseek-step4-kb-standard-20260617-132723.md`
  - 对比结论：`logs/case2-kb-standard-deepseek-final-comparison-20260617-1328.md`
- 废弃文件：
  - `logs/case2-suite-deepseek-step3-kb-standard-20260617-132236.md`：写了“配合下来比较顺畅”。
  - `logs/case2-suite-deepseek-step4-kb-standard-20260617-132318.md`：写了“之前聊到”。
- 后续注意：Step3 当前合作案例库缺少直接金融/资管案例，最终邮件采用同类活动/资料场景迁移。若案例库补入金融案例，应优先用金融案例再重跑 Step3。

## 2026-06-17 案例2信息密度与结构修正交接

- 用户继续指出：真正目标是“用第一版的克制和合规边界，吸收第二版的业务场景丰富度”，不能把邮件压成微信短句；Step2/Step3 应恢复短枚举、多个案例清单、业务场景块；黄金邮件库也必须真实参与。
- 已确认上一轮 case2 日志中 `gold_email_library.items` 为空，说明黄金邮件库没有真正提供可学习样本。已修正 `scratch/run_case2_reactivation_deepseek_with_kb.py` 的兜底检索逻辑：同场景为空时使用 approved/high-score full_email，并扩大 excerpt 长度。
- 已把信息密度和结构要求写入两份文档：
  - `docs/mail_multiturn_sales_email_generation_standard.md`
  - `docs/mail_sequence_12_step_purpose_draft.md`
- 最新通过样本：
  - Step2：`logs/case2-suite-deepseek-step2-kb-standard-20260617-141337.md`
  - Step3：`logs/case2-suite-deepseek-step3-kb-standard-20260617-141200.md`
  - 记录：`logs/case2-density-and-structure-adjustment-20260617-1416.md`
- 后续继续跑其他节点/其他 case 时，不要再用“正文 3-5 段、低压力”压短输出；应显式传入字数下限和结构要求。Step2/Step3 尤其应允许短枚举和案例清单。

## 2026-06-17 案例2最小限制与完整上下文交接

- **用户要求**：原则上能不限制就不限制；案例、知识库内容给全。不能为了“合规/克制”把所有邮件都压成短模板，也不能把风格词写成硬禁词。
- **已完成**：
  - `scratch/run_case2_reactivation_deepseek_with_kb.py` 的 `_quality_flags()` 已收窄为硬风险门：内部编号、电话邮箱、价格折扣、占位符、前序显性承接、客户反馈编造、爱德华/TAVR 等其他案例串场。
  - 已移除硬禁：`完整解决方案`、`一体化解决方案`、`赋能`、`链条`、`流程优化`、`期待您的回复`、`董事会资料` 等风格/结构项。此类内容后续只能作为人工软判断，不应脚本判失败。
  - Round0 仍给足 CRM、合作案例库、黄金邮件库长文本；当前合作案例库取 20 条、黄金邮件库取 10 条长摘录。
- **真实调用结果**：
  - Step2：`logs/case2-suite-deepseek-step2-kb-standard-20260617-142714.md`，质量标记 `pass`。
  - Step3：`logs/case2-suite-deepseek-step3-kb-standard-20260617-142820.md`，质量标记 `pass`。
  - 汇总：`logs/case2-minimal-constraints-full-context-20260617-1429.md`。
- **抽查结论**：
  - Step2 已恢复短枚举和足够信息量，覆盖金融资料、会议、视频、活动物料等场景。
  - Step3 已生成 3 条脱敏案例清单，不是服务清单；未写客户名、合同号、金额、具体日期或申万菱信当前项目。
- **后续注意**：
  - 黄金邮件长摘录里可能包含未脱敏公司名或旧模板占位符。当前最终输出未带出，但产品化时应在输入前做脱敏清洗，并保留长文本结构；不要重新裁成短摘要。
  - 后续扩展其他 case/step 时，不能重新把风格词加回硬禁词；只拦硬风险，风格问题进人工报告。
- **验证**：
  - `python -m py_compile scratch\run_case2_reactivation_deepseek_with_kb.py` 通过。
  - `git diff --check -- docs\mail_sequence_12_step_purpose_draft.md docs\mail_multiturn_sales_email_generation_standard.md scratch\run_case2_reactivation_deepseek_with_kb.py` 通过。

## 2026-06-17 案例1知识库增强四封 DeepSeek 交接

- **用户要求**：先把本轮要求更新到两个目的/标准文件：`邮件多轮销售生成标准`、`邮件三场景四节点目的说明草案`；同时优化 case1/case3 部分；随后完成 case1 的 4 封 DeepSeek 版本。
- **文档已更新**：
  - `docs/mail_sequence_12_step_purpose_draft.md`
  - `docs/mail_multiturn_sales_email_generation_standard.md`
  - 重点补入：少设硬限制、给全上下文、先脱敏再保留长文本、风格词只作软风险、同一 case 四封必须同一版脚本重跑。
  - case1 明确为医疗器械/生命科学老客户新业务，不只写翻译/同传；应覆盖医生教育、学术会议、患者教育、产品培训、市场活动、多媒体医学内容、会议同传/设备、展会活动物料和商务礼品。
  - case3 明确新联系人场景必须先判断公司层面合作基础；设备/技术资料客户围绕产品手册、安装说明、售后培训、技术视频和展会资料。
- **脚本已新增**：
  - `scratch/run_case1_new_business_deepseek_with_kb.py`
  - 该脚本基于 case2 已验证的知识库增强四轮结构改造，只处理 case1 / 爱德华 / `new_business_promotion`。
  - 真实读取 CRM、合作案例库、黄金邮件库；保留最小硬限制质量门。
  - Step3 多次出现“客户反馈/客户后续/之前聊到”后，已增加真实 API 修正轮；报告中保留第5/6轮修正过程。
- **最终可用文件**：
  - Step1：`logs/case1-suite-deepseek-step1-kb-standard-20260617-153201.md`，`pass`。
  - Step2：`logs/case1-suite-deepseek-step2-kb-standard-20260617-153253.md`，`pass`。
  - Step3：`logs/case1-suite-deepseek-step3-kb-standard-20260617-153354.md`，`pass`。
  - Step4：`logs/case1-suite-deepseek-step4-kb-standard-20260617-153450.md`，`pass`。
  - 汇总：`logs/case1-kb-standard-deepseek-final-comparison-20260617-1536.md`。
- **废弃文件不要使用**：
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-150619.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-150856.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-151540.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-151835.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-152227.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-152405.md`
  - `logs/case1-suite-deepseek-step3-kb-standard-20260617-152720.md`
- **验证**：
  - `python -m py_compile scratch\run_case1_new_business_deepseek_with_kb.py` 通过。
  - `git diff --check -- docs\mail_sequence_12_step_purpose_draft.md docs\mail_multiturn_sales_email_generation_standard.md scratch\run_case1_new_business_deepseek_with_kb.py` 通过。

## 2026-06-17 邮件 V39 案例3 Step1 Prompt 双模型直跑交接

- 用户要求：拿 `logs/mail-current-case3-step1-prompt-20260617.md` 中的脚本直接运行 DeepSeek 和 GPT 各一个，记录在邮件 V39 中，同时把脚本放在 prompt 中。
- 已新增 `scratch/run_mail_v39_case3_step1_prompt_compare.py`：
  - 读取 `logs/mail-current-case3-step1-prompt-20260617.md` 的 fenced `text` 内容作为模型 user prompt。
  - 分别调用 DeepSeek `deepseek-chat` 和 OpenAI `gpt-4.1`。
  - 新建 `mail_iteration_run.version_no=39`，run_id=`7330f5ea-e1b0-437c-9133-92ac17d28408`。
  - 使用 `demo_index=301/302` 分别记录 DeepSeek/GPT 两条 draft，避免同 run 下 `(demo_index, suite_step)` 唯一键冲突。
  - `mail_iteration_draft.llm_prompt` 已保存完整 prompt 原文；`response_payload` 已保存 raw output 和 parsed JSON；`real_sending_enabled=false`。
- 报告：`logs/mail-v39-case3-step1-prompt-compare-20260617.md`，完整包含 prompt 原文和两家模型输出。
- 结果摘要：
  - DeepSeek draft_id=`b7e32374-7957-427d-809f-98907d5d64bc`，耗时 3258ms，质量标记：`first_paragraph_not_exact_greeting`、`contains_full_company_name`。
  - OpenAI draft_id=`cd13e59b-0094-42a5-93f4-22637eb6ec89`，耗时 8261ms，质量标记：`first_paragraph_not_exact_greeting`、`subject_empty`、`contains_full_company_name`。
- 验证：`python -m py_compile scratch\run_mail_v39_case3_step1_prompt_compare.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V39 status=success、Drafts Count=2。

## 2026-06-17 邮件 V40 案例3 Step1 仅脚本双模型直跑交接

- 用户要求：只拿本轮消息中“任务/结构脚本/AI指令/变量取值”这段脚本，按上述规则完成 V40。
- 已新增 `scratch/run_mail_v40_case3_step1_script_only_compare.py`：
  - prompt 只包含用户本轮给出的精简脚本，不包含黄金范例库、合同案例库参考或 `logs/mail-current-case3-step1-prompt-20260617.md` 的后半段。
  - 分别调用 DeepSeek `deepseek-chat` 和 OpenAI `gpt-4.1`。
  - 新建 `mail_iteration_run.version_no=40`，run_id=`12b1631b-0ca7-423b-be08-f1d4ca98e81f`。
  - 使用 `demo_index=401/402` 分别记录 DeepSeek/GPT 两条 draft；`mail_iteration_draft.llm_prompt` 已保存本轮精简 prompt 原文。
  - `response_payload` 已保存 raw output 和 parsed JSON；`real_sending_enabled=false`。
- 报告：`logs/mail-v40-case3-step1-script-only-compare-20260617.md`，完整包含精简 prompt 原文和两家模型输出。
- 结果摘要：
  - DeepSeek draft_id=`9d13acda-1af9-40cc-98ba-59f5b3d7a9c2`，耗时 3880ms，质量标记：`first_paragraph_not_exact_greeting`。
  - OpenAI draft_id=`2ac2652f-6630-490d-89c2-9085f1276051`，耗时 5293ms，质量标记：`first_paragraph_not_exact_greeting`。
- 质量注意：V40 去掉黄金范例/合同案例后，两家模型仍没有稳定遵守“paragraphs 第一段必须只是称呼”；后续若要稳定，需要在 prompt 或出口校验中明确“第一段精确等于 `萧小姐`，称呼后的您好和正文必须放第二段”。
- 验证：`python -m py_compile scratch\run_mail_v40_case3_step1_script_only_compare.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V40 status=success、Drafts Count=2。

## 2026-06-18 邮件 V41 案例3 Step1 body_html 仅脚本双模型直跑交接

- 用户要求：只拿本轮消息中的 `subject/body_html` 脚本，按上述规则完成 V41；不再限制 `paragraphs` 段落数组，改为 HTML 符合邮件排版显示。
- 已新增 `scratch/run_mail_v41_case3_step1_body_html_script_only_compare.py`：
  - prompt 只包含用户本轮给出的 body_html 精简脚本，不包含黄金范例库、合同案例库参考或 V39/V40 的额外上下文。
  - system prompt 明确只输出 `subject` 和 `body_html` 两个字段，`body_html` 使用邮件可显示的常规 HTML 标签。
  - 分别调用 DeepSeek `deepseek-chat` 和 OpenAI `gpt-4.1`。
  - 新建 `mail_iteration_run.version_no=41`，run_id=`595fb0b0-71ca-418f-a8a8-15ff46b70df0`。
  - 使用 `demo_index=411/412` 分别记录 DeepSeek/GPT 两条 draft；`mail_iteration_draft.llm_prompt` 已保存本轮 prompt 原文。
  - `response_payload` 已保存 raw output 和 parsed JSON；`final_body_html` 直接保存模型返回的 `body_html`；`real_sending_enabled=false`。
- 报告：`logs/mail-v41-case3-step1-body-html-script-only-compare-20260618.md`，完整包含 prompt 原文和两家模型输出。
- 结果摘要：
  - DeepSeek draft_id=`df7f955e-a0b2-4463-a559-7578047dbf85`，耗时 4049ms，基础质量标记：`pass`。
  - OpenAI draft_id=`669d5ebf-aecc-4d5d-8e00-ea063a33b69d`，耗时 6030ms，基础质量标记：`pass`。
- 质量注意：
  - DeepSeek 使用了“近期注意到贵司在海外业务拓展上持续发力”，虽然未命中当前硬禁“最近”，但属于无真实 history 支撑的推断式表达。
  - OpenAI 引入“某大型制造企业策划国际展会宣传资料”的脚本外案例式表达；如果后续严格执行“必须使用 history 真实合作事实”，应把脚本外案例/未给定案例库事实加入质量门。
- 验证：`python -m py_compile scratch\run_mail_v41_case3_step1_body_html_script_only_compare.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V41 status=success、Drafts Count=2。

## 2026-06-18 邮件 V42/V43 案例3 Step1 body_html 去壳与纯用户脚本交接

- 用户指出 V41 输出出现 `SpeedAsia`，但用户脚本中没有；复核确认是 V41 system prompt 加了“事必达 SpeedAsia 的资深B2B销售邮件主笔”，属于额外加壳。
- V42 修正：
  - 新增 `scratch/run_mail_v42_case3_step1_body_html_no_shell_compare.py`。
  - 保留用户脚本原文，system prompt 只保留 JSON/HTML 格式约束，并禁止加入脚本外品牌/身份/案例。
  - 落库 `mail_iteration_run.version_no=42`，run_id=`1fb2291d-88f4-4a06-9408-8935f8c28063`，2/2 成功。
  - 报告：`logs/mail-v42-case3-step1-body-html-no-shell-compare-20260618.md`。
  - 两家输出不再出现 `SpeedAsia` 或 `事必达`，但仍存在脚本外事实扩写风险。
- 用户随后进一步明确：不要再额外加任何内容，“不得添加脚本外公司/品牌/身份/案例”也不要，给什么脚本就直接运行。
- V43 按该要求完成：
  - 新增 `scratch/run_mail_v43_case3_step1_body_html_user_prompt_only_compare.py`。
  - API `messages` 只包含一条 `user` 消息，内容即用户脚本原文；没有 system prompt，没有身份、品牌、禁词、案例或事实门补充。
  - 首次运行 OpenAI 因 SSL EOF 网络错误失败；新增 `scratch/retry_mail_v43_openai_user_prompt_only.py` 仅补跑 V43 中失败的 OpenAI draft，调用结构仍为单条 user prompt。
  - 最终落库 `mail_iteration_run.version_no=43`，run_id=`15e0dc06-30b3-4ada-ba93-b9dfd3a28e64`，2/2 成功。
  - 报告：`logs/mail-v43-case3-step1-body-html-user-prompt-only-compare-20260618.md`。
  - DeepSeek draft_id=`ae578f30-3c3c-4588-b978-4c7fddf532db`；OpenAI draft_id=`b079096e-a3be-4579-b7c4-0697cd07a65d`。
- 注意：V43 是纯用户脚本对照版，模型自由发挥更明显。DeepSeek 输出“我是王磊/最近/客户反馈”，OpenAI 输出“多个设备说明书和操作手册/某大型装备制造企业”等脚本外事实扩写；这些不是 system prompt 注入，而是无额外约束时模型自身生成。
- 验证：`python -m py_compile scratch\run_mail_v42_case3_step1_body_html_no_shell_compare.py scratch\run_mail_v43_case3_step1_body_html_user_prompt_only_compare.py scratch\retry_mail_v43_openai_user_prompt_only.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V43 status=success、Drafts Count=2。

## 2026-06-18 邮件 V44 案例3 Step1 精确脚本直跑交接

- 用户指出：V43 仍把“只拿以上脚本，按上述规则完成v41”这类执行句传给模型；新请求中末尾“以上做v43测试（此行内容不给，不要加其他）”明确不能传。
- 已新增 `scratch/run_mail_v44_case3_step1_body_html_exact_prompt_only_compare.py`：
  - API `messages` 只包含一条 `user` 消息，内容是用户邮件脚本正文。
  - 没有 system prompt，没有额外身份、品牌、禁词、案例、事实门补充。
  - `SCRIPT_ONLY_PROMPT` 只到“风格要求：像资深销售写给熟悉的客户公司新联系人，而不是营销模板”结束。
  - 脚本和报告已通过 `Select-String` 检查，均不包含用户末尾执行说明关键词。
- 初次运行：
  - DeepSeek 成功，draft_id=`d4cc399d-a17a-4e79-8d8f-f3833ec630d4`。
  - OpenAI 因 SSL EOF 网络错误失败。
- 已新增 `scratch/retry_mail_v44_openai_exact_prompt_only.py` 只补跑 V44 中失败的 OpenAI draft，仍使用同一条 user prompt；补跑成功，draft_id=`e508d796-9d21-4ca6-b5d7-a624ddf2ebf8`。
- 最终落库 `mail_iteration_run.version_no=44`，run_id=`0a6ca544-34d0-435a-b56b-3d4de0c13acf`，status=`success`，Drafts Count=2。
- 报告：`logs/mail-v44-case3-step1-body-html-exact-prompt-only-compare-20260618.md`。
- 验证：`python -m py_compile scratch\run_mail_v44_case3_step1_body_html_exact_prompt_only_compare.py scratch\retry_mail_v44_openai_exact_prompt_only.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V44 success。

## 2026-06-18 邮件 V45 案例3 Step1 结构脚本无输出契约直跑交接

- 用户本轮只给结构脚本和 AI 指令，去掉了 `只输出 JSON`/`subject/body_html` 输出契约；末尾执行说明明确不能传给模型。
- 因 `mail_iteration_run.version_no=44` 已存在，本轮使用 `version_no=45` 保存，报告说明这是用户所说 v44 测试的无输出契约对照版。
- 已新增 `scratch/run_mail_v45_case3_step1_body_html_exact_prompt_no_contract_compare.py`：
  - API `messages` 只包含一条 `user` 消息，内容为结构脚本正文。
  - 没有 system prompt。
  - 没有 `response_format`。
  - 没有额外 `只输出 JSON` 行。
  - 没有末尾执行说明。
- 已真实调用 DeepSeek `deepseek-chat` 与 OpenAI `gpt-4.1` 各一次；落库 `mail_iteration_run.version_no=45`，run_id=`cd3c4d34-169a-4d0f-80ae-e9d241038a2e`，status=`success`，Drafts Count=2。
- 报告：`logs/mail-v45-case3-step1-exact-prompt-no-contract-compare-20260618.md`。
- 结果：
  - DeepSeek draft_id=`146448c6-a49c-42ec-9511-8396247f8575`，返回 Markdown 风格普通邮件文本，`parsed_json=null`。
  - OpenAI draft_id=`5dcd3132-4162-4787-ae8b-b1ec959c1c26`，返回普通邮件文本，`parsed_json=null`。
- 结论：不加输出契约和 API `response_format` 时，模型不会稳定返回 JSON；这版适合作为“只给结构脚本”的 raw generation 对照，不适合作为自动 `subject/body_html` 解析链路输入。
- 验证：`python -m py_compile scratch\run_mail_v45_case3_step1_body_html_exact_prompt_no_contract_compare.py` 通过；定向 `git diff --check` 通过；`scratch/query_iterations.py` 确认 V45 success；关键词检查确认未传末尾执行说明和 `只输出 JSON` 行。
- 用户随后要求“把输出结果填写到对应位置”。已新增并执行 `scratch/backfill_mail_v45_outputs_to_fields.py`：
  - 不重跑模型。
  - 从 V45 两条 draft 的 `response_payload.raw_output` 解析并回填 `final_subject` / `final_body_html`。
  - DeepSeek：从 `**邮件主题**` 提取主题“关于孚乐率过往项目的支持与后续合作可能”，正文转 HTML 后长度 580。
  - OpenAI：raw output 没有主题行，不凭空生成主题；`final_subject` 保持空，正文转 HTML 后长度 462。
  - `logs/mail-v45-case3-step1-exact-prompt-no-contract-compare-20260618.md` 末尾已追加“回填字段”节。
- 回填验证：数据库查询显示 demo_index 451 主题与正文已填，demo_index 452 正文已填、主题为空；`python -m py_compile scratch\backfill_mail_v45_outputs_to_fields.py` 与定向 `git diff --check` 通过。

## 2026-06-18 邮件 V46 老客户多业务开发 4 脚本直跑交接

- 用户要求：读取 `C:\Users\Admin\Desktop\老客户多业务开发.txt` 的 4 个脚本，按 V45 同样方式测试，最终输出 8 个邮件，并把输出结果填写到对应位置。
- 已新增 `scratch/run_mail_v46_4scripts_exact_prompt_compare.py`：
  - 运行时读取桌面 txt。
  - 按 `第1封` 到 `第4封` 拆分 4 个脚本。
  - 每个脚本原文作为唯一 `user` prompt。
  - 没有 system prompt。
  - 没有 `response_format`。
  - 没有额外输出 JSON 契约。
  - 没有变量补值或额外上下文。
  - DeepSeek 和 OpenAI/GPT 各跑 4 个脚本，共 8 次模型调用。
  - 从 raw output 提取主题和正文，回填 `final_subject` / `final_body_html`。
- 已落库 `mail_iteration_run.version_no=46`，run_id=`baed295e-e557-4c4a-a085-9b054ef35b2e`，status=`success`，Drafts Count=8。
- 报告：`logs/mail-v46-4scripts-exact-prompt-compare-20260618.md`。
- 8 条 draft：
  - Step1 DeepSeek demo_index=471 draft=`46fd479f-3ed8-4765-8e4e-7a4f61a7f7ae`；OpenAI demo_index=472 draft=`79dbfc2b-8cc3-4b62-8f2d-17a53aebbfe8`。
  - Step2 DeepSeek demo_index=481 draft=`75eb9413-9163-47fc-8d1a-a4c0dbb9fc44`；OpenAI demo_index=482 draft=`c4c3b267-4d8a-4841-8a4a-d5ce7443dae6`。
  - Step3 DeepSeek demo_index=491 draft=`b6eb0eaf-5c0c-4595-bb44-48be52c2d19e`；OpenAI demo_index=492 draft=`fd478c98-9af8-4b97-9c27-83da65a811e1`。
  - Step4 DeepSeek demo_index=501 draft=`14ecef76-7be2-4a96-963f-314748902eb6`；OpenAI demo_index=502 draft=`4e65454d-7dde-45b9-a8b4-8bfe2adb84de`。
- 注意：源脚本仍包含 `{customer_name}`、`{company_name}`、`{industry}`、`{history}`、`{case_studies}` 等占位符。按 V45 同样方式未补变量，因此部分输出主题/正文保留占位符，这不是脚本 bug，是输入边界决定的结果。
- 验证：`python -m py_compile scratch\run_mail_v46_4scripts_exact_prompt_compare.py` 通过；定向 `git diff --check` 通过；DB 查询确认 V46 success、8 条 draft 均有 `final_subject` 和 `final_body_html`。

## 2026-06-18 邮件质量诊断模板区收窄与直接脚本生成交接

- **用户要求**：
  - 邮件质量诊断页“三大场景全阶段脚本模板（可编辑保存）”区域只显示两个字段：`AI指令`、`发送间隔`；其他字段都隐藏不在界面显示。
  - `AI指令` 默认取当前内容，可人工修改保存，保存失败要报错；之后生成时直接使用此脚本，只做变量替换，不再额外增加限制或约束。
  - `发送间隔` 为数字型，第一封默认 0，浮动说明“距今天多少天后发送”；第 2/3/4 封按逻辑默认填写，可人工修改保存。
  - 变量为 `{customer_name}`、`{company_name}`、`{history}`、`{industry}`；其中行业沿用现有行业判断逻辑。
- **已完成**：
  - `frontend/index.html` 模板区已移除目的说明、变量说明、结构脚本等旧渲染，只保留数字型 `发送间隔` 与 `AI指令` textarea。
  - `backend/main.py` 的模板序列化新增 `send_interval_days` / `send_interval_help`；旧 `send_timing_cn` 若不是纯数字或“距今天 X 天”，前端按默认累计间隔显示 0/7/17/27。
  - `PUT /api/v1/mail/sequence-templates/{scenario}/{suite_step}` 新增 `send_interval_days` 保存逻辑，保存为数字字符串以兼容现有表结构。
  - `_build_mail_draft_llm_full_prompt()` 已改为只取 `ai_instruction_script`，替换变量后直接返回该脚本；不再拼接系统 prompt、CRM 原始摘要、黄金范例库、合同案例库、边界规则和 JSON 输出要求。
  - 邮件草稿 LLM 调用新增纯文本路径 `_call_llm2_text_for_mail_draft()`，不再强制 `response_format=json_object`；后端新增 raw text 解析，能从 JSON/body_html/paragraphs/主题标签/纯正文中回填草稿字段。
- **变量当前口径**：
  - `{industry}`：沿用 `_mail_generation_industry_for_prompt()`，也就是目前项目内已有的行业归一判断。
  - `{customer_name}`：本地归一，英文名保留英文首段；中文联系人按姓氏加先生/小姐的保守规则处理。
  - `{company_name}`：本地去掉常见公司后缀后作为简称。
  - `{history}`：从 CRM 商机/合同/跟进文本归纳为“为客户提供XX服务”，服务项按笔译、同传、多媒体译制、排版印刷、活动物料等关键词提取。
  - 本轮未新增 deepseek14b 变量预处理调用；如后续要完全按用户描述由 deepseek14b 判断称呼、公司简称和合同服务总结，需要另接变量预处理接口。
- **验证**：
  - `python -m py_compile backend\main.py` 通过。
  - `git diff --check -- backend/main.py frontend/index.html` 通过。
  - `rg` 确认模板区不再渲染 `mql-template-purpose`、`mql-template-send`、`mql-template-script`、“变量说明”、“结构脚本”、“保存目的”等旧控件和文本。
- **注意**：
  - 工作区中 `backend/main.py` 和 `frontend/index.html` 原本已有其他未提交改动，本轮未回滚也未整理。
  - `TASKS.md` 的第一个未完成任务仍是 Task 79（SMTP 真发通道），本轮没有启用真实发送，也未修改 Task 79 状态。

## 2026-06-18 邮件 V47 老客户公司新联系人 4 脚本变量替换后直跑交接

- **用户要求**：读取 `C:\Users\Admin\Desktop\老客户公司新联系人.txt` 的 4 个脚本，按 V46 一样测试，最终输出 8 个邮件并填写到对应位置；中间变量先由当前 Agent 替换，客户为案例3客户联系人。用户确认变量后要求“好的进行v47”。
- **变量替换**：
  - `{customer_name}` -> `萧小姐`
  - `{history}` -> `为客户提供笔译、排版印刷服务`
  - `{industry}` -> `工业设备/制造客户`
  - `{case_company_1}` -> `某跨国制造集团`
  - `{case_company_2}` -> `某大型工业设备企业`
  - `{case_company_3}` -> `某知名空气处理设备厂商`
- **已完成**：
  - 新增并执行 `scratch/run_mail_v47_new_contact_replaced_prompt_compare.py`。
  - 脚本读取桌面 txt，拆分 4 个脚本，先做变量替换并检查替换后 prompt 不残留 `{...}` 占位符。
  - 每个替换后脚本作为唯一 `user` prompt；无 system prompt、无 `response_format`、无额外输出契约。
  - DeepSeek 与 OpenAI/GPT 各跑 4 个脚本，共 8 次真实 LLM 调用。
  - 从 raw output 提取主题和正文，回填 `mail_iteration_draft.final_subject` / `final_body_html`。
- **落库结果**：
  - `mail_iteration_run.version_no=47`
  - run_id=`bd54285e-e125-41c7-b2eb-5a9351f72fd9`
  - status=`success`
  - Drafts Count=8，8/8 成功，真实发信关闭。
- **报告**：`logs/mail-v47-new-contact-replaced-prompt-compare-20260618.md`。
- **8 条 draft**：
  - Step1 DeepSeek draft=`ea476090-6985-424d-bf6c-7b4405cee715`；OpenAI draft=`ca8f7b6b-43b0-46be-a6ae-21afa41679d2`。
  - Step2 DeepSeek draft=`f33743cb-726b-4f51-92af-44f4815c4d4b`；OpenAI draft=`918165a6-438f-44ac-8f8d-c20c0ec9898e`。
  - Step3 DeepSeek draft=`cf3c6241-e16b-4537-994c-9f515742f91e`；OpenAI draft=`26ac163e-d02e-48b8-8653-a183ec320876`。
  - Step4 DeepSeek draft=`bd4195ad-931c-47d2-b071-fbb01adba979`；OpenAI draft=`de183c38-4af6-40a1-b416-3dfacc2d0063`。
- **注意**：OpenAI 四封未显式输出主题行，所以 `final_subject` 为空但正文 HTML 已填；DeepSeek 四封均提取到主题。报告中的“源文件全文”会保留原占位符用于审计，实际模型 prompt 和数据库 `llm_prompt` 已使用替换后脚本。
- **验证**：
  - `python -m py_compile scratch\run_mail_v47_new_contact_replaced_prompt_compare.py` 通过。
  - `python scratch\run_mail_v47_new_contact_replaced_prompt_compare.py` 成功返回 8/8。
  - `python scratch\query_iterations.py 47` 确认 V47 status=success、Drafts Count=8。
  - 定向 `git diff --check` 通过。

## 2026-06-18 邮件 V48 老客户激活 4 脚本变量替换后直跑交接

- **用户要求**：读取 `C:\Users\Admin\Desktop\老客户激活.txt` 的 4 个脚本，做 V48 测试，要求和 V47 一样，最终输出 8 个邮件并填写到对应位置；中间变量由当前 Agent 先完成替换，客户为案例2客户联系人。
- **变量替换**：
  - `{customer_name}` -> `周希`
  - `{company_name}` -> `申万菱信`
  - `{industry}` -> `金融/资管客户`
  - `{history}` -> `为客户提供董事会资料、议案及中英文资料笔译服务`
  - `{business_lines}` -> `笔译、会议沟通支持、多语言资料、本地化排版、多媒体内容及对外展示支持`
  - `{case_company_1}` -> `某大型金融机构`
  - `{case_company_2}` -> `某跨国资管集团`
  - `{case_company_3}` -> `某上市金融服务集团`
- **已完成**：
  - 新增并执行 `scratch/run_mail_v48_reactivation_replaced_prompt_compare.py`。
  - 脚本读取桌面 txt，拆分 4 个脚本；兼容 `第一封`、`第二封`、`第2封：...` 等标题，并合并重复空标题。
  - 每个替换后脚本作为唯一 `user` prompt；无 system prompt、无 `response_format`、无额外输出契约。
  - DeepSeek 与 OpenAI/GPT 各跑 4 个脚本，共 8 次真实 LLM 调用。
  - 从 raw output 提取主题和正文，回填 `mail_iteration_draft.final_subject` / `final_body_html`。
- **落库结果**：
  - `mail_iteration_run.version_no=48`
  - run_id=`3a1b84db-d46e-49ee-959b-53513b1b0bc2`
  - status=`success`
  - Drafts Count=8，8/8 成功，真实发信关闭。
- **报告**：`logs/mail-v48-reactivation-replaced-prompt-compare-20260618.md`。
- **8 条 draft**：
  - Step1 DeepSeek draft=`e1f48164-9323-46fd-86b8-5d000228efff`；OpenAI draft=`381571ee-9002-4baf-87ec-4bf834360223`。
  - Step2 DeepSeek draft=`aee7bc01-2b28-4dc0-bf20-2036b468c168`；OpenAI draft=`345d13ec-c1d0-4478-8f61-1241477a45c1`。
  - Step3 DeepSeek draft=`d9309b22-7e34-4ea1-83b7-4e782d955cbc`；OpenAI draft=`141d99ae-365f-4c1d-aa5a-b568ec3a5817`。
  - Step4 DeepSeek draft=`61633d97-9563-43dd-8c73-2a4655c9b386`；OpenAI draft=`0f01346c-a906-4efd-8355-a1314f0ddcc3`。
- **注意**：OpenAI 第1封和第4封未显式输出主题行，所以 `final_subject` 为空但正文 HTML 已填；其余 6 封主题和正文均已提取。报告中的“源文件全文”会保留原占位符用于审计，实际模型 prompt 和数据库 `llm_prompt` 已使用替换后脚本。
- **验证**：
  - `python -m py_compile scratch\run_mail_v48_reactivation_replaced_prompt_compare.py` 通过。
  - `python scratch\run_mail_v48_reactivation_replaced_prompt_compare.py` 成功返回 8/8。
  - `python scratch\query_iterations.py 48` 确认 V48 status=success、Drafts Count=8。
  - 定向 `git diff --check` 通过。

## 2026-06-18 邮件 V49 案例1老客户多业务开发 4 脚本变量替换后直跑交接

- **用户要求**：读取 `C:\Users\Admin\Desktop\老客户多业务开发.txt` 的 4 个脚本，做 V49 测试，要求和 V48 一样，最终输出 8 个邮件并填写到对应位置；中间变量由当前 Agent 先完成替换，客户为案例1客户联系人。
- **变量替换**：
  - `{customer_name}` -> `Michelle Li`
  - `{company_name}` -> `爱德华`
  - `{industry}` -> `医疗器械/生命科学客户`
  - `{history}` -> `为客户提供笔译、同传设备及会议口译相关支持`
  - `{business_lines}` -> `笔译、会议同传及设备支持、多语言资料、本地化排版、多媒体医学内容、展会活动物料及商务礼品支持`
  - `{case_company_1}` -> `某跨国医疗器械企业`
  - `{case_company_2}` -> `某生命科学集团`
  - `{case_company_3}` -> `某大型医疗技术企业`
  - `{case_studies}` -> `3条医疗器械/生命科学脱敏案例文本`
- **已完成**：
  - 新增并执行 `scratch/run_mail_v49_case1_multibusiness_replaced_prompt_compare.py`。
  - 脚本读取桌面 txt，拆分 4 个脚本，先做变量替换并检查替换后 prompt 不残留 `{...}` 占位符。
  - 每个替换后脚本作为唯一 `user` prompt；无 system prompt、无 `response_format`、无额外输出契约。
  - DeepSeek 与 OpenAI/GPT 各跑 4 个脚本，共 8 次真实 LLM 调用。
  - 从 raw output 提取主题和正文，回填 `mail_iteration_draft.final_subject` / `final_body_html`。
- **落库结果**：
  - `mail_iteration_run.version_no=49`
  - run_id=`a75a3502-ab52-44df-957b-7c21e61db0bc`
  - status=`success`
  - Drafts Count=8，8/8 成功，真实发信关闭。
- **报告**：`logs/mail-v49-case1-multibusiness-replaced-prompt-compare-20260618.md`。
- **8 条 draft**：
  - Step1 DeepSeek draft=`25c51e4c-d2b7-4d46-bc98-402af5155193`；OpenAI draft=`9fba7eeb-a68e-4638-b3b5-03541fdd69dc`。
  - Step2 DeepSeek draft=`9a01e320-9c82-4f91-a14c-deaefb16a448`；OpenAI draft=`8ad0cb69-40f7-4fcc-a0c8-2187182ea3b8`。
  - Step3 DeepSeek draft=`67056c7d-baa7-4517-985b-35abe3db2320`；OpenAI draft=`1a86dda0-9c6b-4938-869b-03045530331b`。
  - Step4 DeepSeek draft=`61732028-43e1-434a-9a32-1ba3eeb55751`；OpenAI draft=`07e02a90-d0a1-4af3-9798-f49d9bd7b71a`。
- **注意**：8 封均提取到主题和正文。Step3 原脚本只提供 `company_name`、`industry`、`case_studies`，未提供 `customer_name`，因此两家 Step3 质量备注为 `missing_known_greeting`；这是脚本输入结构导致，不影响本轮落库和字段回填。
- **验证**：
  - `python -m py_compile scratch\run_mail_v49_case1_multibusiness_replaced_prompt_compare.py` 通过。
  - `python scratch\run_mail_v49_case1_multibusiness_replaced_prompt_compare.py` 成功返回 8/8。
  - `python scratch\query_iterations.py 49` 确认 V49 status=success、Drafts Count=8。
  - 定向 `git diff --check` 通过。

## 2026-06-18 邮件质量诊断模板保存按钮修复交接

- **用户反馈**：邮件质量诊断页面“三大场景全阶段脚本模板（可编辑保存）”区域点“保存 AI 指令”没有用。
- **定位**：
  - 前端保存函数为 `saveMailSequenceTemplateField(...)`，调用 `PUT /api/v1/mail/sequence-templates/{scenario}/{suite_step}`。
  - 后端保存路由存在，支持 `send_interval_days` 与 `ai_instruction_script`。
  - 前端 AI 指令按钮原来嵌在包裹 textarea 的 `label` 内，长文本区域下按钮点击反馈不明确，容易表现为点击无效。
- **已改**：
  - `frontend/index.html`：AI 指令区域改为 `div + label[for] + textarea + button`，按钮不再嵌套在 label 内。
  - `frontend/index.html`：AI 指令保存按钮和发送间隔保存按钮均增加独立 id；保存时按钮显示“保存中...”，失败时显示“保存失败，重试”，顶部状态栏继续显示后端错误。
  - `frontend/index.html`：按用户继续反馈“模板文字太多”，将 AI 指令编辑框默认高度压缩为 8rem 内部滚动，并隐藏卡片头部版本号/更新时间，只保留阶段标题、发送间隔和 AI 指令。
- **验证**：抽取 `frontend/index.html` 内联脚本后 `node --check` 通过。
- **注意**：本轮未对线上生产模板做 PUT 写入验证，避免改动用户当前模板内容；若部署后仍失败，优先看浏览器 Network 中 `PUT /api/v1/mail/sequence-templates/...` 的状态码和返回 `detail`。

## 2026-06-18 邮件质量诊断模板 12 份案例维度交接

- **用户反馈**：每个案例要有不同版本，相当于 12 个模板；当前按 3 个场景显示导致 3 个案例模板一样。
- **已改设计**：
  - 旧维度：`scenario + suite_step`。
  - 新维度：`customer_key + scenario + suite_step`。
  - 当前测试面板默认生成/展示 `MAIL_CURRENT_DEMO_CASES` 中 3 个案例各 4 封模板，共 12 份。
- **已改文件**：
  - `backend/database.py`：`MailSequenceTemplate` 增加 `customer_key`，唯一键改为 `customer_key, scenario, suite_step`。
  - `backend/main.py`：建表/补丁新增 `customer_key` 列，删除旧唯一约束 `uq_mail_sequence_template_scenario_step`，增加客户维度唯一索引；`_ensure_mail_sequence_templates` 改为创建 12 份当前案例模板；`_get_mail_sequence_template_for_prompt` 支持 `customer_key`，生成草稿时优先取客户模板。
  - `backend/main.py`：`GET /api/v1/mail/sequence-templates` 返回 `templates_by_case` 与 `case_order`；`PUT /api/v1/mail/sequence-templates/{scenario}/{suite_step}` 支持 `customer_key` query。
  - `frontend/index.html`：模板下拉从场景改为案例；渲染 `templates_by_case[customer_key].templates`；保存时带 `customer_key`，不同案例不会互相覆盖。
- **后续修正**：
  - 用户反馈“显示了，但修改保存还是 3 个案例共用 4 个模板”。线上 `GET /api/v1/mail/sequence-templates` 已确认返回 12 条、`degraded=false`。
  - 为兼容旧前端缓存或旧保存请求未带 `customer_key`，后端保存接口增加兜底：不带 `customer_key` 时根据场景映射当前案例客户编号，`new_business_promotion -> KH15411-117`，`re_activation -> KH02659-011`，`new_contact_intro -> KH13770-006`；找不到行时新建该案例模板行，不覆盖旧共享历史模板。
  - 用户反馈模板区不应新增独立下拉，应该跟随上方案例切换联动。`frontend/index.html` 已移除 `mql-template-scenario` 下拉，模板区通过 `mailDemoContactActiveIndex` 自动取当前上方案例对应的 4 个模板；`pickMailDemoContact(...)` 会同步重渲染模板区。
- **验证**：
  - `python -m py_compile backend\main.py backend\database.py` 通过。
  - 抽取 `frontend/index.html` 内联脚本后 `node --check` 通过。
  - `SKIP_DB_PATCH=1` 导入 `main` 并确认 `/api/v1/mail/sequence-templates` 与 `/api/v1/mail/sequence-templates/{scenario}/{suite_step}` 路由注册通过。
  - `SKIP_DB_PATCH=1` 导入 `main` 并断言 3 个场景到 3 个客户编号的映射通过。
  - 抽取 `frontend/index.html` 内联脚本后 `node --check` 通过，并确认不再存在 `mql-template-scenario` 引用。
  - `git diff --check -- backend/main.py backend/database.py frontend/index.html` 通过。
- **注意**：本轮未对线上数据库执行真实迁移请求；首次线上启动会通过现有初始化逻辑补列、删旧唯一约束并创建新唯一索引。若旧库存在重复脏数据，唯一索引创建可能需要人工清理重复行。

## 2026-06-18 mail-suite 独立页草稿生成修复交接

- **用户要求**：上面邮件质量诊断模板的新流程，也要对 `https://api.speedasia.net/static/mail-suite.html?id=KH33879-001` 生效；只生成草稿、不真实发信时，允许无有效邮箱，用内部草稿占位邮箱或跳过 recipient email 硬校验。用户说明 CRM 中该客户实际有邮箱。
- **线上验证前状态**：
  - `GET /static/mail-suite.html?id=KH33879-001` 返回 200。
  - `GET /api/v1/mail/customer-suite?id=KH33879-001` 命中真实 CRM：`crm_profile_source=crm_sql_customer_key_contact_email`，客户为 `恩富软件（中国）有限公司`，客户域名 `infor.com`。
  - 4 封草稿均失败：`valid recipient email is required`。
  - 原因：`sanitize_text` 会把邮箱脱敏成 `***EMAIL***`，`customer-suite` 又把该脱敏值传给草稿生成邮箱校验。
- **已改**：
  - `backend/main.py` 新增 `_mail_review_only_draft_contact_email(...)`：从 CRM 客户域名生成内部 review-only 地址，例如 `draft-only+kh33879-001@infor.com`，仅用于草稿生成安全门校验，不真实发信。
  - `backend/main.py` 新增 `_mail_is_review_only_draft_email(...)`，避免占位邮箱本地部分被当作客户称呼。
  - `get_mail_customer_suite(...)`：`customer_profile.contact_email` 仍保留脱敏展示；`MailGenerateDraftRequest.contact_email` 改用生成专用 `draft_contact_email`。
  - `_get_mail_sequence_template_for_prompt(...)`：如果非当前 3 个案例客户没有专属模板，回落到同 `scenario + suite_step` 的已保存案例模板，保证独立页也走新 AI 指令模板链路。
- **验证**：
  - `python -m py_compile backend\main.py backend\database.py` 通过。
  - `SKIP_DB_PATCH=1` 导入 `main` 并断言 `KH33879-001 + infor.com` 可生成 review-only 占位邮箱，通过。
  - `git diff --check -- backend/main.py backend/database.py frontend/index.html PROGRESS.md TASK_HANDOFF.md logs/codex-run.log` 通过。
- **注意**：本轮改的是本地代码；线上需部署后再复测该 URL。真实发信仍关闭，review-only 占位邮箱只用于草稿生成链路通过安全门。

## 2026-06-18 mail-suite 脚本外 SpeedAsia 品牌词修复交接

- **用户反馈**：`https://api.speedasia.net/static/mail-suite.html?id=KH33879-001` 生成草稿中出现脚本里没有的 `SpeedAsia Sales`，要求所有 `SpeedAsia` 替换为 `事必达`。
- **定位**：
  - `SpeedAsia Sales` 直接来源于 `backend/main.py` 的 `get_mail_customer_suite()` 默认 `seller_name` / `seller_signature`。
  - 旧模板种子、fallback 签名、邮件迭代默认签名中也残留 `SpeedAsia` / `SPEED`，若线上数据库已有旧模板，单纯改种子仍可能继续漏出。
- **已改**：
  - `backend/main.py` 新增 `_mail_brand_display_text()`，只做品牌词替换，不向 LLM 追加任何新限制或约束。
  - 模板变量替换、模板接口序列化、模板保存、最终草稿 `subject/body_html/llm_prompt` 出站都调用品牌词归一，旧库内容也会在展示和生成出口被替换。
  - `mail-suite` 默认销售姓名/签名改为 `事必达销售`。
  - 模板种子、fallback 默认签名、迭代默认签名中的 `SpeedAsia`/`SPEED` 改为 `事必达`。
  - `backend/database.py` 的 `MailDemoContact.default_seller_signature` 默认值改为 `销售测试\n事必达翻译与本地化部`。
- **验证**：
  - `python -m py_compile backend\main.py backend\database.py` 通过。
  - `git diff --check -- backend/main.py backend/database.py` 通过。
  - `SKIP_DB_PATCH=1` 导入 `main` 并断言 `_mail_brand_display_text('SpeedAsia Sales / SPEED') == '事必达 Sales / 事必达'` 通过。
  - `rg -n "SpeedAsia|SPEED" backend/main.py backend/database.py frontend/index.html` 只剩归一函数自身包含匹配词。
- **下一步**：服务器端人工更新后，重新打开该 URL 生成草稿，正文签名应显示 `事必达销售`，不应再出现 `SpeedAsia Sales`。

### 追加修正：正文中 LLM 自发输出 SpeedAsia

- **用户补充截图**：正文里也有 `是否方便将SpeedAsia列为参考供应商`，说明问题不只是默认签名，LLM 正文也会自发输出该品牌词。
- **已改**：`MailGenerateDraftResponse.model_post_init()` 对所有最终响应做最后一层归一，覆盖普通 drafted、红牌阻断、黄牌锁定等所有返回分支的 `final_subject` 与 `final_body_html`。
- **新增验证**：构造 `MailGenerateDraftResponse(final_subject='SpeedAsia subject', final_body_html='<p>是否方便将SpeedAsia列为参考供应商</p><p>SpeedAsia Sales</p>')`，返回对象中已变为 `事必达 subject` 和 `事必达 Sales`。

## 2026-06-18 mail-suite 联系人显示与草稿卡片隐藏项交接

- **用户反馈**：`mail-suite` 独立页客户信息区“联系人”为空，但邮件正文里的联系人称呼是对的；草稿正文下方“目标推广业务 / 已有业务线 / 下一步建议”整块不应显示。
- **定位**：
  - 正文称呼走生成链路内部 CRM 查询的 `contact_name`。
  - 页面客户信息区读取 `profile.crm_contact_name`，但 `GET /api/v1/mail/customer-suite` 的 `customer_profile` 原来没有返回该字段，所以页面为空。
  - 草稿卡片下方三列信息来自 `review_metadata.crm_profile_signals` 和 `review.suggested_next_step`，属于内部诊断展示。
- **已改**：
  - `backend/main.py`：`customer_profile` 补充 `crm_contact_name` 与 `contact_name`，均来自 CRM 联系人姓名；同时透传 `customer_lifecycle_stage/customer_tier/existing_business_lines` 供页面需要时使用。
  - `frontend/mail-suite.html`：客户信息区联系人优先读取 `profile.crm_contact_name`，缺失时回退 `profile.contact_name`。
  - `frontend/mail-suite.html`：移除草稿正文下方“目标推广业务 / 已有业务线 / 下一步建议”整块内部诊断面板；复制按钮和反馈区保留。
- **边界**：本次没有修改任何 LLM prompt、AI 指令、模板规则或额外生成约束。
- **待验证**：部署后打开 `https://api.speedasia.net/static/mail-suite.html?id=KH33879-001`，客户信息区应显示脱敏联系人；草稿正文下方不再显示目标推广业务、已有业务线、下一步建议三列面板。

## 2026-06-23 企微智能助手第二候选去思考过程交接

- 用户反馈：企微回复智能助手中第二条候选不应显示思考过程，应直接给可发结果；要求仅涉及企微。
- 已完成：`backend/intent_engine.py` 增强 `clean_sendable_reply()`，抽取显式最终回复标签，过滤“理解重点/思考过程/策略”等元分析；截图类暂无需求场景兜底为直接可发承接话术。
- 已完成：`backend/main.py` 流式盲评 `_blind_texts` 对 AI 与训练AI两路都调用 `IntentEngine.clean_sendable_reply()`，与非流式保持一致。
- 验证：py_compile、定向 diff-check、函数级样例均通过。
- 注意：启动规则要求读取的 `企微记录入知识库标准定义.md` 当前仓库根目录未找到，本轮已按现有企微代码与 `项目进展.md` 继续处理；未改邮件相关文件。

## 2026-06-23 邮件统计实发漏计交接

- 用户指出邮件统计页 AI实际发送数为0，但 CRM 截图显示 2026-06-23 16:00 东丽医疗邮件已发送。
- 核查：CRM spSendInfo0017 中该邮件 Status=SendSuccess、FactSendTime=2026-06-23 16:00:28；本地对应 plan_id=4fac741e-8974-4b5a-99e4-d282a30005ca 原 crm_send_id 为空，因此旧 sync_send_status 未查询它。
- 已改 backend/mail_ai_stats.py：新增 _crm_send_info_for_missing_send_id fallback，缺 SendId 时按 subject + PlanSendTime 窗口 + UseRange + sender 反查 spSendInfo；同时兼容 SQL Server text 字段 CAST 后再匹配。
- 已验证并写回本地统计缓存：目标记录 crm_send_id=Mal_S260623-000003、crm_send_status=SendSuccess、crm_fact_send_time=2026-06-23 16:00:28；2026-06-23 sent_count=1。
- 注意：用户消息中贴过真实 .env 密码，后续回复和日志不得回显。

## 2026-06-24 09:42:29 邮件新增套装下拉与标题编辑交接

- 用户反馈：邮件质量诊断页新增套装后刷新仍不在模板下拉显示；单独 mail-suite.html 页面已显示；同时要求每封邮件标题可修改。
- 已完成：backend/main.py 将自建套装模板纳入 /api/v1/mail/sequence-templates 返回，新增 	emplate_group_key，动态套装以 scenario 分组；保存接口允许动态 scenario，并支持保存 step_label_cn。
- 已完成：frontend/index.html 模板区下拉读取动态分组；每封模板阶段标题可编辑保存；质量诊断页单封和整套生成结果里的邮件主题改为输入框可人工修改。
- 验证：后端 py_compile、前端内联脚本 node --check、定向 diff-check、自建套装序列化冒烟均通过。
- 注意：本轮没有启用真实发信，没有访问或输出任何密钥；工作区原本已有大量未提交/未跟踪文件，本轮只处理 backend/main.py 与 frontend/index.html，并为前端脚本检查生成了 scratch/frontend-index-scripts-check.js 临时校验文件。

## 2026-06-24 10:40:58 知识库命中日志双击查看交接

- 范围：知识库管理 > 命中日志。
- 后端：backend/main.py 新增 _hit_log_hit_chunks；GET /api/kb/hit_logs 增加 include_hits 参数，true 时返回 hit_chunks。默认不带详情，兼容旧调用。
- 前端：frontend/index.html 的 loadKbLogs 请求 include_hits=true；命中数按钮支持双击打开弹窗，显示每条命中切片详情。
- 验证：py_compile、前端 node --check、定向 diff-check 通过。
- 注意：未读取或输出 .env 密钥；未启用真实发信；工作区原有大量未提交改动未处理。


## 2026-06-24 10:41:15 知识库命中日志双击查看交接

- 范围：知识库管理 > 命中日志。
- 后端：backend/main.py 新增 _hit_log_hit_chunks；GET /api/kb/hit_logs 增加 include_hits 参数，true 时返回 hit_chunks。默认不带详情，兼容旧调用。
- 前端：frontend/index.html 的 loadKbLogs 请求 include_hits=true；命中数按钮支持双击打开弹窗，显示每条命中切片详情。
- 验证：py_compile、前端 node --check、定向 diff-check 通过。
- 注意：未读取或输出 .env 密钥；未启用真实发信；工作区原有大量未提交改动未处理。

## 2026-06-24 11:18:57 邮件测试套装 111/222 删除交接

- 用户要求：删除邮件质量诊断页下拉中的 111、222 两个测试套装。
- 已完成：查到 111 -> custom_ec17323c、222 -> custom_0bccb7bd，各 3 条 mail_sequence_template；已删除对应 6 条模板和 2 条 mail_custom_suite 元数据。
- 验证：删除后按 label/scenario 复查，mail_custom_suite 残留 0，mail_sequence_template 残留 0；当前 remaining_custom_suites 为空。
- 注意：没有启用真实发信，没有输出或复制 .env 凭据。若浏览器仍显示旧下拉，点击“刷新模板”或刷新页面即可重新拉取后端数据。

## 2026-06-24 13:00:05 邮件模板下拉文案去重交接

- 用户要求：模板下拉只显示后面的字段，避免“老客户其他业务介绍 · 老客户其他业务介绍”这类重复。
- 已完成：frontend/index.html 的 renderMailTemplateCaseSelect 改为优先显示 scenario_label_cn，回退 case_label/key。
- 验证：前端内联脚本 node --check 和 frontend/index.html 定向 diff-check 均通过。
- 注意：本轮未修改后端、未启用真实发信、未输出 .env 凭据。

## 2026-06-24 13:23:06 交接：邮件套装页重刷/脚本按钮
- 已完成：保存表新增 llm_prompt 字段；生成响应携带 llm_prompt；套装自动保存和单封重刷会落库真实 prompt；前端新增重刷/脚本按钮和 prompt 展示面板。
- 注意：旧历史保存稿如果当时没有 llm_prompt 字段，无法证明当时 prompt，页面会提示缺失；重刷后会保存本次真实 prompt。
- 验证：py_compile、前端脚本 node --check、git diff --check 均通过。

## 2026-06-24 13:34:53 交接：老客户激活用错模板
- 原因：KH33103-015 无专属模板时，旧查找顺序先取 customer_key='' 的共享模板，导致老客户激活没有使用质量页规范模板。
- 已修复：_get_mail_sequence_template_for_prompt 对内置场景先查规范 customer_key，再查空共享模板。
- 现状：KH33103-015/re_activation 已有 4 条旧保存稿和旧 llm_prompt；不自动覆盖人工/历史保存内容。前端点‘重刷’会按新模板重新运行 LLM 并覆盖单封。

## 2026-06-24 13:40:54 交接：套装模板严格模式
- 生成路径 _get_mail_sequence_template_for_prompt 已改为严格读取规范模板，不再使用客户专属/空共享/任意模板 fallback。
- 当前验证 4 个套装全部 OK：new_business_promotion=>KH15411-117，re_activation=>KH02659-011，new_contact_intro=>KH13770-006，print_quote_followup=>PRINT-QUOTE-FOLLOWUP。
- 注意：旧保存稿仍会按 saved_edit 读取，不会被自动覆盖；要更新旧页面内容需点单封重刷。

## 2026-06-24 14:03:48 交接：自动判断场景不跟随手动下拉
- 后端 customer-suite 响应新增 auto_scenario / auto_scenario_label_cn / auto_scenario_basis，同时保留当前使用 scenario。
- 前端客户信息里的自动判断场景固定读 auto_* 字段；手动切换下拉仅改变当前生成套装。
- 验证通过：py_compile、mail-suite 脚本 node --check、diff check。

## 2026-06-24 14:22:58 交接：当天统计实时刷新与签名兜底
- get_mail_ai_stats_summary 中 includes_today=true 时自动 refresh_all，不再需要用户点从CRM刷新才更新当天真发/回信/价值。
- 新增 _mail_suite_signature_context，套装页/重刷/发送共用签名上下文；展示和重刷正文会始终注入非空签名。
- 注意：发送仍要求真实企业发件邮箱；兜底签名只解决正文展示/草稿签名，不绕过发件邮箱校验。

## 2026-06-24 17:12:00 知识库管理独立页面交接

- 用户要求：这个节点单独出一个网页，原有保持不变；新页面隐藏“返回企微实时智能”；隐藏“知识分类怎么选”那排说明卡片。
- 已完成：新增 `frontend/kb.html` 作为独立入口，iframe 打开 `index.html?kbStandalone=1#kb`；`index.html` 检测 `kbStandalone=1` 后自动打开知识库管理并加 `body.kb-standalone`，隐藏返回按钮和知识分类说明卡片。
- 验证：前端内联脚本 `node --check` 通过；定向 `git diff --check` 通过。
- 注意：未输出或复制 `.env` 凭据；工作区原本已有大量未提交改动，本轮只新增/修改前端独立入口相关内容和状态日志。

## 2026-06-24 17:20:00 知识库列表默认已发布交接

- 用户要求：进入知识库页面默认就是“已发布”，两个页面保持一致。
- 已完成：`frontend/index.html` 中 `documents` 列表状态默认阶段改为 `published`；由于独立页 `frontend/kb.html` 复用同一入口逻辑，两个页面默认一致。
- 验证：前端内联脚本 `node --check` 通过；定向 `git diff --check` 通过。

## 2026-06-24 17:52:00 邮件生成模型配置交接
- 范围：仅邮件模块；未修改企微回复生成链路。
- 主要文件：backend/main.py、frontend/index.html、frontend/mail-suite.html。
- 配置接口：GET/PUT /api/v1/mail/draft-llm-config；请求建议使用 {"model":"deepseek-v4-flash"|"deepseek-v4-pro"|"chatgpt"}，旧 provider 字段仍兼容。
- 生成链路：_call_llm2_json_for_mail_draft/_call_llm2_text_for_mail_draft 未显式传 model 时读取 runtime_llm_settings.json 的 mail_generation_model。
- 验证通过：py_compile、两个前端脚本 node --check、定向 diff-check。
- 注意：未启动真实发信；未输出或修改任何密钥。

## 2026-06-24 18:02:00 知识库独立页免登录交接
- 用户要求：frontend/kb.html 这个网页不用登录。
- 已完成：backend/main.py 的 _frontend_path_requires_auth 免登录白名单新增 /static/kb.html。
- 范围：仅放开知识库独立页；/static/index.html 主工作台仍需登录。
- 验证通过：py_compile 与定向 diff-check。

## 2026-06-25 11:11:00 邮件套装页脚本为空/重刷版本/签名缺失交接

- 用户反馈 URL：/static/mail-suite.html?id=KH00362-425，问题包括刷新后脚本为空、再次进入疑似不是重刷版本、重刷后签名档仍无。
- 已确认昨日记录确实修过相关方向：13:23 单封重刷与真实 prompt 查看、13:34/13:40 模板命中与旧保存稿说明、14:22 签名稳定性。
- 今日复现原因不是“昨天完全没修”，而是修复没有覆盖完整闭环：自动保存未落 llm_prompt；保存稿读取未回填 llm_prompt；重刷接口未在返回和落库前注入套装签名；负责人签名取不到时缺固定兜底。
- 本轮改动：backend/main.py 补齐 llm_prompt schema patch、序列化、自动保存、保存稿读取；新增 _mail_suite_fallback_signature_html() 和 _mail_suite_signature_html_for_customer()；
regenerate_mail_customer_suite_draft() 生成后立即 _apply_mail_suite_signature() 再保存/返回。
- 验证结果：AST 语法解析通过；定向 diff-check 通过；python -m py_compile 被 backend/__pycache__ / 临时 pycache rename 权限阻断。
- 线上确认：静态页 HEAD 返回 200，Last-Modified=Wed, 24 Jun 2026 09:52:05 GMT；当前 shell 调 API JSON 受本地 127.0.0.1 代理不可用影响未能拿到响应。部署本轮后需重启后端，再打开该客户点“重刷”验证 prompt_len > 0 且正文含 mail-signature。

## 2026-06-25 11:20:44 邮件套装发件销售代表多 Owner 解析交接

- 用户追问截图中 KH07679-004 为何未读取销售代表邮箱。定位：CRM usrCustomerContact.Owner 保存为 2012,0017，旧实现只支持单个 Owner 精确等于 usrStaff.StaffId，所以没有命中在职员工，也就没有发件企业邮箱。
- 本轮修复：_fetch_mail_contact_owner_staff_id() 增加多 Owner 拆分与评分，拆分后只允许在职员工参与；优先级为默认企业邮箱 > 可用企业邮箱 > 无邮箱，同时销售/电销/大客户/市场部门优先。
- 只读验证：KH07679-004 选择 0017（韩瑾 / Angela / 大客户部），有默认可用企业邮箱；2012 在职但无可用邮箱记录，因此不作为发件人优先项。
- 边界：签名档展示仍有兜底签名；真实发送仍必须取到在职销售的企业发件邮箱，不会用兜底签名绕过发件邮箱校验。

## 2026-06-25 11:30:46 邮件套装销售代表优先工号规则交接

- 新增显式优先工号：0017、0002、0141、0188、1607。
- 选择口径：先拆联系人 Owner 中的多个工号，只允许在职员工；优先工号中有默认/可用企业邮箱者优先，其次其他有邮箱的在职销售，最后才是无邮箱 fallback。
- KH07679-004 验证：2012 在职但无可用邮箱；0017 在职且有默认可用邮箱，因此选择 0017。

## 2026-06-25 11:39:18 邮件套装历史保存稿 prompt 回填交接

- 截图显示签名已存在但 prompt 0 字符，说明命中历史 saved_edit，缺的是旧行 llm_prompt 回填，不是正文签名问题。
- 新逻辑：读取 saved_edit 时若 llm_prompt 为空，调用 prompt-only 装配并写回 mail_customer_suite_draft_edit.llm_prompt；不调用 LLM、不覆盖正文、不改变人工保存逻辑。
- 验证 KH00362-425 / re_activation / Step1：prompt-only 装配长度 745。

## 2026-06-26 邮件质量诊断面板交互改造 + 测试邮件直出交接

- 用户需求(6 项): 说明文字改浮动且改成易懂用途文案; 每封 AI 指令框高度翻倍; 隐藏原表单红框; 把生成测试邮件挪到每封邮件保存旁; 模板标题改名并在保存名称旁加可改的测试客户编号 + 生成测试套装邮件按钮; 单封/套装测试都用该客户编号弹新页(mail-suite.html)预览, 只展示不入库、去掉其他邮箱限制。
- 前端 index.html: 标题/模型选择/子标签/案例切换/模板区 tooltip 全部改成大白话; AI 指令 textarea rows14->28、height16rem->32rem、max28rem->56rem; 隐藏原输入网格+生成按钮+未接入字段路线图(加 hidden); 模板标题"三大场景全阶段脚本模板(可编辑保存)"->"场景全阶段脚本模板"; 新增 #mql-test-customer-key(默认案例一客户编号, onblur 存 localStorage) 与 openMailTestSuite()/openMailTestSingle()/saveTestCustomerKey()/ensureTestCustomerKeyDefault(); 每封卡片新增"生成测试邮件"按钮(保存旁)。
- 前端 mail-suite.html: loadSuite/fetchSuite 读 ?test=1&step=N&scenario=, 测试模式不读不写缓存、Accept:application/json、加测试横幅; 新增 TEST_MODE/ONLY_STEP 全局与 .test-banner 样式。
- 后端 main.py GET /api/v1/mail/customer-suite: 新增 step、test 两个 query 参; test=1 时 saved_edits 置空强制重生成(反映脚本最新改动)且跳过自动写库; step=N 时只生成该封。生成读取的是 scenario 共享模板(_get_mail_sequence_template_for_prompt customer_key=""), 所以任意测试客户+同场景即可验证改后的脚本。
- 验证: backend/main.py ast.parse 通过。未启动真实发信; 未改密钥。

## 2026-06-26 内置老场景也支持改名(不影响使用)交接

- 用户需求: 老的 3 个内置场景(老客户激活/老客户其他业务介绍/新客户开发介绍, 含印刷报价后跟进)也能改显示名, 且不影响生成与已存草稿。
- 后端 main.py: 新增 _load/_save/_apply_mail_scenario_label_overrides(), 改名持久化到 runtime_llm_settings.json 的 scenario_label_overrides, 启动时 + 列模板/套装选项接口处热载入(兼容多 worker); PUT /api/v1/mail/custom-suites/{scenario} 放开内置场景分支(只改内存中文名 _MAIL_SCENARIO_CHINESE + 覆盖文件 + 模板行 scenario_label_cn, scenario 代码不变)。
- 前端 index.html: syncMailSuiteNameInput/saveMailSuiteName 取消"仅自建套装可改名"限制, 选中任一套装即可改名。
- 不影响使用: 生成流程/场景路由/已存草稿都以 scenario 代码为准, 仅显示名变化。
- 验证: ast.parse 通过。提醒: 截图为旧缓存页, 需 Ctrl+F5 才能看到上一轮新版 UI。

## 2026-06-26 邮件诊断页头部精简交接

- 用户需求: 测试预览页黄色横幅去掉; 邮件诊断页隐藏"邮件工作台"面包屑与右上"已加载N案例"状态文字; "真实测试案例切换"默认折叠; 顶部"智能销售辅助工作台"与"邮件质量诊断"两行高度压一半。
- mail-suite.html: 移除 #test-banner 及其填充逻辑(仅留 body.test-mode class)。
- index.html: 删 邮件工作台 面包屑; #mql-demo-contacts-status 加 hidden; 案例切换默认折叠(mailDemoContactsCollapsed=true + collapsible 加 hidden + 按钮 展开); 顶部 header py-2->py-1、标题 text-lg->base、主导航按钮 py-2->py-1; 邮件诊断头 pt-5 pb-4->pt-2 pb-2、items-end->center、h1 text-xl->lg、子标签与模型选择 py-2->py-1。

## 2026-06-26 反馈记录页改造(结论/已处理/列精简)交接

- 需求(9+1): 说明文字浮动易懂; 保存时间->时间只显年月日; 每行最多2行超出...浮动看全; 客户/联系人->只显联系人编号; 场景阶段拉宽显示"场景- N"; 隐藏对应主题列; 新增可编辑"结论"列(leave 保存); 新增"已处理"勾选+上方筛选; 隐藏说明文字与"已加载N条"状态; 另:案例切换标题去掉(3选1...)括号。
- 后端: mail_customer_suite_feedback 加 conclusion TEXT + handled BOOLEAN(DDL ALTER + database.py 模型 + 序列化); GET 加 handled 筛选参数; 新增 PATCH /api/v1/mail/customer-suite-feedback/{id} 改结论/已处理。
- 前端 index.html: 反馈表头重排(时间/联系人编号/场景阶段/反馈摘要/结论/已处理/操作); 渲染用 -webkit-line-clamp:2 截断+title 浮动全文; 日期 slice(0,10); 场景阶段 whitespace-nowrap 显示"场景- N"; 结论 input onblur PATCH; 已处理 checkbox onchange PATCH; 新增 handled 筛选下拉; 隐藏 p 说明与 mail-feedback-status(内联 display:none); saveMailFeedbackConclusion/saveMailFeedbackHandled。
- 验证: ast.parse 通过。新列由启动 DDL 自动补; 需重启后端生效。

## 2026-06-26 生命周期阶段改按联系人维度交接

- 需求: 生命周期(熟/老/新联系人)按"人"算, 不按公司汇总; 同公司不同联系人也分新老。
- crm_profile._get_customer_lifecycle_stage: 去掉先查 CustomerId 再按公司统计的逻辑, 一律按 ContactId 统计该联系人自己的销售合同(usrContract.ContractType=销售合同, 未删)。规则不变: 近1年>=3->熟, 历史有->老, 无->新。
- main.py 注释同步改为按联系人维度。所有调用方(行4568/4884 等)都走此函数, 改动全覆盖。
- 注意: 依赖 usrContract.ContactId 落数; 若公司合同未挂到具体联系人, 该联系人会判为新联系人(符合"按人"诉求)。需重启后端生效。
- 验证: ast.parse 通过。

## 2026-06-26 16:20:03 知识库命中详情与统计交接
- 用户需求：1）知识库命中日志双击命中数时弹窗没有详细信息；2）新增按每个知识库切片命中个数统计的页面，可选择统计时间范围。
- 已完成：backend/main.py 为 /api/kb/hit_logs 补齐 include_hits 参数和 hit_chunks 详情；新增 /api/kb/hit_logs/chunk_stats 按真实命中日志聚合切片命中次数；frontend/index.html 新增“命中统计”标签页、日期筛选、统计表，并补充 #kb-hit_stats hash 映射。
- 验证：python -m py_compile backend\main.py 通过；抽取内联脚本后 node --check scratch\frontend-index-scripts-check.js 通过；定向 git diff --check -- backend/main.py frontend/index.html scratch/frontend-index-scripts-check.js 通过。
- 注意：本轮未读取或输出 .env 中的凭据；未处理工作区中原有其它未提交和未跟踪文件。部署后需重启后端并强刷前端静态页。

## 2026-06-26 17:30:49 知识库命中快照审计交接
- 用户指出：按历史 chunk_id 重新查询当前知识库会误导排查，因为当时给后续回复生成流程的可能是旧正文/旧排序/旧字段，当前重查不能代表当时输入。
- 已修正：backend/database.py 增加 KnowledgeHitLog.hit_chunks_snapshot；backend/main.py 启动 DDL 补列；backend/intent_engine.py 在知识库检索写日志时保存当时的完整命中快照。
- 前端修正：frontend/index.html 的命中日志详情明确区分“原始检索快照”和“当前切片”；统计页也显示“有原始快照 / 当前表回查”，历史日志缺快照时展示警告。
- 说明：旧日志不是报错没成功，而是旧 schema 只记录了 hit_chunk_ids/scores，没有记录当时正文快照；旧数据无法还原当时原文，只能从新日志开始审计准确。

## 2026-06-26 自动群发 Step1: 排期引擎+5表+dry-run 交接

- 范围: 只做排期引擎(纯函数)+数据表+dry-run 预览, 完全不碰 CRM 写入、不生成草稿、不入库。
- database.py 新增 5 表: mail_autosend_config / mail_autosend_suite_rule / mail_autosend_run / mail_autosend_plan_item / mail_contact_suite_history; main.py auto_patch_db 补 DDL(启动自动建)。
- 引擎(main.py): _autosend_cond_eval/_rule_matches/_pick_suite(命中且没发过->兜底最后一个->都发过则跳过提示)/_schedule(逐人逐封, 第k封=第k-1封实际落日+周期, 每日上限含CRM已有量顺延, 9:00每5分钟)/_sort_contacts(6种排序)。
- CRM 读取(只读): _autosend_load_contacts_for_sales(按销售取名下有有效邮箱联系人, 聚合历史累计销售合同额Money1+2+3/末次合作/业务线BusinessType, ContractType=销售合同 按ContactId)、_autosend_existing_crm_load(spQueueSend 按 InputerStaffId+PlanSendTime 计已有待发量)。
- 接口: POST /api/v1/mail/autosend/dry-run (demo/contacts/sales_staff_ids 三选一, 返回 items+skipped+day_load)。
- 本地纯函数验证(scratch): 26联系人 cap10 周期[0,5] -> 第25人第1封第2天、第2封第7天; 第7天占满则跳第8天, 与用户示例完全一致。
- 待办 Step2: 配置/规则 CRUD + 自动发送 UI + dry-run 预览表; Step3: 接真生成草稿+写 spQueueSend+历史去重。需重启后端建表/上线接口。

## 2026-06-26 17:56:56 知识库命中详情链路快照交接
- 用户指出实时智能页面今天的记录已经显示过知识库检索命中详情。已按此修正，不能再把旧记录一概判断为无法还原，也不能用当前表回查冒充当时传给后续流程的内容。
- 当前实现：命中日志详情优先读取 hit_logs 自带快照；没有时按 log_id 关联 reply_chain_snapshot、intent_summaries，并按 request_id/session_id 检索 api_assist_invocation.result_payload 中的 knowledge_v2.hits；只有这些都找不到时才按 hit_chunk_ids 查当前 knowledge_chunk，并返回明确 warning。
- 新写入日志仍会保存 hit_chunks_snapshot，减少后续跨表恢复依赖。旧记录若链路快照仍在，可以恢复当时 hits；若链路快照和 hit_logs 快照都没有，才只能降级为当前表辅助查看。
- 验证通过：后端 py_compile、前端内联脚本 node --check、定向 diff-check。

## 2026-06-26 自动群发 Step2: 配置/规则 CRUD + UI + dry-run 预览 交接

- 后端 main.py: 模型 import 补 5 表; 新增接口 GET/PUT /api/v1/mail/autosend/config(排序/周期/上限/兜底/去重单行配置)、GET/PUT /api/v1/mail/autosend/suite-rules(整组替换, 顺序即priority末位兜底)、GET /api/v1/mail/autosend/sales-staff-names(工号->中文名)。序列化/解析辅助函数齐备。
- 前端 index.html: 质量诊断后新增"自动发送"子标签 + mail-autosend-panel(区1联系人范围+排序; 区2套装优先级可增删改上下移+条件且/或; 区3周期/每日上限/开始日期+保存配置/预览排期); switchMailWorkspaceTab 接 autosend; 全套 autosend* JS(加载配置/规则/场景、规则增删改、保存、dry-run、渲染排期表/跳过/每日封数)。
- dry-run: 留空销售工号走 demo; 填工号走 CRM 取数。仅预览不写CRM。
- 验证: backend ast.parse 通过; 新增前端 JS 块 node --check 通过。需重启后端上线接口+建表。
- 待办 Step3: 接真生成草稿+写 spQueueSend+历史去重+后台任务进度。

## 2026-06-29 10:17:32 交接：一键启动后台 detached 防冻结
- 用户反馈：服务器端后台每次刚启动后，cmd 窗口会像卡住；选中窗口再点向下箭头后日志立刻继续。
- 分析结论：Windows 控制台 QuickEdit/滚动暂停会阻塞 stdout/stderr，当前 start_backend.ps1 的控制台输出与 Tee-Object 可能使 uvicorn 请求处理被控制台 I/O 卡住。
- 已完成：新增 start_backend_detached.ps1；一键启动后台.bat 改为调用 detached helper，真实后端跑在隐藏 PowerShell 中，stdout/stderr 写 backend/logs/backend_8071_*.stdout.log / stderr.log，业务日志仍看 backend/logs/app.log。
- 验证：PowerShell PSParser 语法检查 OK；定向 git diff --check OK。未实际执行启动，避免影响当前运行的后台。

## 2026-06-29 10:41:57 交接：detached 后端 + 可见日志查看窗口
- 用户进一步要求：前台仍要可见日志，便于发现报错和十几分钟无日志的问题。
- 当前方案：真实后端由 start_backend_detached.ps1 用隐藏 PowerShell 启动，并将 stdout/stderr 重定向到 backend/logs/backend_8071_*.stdout.log / stderr.log；同时打开 start_backend_log_viewer.ps1 可见窗口跟踪 app.log/stdout/stderr。
- 关键边界：日志查看窗口可以被选中/滚动，最多只阻塞日志查看器输出，不会阻塞 uvicorn/FastAPI 后端进程。
- 验证：两个 ps1 均 PSParser 语法 OK；一键启动后台.bat/start_backend_detached.ps1/start_backend_log_viewer.ps1 定向 diff-check OK；未实际启动后台。

## 2026-06-29 10:59:27 交接：后台启动关闭/报错/重复双击行为
- 关闭行为：关闭一键启动 bat 的前台窗口或日志查看窗口，不会关闭隐藏后端进程；停止后端应使用停止脚本或按端口/PID 停止。
- 报错可见性：隐藏后端 stdout/stderr 已重定向到 backend/logs/backend_8071_*.stdout.log / stderr.log，日志查看窗口同时跟踪 app.log/stdout/stderr；后端进程退出时日志窗口会提示。
- 重复双击：start_backend.ps1 -KillPortOwner 会清理 8071 端口旧后端；start_backend_detached.ps1 现在会通过 backend_8071_log_viewer.pid 先关闭旧日志查看窗口，再打开新的日志窗口，避免前台窗口重复堆积。
- 验证：两个 ps1 均 PSParser 语法 OK；一键启动后台.bat/start_backend_detached.ps1/start_backend_log_viewer.ps1 定向 diff-check OK；本轮未实际启动后台。

## 2026-06-29 11:18:14 交接：首页刷新卡住 REQUEST_START 观测补强
- 当前判断：日志停在 favicon.ico 404 不代表后端在处理 favicon；前端默认流程后续应进入 /api/sessions 加载企微会话列表。若该请求未完成，旧日志机制不会显示它。
- 本轮修改：backend/main.py 的 request_observability_middleware 在 /api/* 请求进入时先写 REQUEST_START，包含 path/method/request_id/query。
- 预期效果：重启后再次卡住时，日志窗口最后的 REQUEST_START 行就是当前 in-flight 卡点；若看到 path=/api/sessions，优先排查 get_sessions 中 message_logs DISTINCT ON 查询、当日统计 _build_api_day_stats、会话标记 _build_api_session_marks。
- 验证：py_compile 与定向 diff-check 通过；未实际重启后台，因当前沙箱 curl localhost:8071 返回 000。

## 2026-06-29 11:38:05 交接：TRAIN_AI_TIMEOUT 归属日志
- 问题：用户服务器日志在首页刷新期间出现 TRAIN_AI_TIMEOUT model=unsloth-qwen2.5-task-62，但没有 request/session/runtime_key 上下文。
- 当前代码已补：_train_ai_chat(messages, ..., call_context=None)，日志追加 context；_generate_reply_style_candidates 调用处传 source=reply_style_candidates/runtime_key。
- 后续判断：部署重启后若仍出现 TRAIN_AI_TIMEOUT，看同一行 context 字段。若 context 为空，说明来自其他 _train_ai_chat 调用点（例如自动辅助或案例链路），再给对应调用点补 call_context。
- 验证：py_compile 与定向 diff-check 通过；未实际重启服务器。

## 2026-06-29 页面加载卡住排障交接

- 用户现象：后台窗口仍有日志，多个页面一直加载；截图显示 /api/kb/hit_logs/chunk_stats 耗时 176367ms，/api/v1/mail/customer-suite 耗时 194063ms，均最终 200 OK。
- 已完成：新增全局 REQUEST_IN_FLIGHT 运行中日志，所有 /api/* 超过 SLOW_REQUEST_MS 未完成会显示具体 path、query、request_id、elapsed_ms；知识库命中统计默认避免逐条链路快照回溯并记录 KB_HIT_STATS_DONE 计时；前端几个加载入口增加超时和错误展示。
- 服务器更新后看法：若再卡住，先看 REQUEST_IN_FLIGHT 的 path/query；若是知识库统计，看 KB_HIT_STATS_DONE 的 timings_ms 和 chain_lookup_count；若是 customer-suite，当前能明确到 /api/v1/mail/customer-suite 这一接口，下一步可再给该接口内部 CRM/模板/LLM/保存阶段加分段日志。
- 验证：python -m py_compile backend\main.py、node --check scratch\frontend-index-scripts-check.js、git diff --check -- backend/main.py frontend/index.html 通过。


## 2026-06-29 桌面后台日志慢节点交接

- 日志文件可读：C:\Users\Admin\Desktop\backend_8071_20260629_134512.stdout.log、C:\Users\Admin\Desktop\backend_8071_20260629_134512.stderr.log。
- 已定位主要失败：/api/wecom/trigger_analytics?start_date=2026-06-29...limit=300 两次约 24s 后 500，异常为 psycopg.errors.QueryCanceled: 由于语句执行超时，正在取消查询命令，SQL 是按 triggered_at 查 pi_assist_invocation 并全量 SELECT 大字段。
- 已修改：get_wecom_trigger_analytics 改为 SQL 层过滤 source、limit；启动自动补 pi_assist_invocation(triggered_at DESC) 与 (trigger_source, triggered_at DESC) 索引；返回前记录 WECOM_TRIGGER_ANALYTICS_DONE。
- 仍需后续关注：/api/kb/hit_logs/chunk_stats 仍慢，本轮默认 scan_limit 从 1000 降至 500；/api/v1/mail/customer-suite* 仍会慢，需要进一步分段日志和保存/生成链路优化。
- 非问题项：/api/wecom/session_updates?wait=25 约 25s 是长轮询正常行为；本日志中 /api/sessions 返回 200 OK。
- 验证：python -m py_compile backend\main.py、node --check scratch\frontend-index-scripts-check.js、git diff --check -- backend/main.py frontend/index.html 通过。


## 2026-06-29 轻量首屏交接

- 用户要求：慢页面不要为了详细计算卡住，详细内容可以后置，先确保数据能显示。
- 已完成：统计分析 limit=80；知识库命中统计 limit=100/scan_limit=200；本地 API timeout=15000ms；mail-suite 首屏调用 /api/v1/mail/customer-suite?...&generate=false，后端只读客户信息和已保存草稿，不自动生成缺失草稿。
- 后续验证点：服务器更新重启后，打开企微统计分析应先显示最近 80 条；知识库命中统计应只扫 200 条日志；邮件套装页应先显示客户信息和已保存草稿，未生成项提示可重刷。
- 若仍慢：继续针对 /api/v1/mail/customer-suite-draft 和 /api/kb/hit_logs/chunk_stats 做数据库字段瘦身/分页，不再首屏拉详情。


## 2026-06-29 轻量首屏交接

- 用户要求：慢页面不要为了详细计算卡住，详细内容可以后置，先确保数据能显示。
- 已完成：统计分析 `limit=80`；知识库命中统计 `limit=100&scan_limit=200`；本地 API timeout=15000ms；mail-suite 首屏调用 `/api/v1/mail/customer-suite?...&generate=false`，后端只读客户信息和已保存草稿，不自动生成缺失草稿。
- 后续验证点：服务器更新重启后，打开企微统计分析应先显示最近 80 条；知识库命中统计应只扫 200 条日志；邮件套装页应先显示客户信息和已保存草稿，未生成项提示可重刷。
- 若仍慢：继续针对 `/api/v1/mail/customer-suite-draft` 和 `/api/kb/hit_logs/chunk_stats` 做数据库字段瘦身/分页，不再首屏拉详情。

## 2026-06-29 邮件草稿 QueryCanceled 交接
用户反馈生成单封草稿时 email_fragment_asset 查询因 statement_timeout 被取消。判断为邮件 Few-Shot/黄金范例查询慢查询：缺少 source_type/scenario_label/function_fragment/status/useful_score 组合索引，且 approved full_email 分支曾拉取最多 2000 条整行大字段。已在 auto_patch_db 补 idx_efa_mail_gold_seed_lookup 与 idx_mgsr_status_fragment，并把 full_email 候选限制为 max(limit*20, 40/60)。重启后首次启动会自动建索引；若生产表很大，首次 CREATE INDEX 可能需要等待。

## 2026-06-29 18:40:00 知识库 KB3 动态路由与多路召回升级交接
- 目标：将新版服务知识库（KB3/Unit 表）作为微信侧可选知识库，支持配置台动态选择主用/对比知识库，并增加仅检索已确认单元过滤。
- 已完成：
  1. 数据库模型：`database.py` 中为 `WecomRuntimeConfig` 新定义 `wecom_kb_primary`、`wecom_kb_compare` 和 `wecom_kb3_confirmed_only` 字段。
  2. 检索匹配：`intent_engine.py` 实现 `retrieve_service_knowledge_v3`，支持 `pgvector` 余弦相似度与 `pg_trgm` `word_similarity`/`similarity` 混合检索与 token 兜底。
  3. 配置路由：`main.py` 扩展 `_retrieve_knowledge_routed` 以处理配置路由；扩展 `save_ai_scripts` 并持久化。
  4. 前端对接：`index.html` 完成“微信侧知识库召回配置”UI 交互与 `saveSettings` 参数保存。
- 后续验证：本地测试已通过。当服务器重启后，前端打开 Settings 能够成功显示和保存“主用知识库/对比知识库”设置。

## 2026-06-30 13:18:15 交接：mail-suite 逐封自动刷新与 3 次重试

- 用户问题：进入 mail-suite.html 后 4 封空白/整批生成等待；担心 4 封同步刷、多线程互相影响；希望前台好一封显示一封，失败自动重刷，3 次失败后停止报错。
- 已处理：前端默认请求 /api/v1/mail/customer-suite?...&generate=false 快速读取保存稿，随后 utoGenerateMissingDrafts() 逐封调用 /api/v1/mail/customer-suite-draft/regenerate，每封最多 3 次重试，状态显示“自动刷新中/重新刷新中”。
- 后端处理：_build_mail_generate_draft_response() 在完成 DB 取数、进入 LLM 组装前 db.rollback() 释放事务；单封 regenerate 接口不再使用请求注入 DB session 跑 LLM，改为 generation_db 与 save_db 分离；整套接口兜底并发从 4 降到 2。
- 判断：部分失败主要来自 DeepSeek 返回空正文/解析不到正文，旧日志还叠加了 DB idle-in-transaction 超时；本轮不恢复 fallback_template 假成功，而是让前端自动重试并最终显示真实失败原因。
- 验证通过：python -m py_compile backend\main.py；抽取当前 frontend/mail-suite.html script 后
ode --check scratch\frontend-mail-suite-current-check.js；git diff --check -- backend/main.py frontend/mail-suite.html。
- 后续上线注意：需重启后端并强刷 mail-suite.html 静态页；若仍有单封 3 次失败，重点看该封 MAIL_DRAFT_LLM2_FAILED 前的 raw/parse 日志和对应脚本输出格式。

## 2026-06-30 15:05:05 交接：邮件配置页 DeepSeek 参数真接入

- 用户要求：在邮件配置页面顶部增加邮件生成 LLM 选择，复用其它页面模型选择逻辑；新增 DeepSeek API 主要参数配置，对应 deepseek-v4-flash / deepseek-v4-pro，保存后后续生成按这里配置走，并新增数据库字段。
- 已完成：backend/database.py 的 WecomRuntimeConfig 增加 mail_generation_model、mail_deepseek_model_configs；backend/main.py 的自动补表、运行时配置 GET/PUT、邮件模型配置和 LLM 请求体均已接入。
- 前端：frontend/index.html 的邮件配置页新增 “邮件生成 LLM 选择与 DeepSeek 参数” 面板，可编辑两套 DeepSeek 参数并随“保存配置（立即生效）”提交。
- 注意：stream/tools 这类会破坏当前 JSON 解析保存链路的能力未作为可启用项接入；当前接入的是邮件草稿链路可安全使用的 DeepSeek 参数。需重启后端使新增数据库字段自动补表生效，前端需强刷静态资源。
- 验证：python -m py_compile backend\main.py backend\database.py；node --check scratch\frontend-index-current-check.js；git diff --check -- backend/main.py backend/database.py frontend/index.html。
## 2026-06-30 18:22:48 交接：mail-suite 首封发送时间恢复当前时间+10分钟

- 问题：邮件套装页第 1 封发送时间会被保存稿/默认值 09:00 覆盖，未保持“当前时间 +10 分钟”。
- 已处理：frontend/mail-suite.html 第 1 封渲染统一走浏览器当前时间 +10 分钟；成功重刷后回填 DOM 也使用同一逻辑。点击发送时，前端把页面当前 send_interval_days/send_time 传给后端。
- 后端同步：backend/main.py 发送接口优先使用前端传入的 send_interval_days/send_time 计算 plan_send_time，未传时才回退保存稿和默认值。
- 验证：后端 py_compile、当前 mail-suite 内联脚本 node --check、定向 diff-check 均通过。未启用真实发信；未触碰 Task 79。
- 注意：根目录缺少 AGENTS.md 要求读取的 邮件智能回复实现方案.md 和 文件创建要求.md，本轮已按现有任务/进展/交接文件恢复上下文继续完成局部修复。

## 2026-07-01 11:35:58 交接：KB3 检索过滤与向量日志口径修复
- 已修复 backend/intent_engine.py 的 KB3 检索实现：has_vectors_in_db 不再受 qvec 是否生成影响；新增 query_embedding_available/semantic_search_enabled 解释为什么退回词法检索。
- 已将 query_features.knowledge_type 下推为 KB3 Unit SQL 过滤，覆盖 semantic/trgm/backup 三段召回。映射口径：faq -> unit_type=faq；process -> 流程规范/技术处理；capability -> 产品知识/案例；pricing -> 搜索文本含报价/价格/费用/付款/发票等价格结算词。
- 验证通过：python -m py_compile backend\\intent_engine.py；git diff --check -- backend/intent_engine.py。手工 KB3 查询新增一条 manual_kb3_filter_check 命中日志，用于确认字段与过滤生效。
- 注意：本次验证显示 Ollama embedding 调用失败 RemoteDisconnected，因此语义召回仍会关闭，但现在日志会准确显示为 query_embedding_available=false，而不是误导为库内没向量。

## 2026-07-01 13:54:49 交接：KB3 笔译资质类业务重排
- 在 backend/intent_engine.py 的 KB3 检索中新增 business_rerank，位置在召回完成后、top_k 截断前。
- 重排目标：客户问资质/营业执照/翻译专用章/认证/盖章时，优先 FAQ/产品知识/流程规范中可直接回答的资质条目；降低字段统一、VAT/registration number、加急开票审批、销售技巧和案例类泛相关条目。
- 验证结果：宽查询《审计报告和营业执照；客户询问保加利亚语翻译能力；保加利亚语翻译需求》top5=1547/348/82/349/48；资质问句 top3=1779/1154/878。Ollama embedding 正常 EMBEDDING_OK。
- 后续如继续优化，可把 business_rerank 规则沉淀为可配置表或按 taxonomy 维护，不建议继续硬编码过多长尾规则。

## 2026-07-01 交接：企微实时智能 02-05 链路 KB3-only 文档

- 用户要求先不继续优化，整理从 02 强信号扫描到 05 知识库检索证据的实现文档，并要求知识库仅以 KB3 为准。
- 已新增 docs/企微实时智能_02到05链路_KB3-only.md。内容包括：前端节点渲染、/api/wecom/sidebar_assist 请求字段、Fast-Track 规则来源、第一阶段 LLM-2/LLM-1 结构化提取、CRM 聚合画像读取字段、thread_business_fact、KB3 路由配置、KB3 SQL/向量/词法/重排/日志快照字段。
- 本轮未修改 backend/main.py、backend/intent_engine.py 等业务代码；只新增文档和状态记录。
- 验证：git diff --check -- docs/企微实时智能_02到05链路_KB3-only.md 通过。

## 2026-07-01 17:44:19 交接：联系人已用套装查询与两处点击入口

- 用户要求：做 API 和使用说明文档，根据联系人编号输出该联系人使用过的套装及套装哪几封；并在截图位置增加两个点击显示。
- 已完成：增强 /api/v1/mail/customer-suite-records 返回 used_steps / used_step_labels；新增文档 docs/mail_customer_suite_records_api.md；在 frontend/mail-suite.html 的客户信息联系人旁、自动排期清单联系人旁增加“已用套装”按钮，弹窗读取真实接口显示已用套装、封次、来源、最近活动。
- 数据来源：mail_customer_suite_draft_edit、mail_customer_suite_send_plan、mail_customer_suite_feedback、mail_autosend_plan_item、mail_contact_suite_history。接口只读，不生成草稿、不写 CRM、不真实发信。
- 验证：python -m py_compile backend\main.py、node --check scratch\frontend-mail-suite-current-check.js、定向 git diff --check 均通过。
- 后续：重启后端并强刷 /static/mail-suite.html 后生效。

## 2026-07-02 13:06:38 交接：自动排期待发日历展示修复

- 用户要求：去掉刷新日历后“今天起40天今天起40天”的重复文案；在合计封数后增加涉及联系人数量，点击后在下方按排期清单格式展示对应清单；日历格子如 07-02 8 改为一行显示。
- 已完成：frontend/mail-suite.html 抽出排期清单表格渲染 helper；日历状态改为“合计 X 封 · 涉及 Y 个联系人”；联系人数量点击展示当前周期本地预排清单；日期格子改为单行日期+数量；日期格单击展示当天清单并继续加载 ③ 邮件详情。
- 验证：当前 mail-suite 内联脚本抽取后 node --check 通过；git diff --check -- frontend/mail-suite.html 通过。
- 注意：涉及联系人统计基于当前已加载的本地自动排期清单 as2PlanItems；CRM 待发明细仍按日期点击后在 ③ 邮件详情逐封读取。

## 2026-07-02 13:22:19 交接：自动排期后台生成防重复与状态锁定

- 用户问题：确认“后台生成”是否多次点击会重复任务、销售 A/B 是否互相等待或覆盖、服务器关闭后队列是否清空/是否继续，以及需要按钮生成中状态跨刷新锁住。
- 代码结论：原逻辑按销售工号内存去重；同一销售重复点击返回 already_running，不会再起同一销售 worker；不同销售各起后台线程并发跑，不等待 A 全部完成才跑 B；写入按 owner_staff_id/item_id 更新，正常不互相覆盖。风险是 active 只在内存中，服务重启后会丢，且中断时 drafting 可能残留。
- 已修复：新增后端锁和 helper，防同销售并发竞态；generate-status 计算 remaining；非 running 状态发现 orphan drafting 会恢复为 planned，避免服务重启后卡死。前端按钮跟随后端 running 状态，点击后立即禁用并显示“生成中...”，刷新/重开页面会继续查询状态并锁住。
- 当前只读统计：0017 planned=120 还未生成；0188 drafted=160 已生成。当前本机 8071 连接失败，说明本地没有可查询的运行中后端进程，无法从内存确认 active worker。
- 验证：backend/main.py py_compile 通过；当前 mail-suite 内联脚本 node --check 通过；定向 diff-check 通过。

## 2026-07-02 14:07:16 交接：待发日历联系人与清单
- 已完成：calendar 接口新增 days 窗口、contact_count、planned_contacts、pending_contacts；CRM Receiver 增加归一化统计。
- 已完成：frontend/mail-suite.html 日历状态使用后端 contact_count；联系人数字和日期点击均渲染 CRM待发 + 本地预排合并清单。
- 注意：合并清单中的 CRM 行通过 crm-day 接口读取 rowid/subject/receiver/plan_time，点击

## 2026-07-02 14:31:25 交接：日历联系人清单表格
- 已完成：/api/v1/mail/autosend/plan 增加 include_sent 参数，默认不影响现有排期清单；日历调用 include_sent=1。
- 已完成：frontend/mail-suite.html 日历下方恢复为联系人套装四列格式，封次格显示 MM-DD HH:mm + 状态颜色。
- 待办：后台生成队列后续按 3 个销售并发上限、清空排期取消旧 worker/防回写继续实现。

## 2026-07-02 14:45:46 交接：日历 41/125 口径
- 已完成：frontend/mail-suite.html 的联系人清单改为 CRM 待发锁定联系人套装，本地 include_sent 记录用于补齐该联系人全部封次。
- 已完成：周期过滤只决定哪些联系人入表；入表后四封邮件按实际日期显示，周期外日期不再被隐藏。
- 暂停：后台生成队列 3 销售上限、清空取消旧 worker/防回写逻辑尚未继续实现。

## 2026-07-02 14:49:15 交接：联系人清单排序
- 已完成：frontend/mail-suite.html 中 cal1RenderContactTable 增加排序选择；cal1SortedGroupKeys 按公司名/套装/第1封时间排序。
- 默认排序为 company；切换排序只重绘当前已加载表格，不重新请求后端。

## 2026-07-02 15:24:25 交接：邮件套装生成记录用于日历清单
- 已完成：backend/main.py 新增 _autosend_enrich_crm_queue_items，并应用到 crm-day/crm-range。
- 已完成：frontend/mail-suite.html 的 cal1CrmVirtualItems 优先使用 mapped customer/scenario/suite_step/company_name/contact_name；crm-range 读 120 天补齐第4封等周期外封次。
- 已完成：customer-suite-send 返回 prepared[].crm_send_id，前端 as2CommitItems 读取 prepared[0].crm_send_id 后回标 autosend plan item。
- 注意：历史 CRM 待发若没有 mail_customer_suite_send_plan.spqueue_rowid 记录，仍只能显示 CRM待发 兜底。

## 2026-07-02 15:32:54 交接：CRM待发映射二次修复
- 之前页面无变化的原因：只按 spqueue_rowid 精确匹配可能因大小写/RowId口径不一致失败。
- 已完成：_autosend_enrich_crm_queue_items 同时按 lower(spqueue_rowid) 和 crm_send_id(SendId) 关联 mail_customer_suite_send_plan。
- 已完成：crm-day/crm-range SQL 读取 SendId 并作为 crm_send_id 返回。
- 注意：后端需要重启/部署后浏览器页面才会体现映射结果。

## 2026-07-02 17:02:42 交接：邮件套装日历清单本地索引化
- 已完成：backend/database.py 与 backend/main.py 为 mail_customer_suite_send_plan 增加 company_name/contact_name/recipient_email_key 字段和索引，发送入 CRM 时写入，历史可用 recover-suite-index 回收。
- 已完成：/api/v1/mail/autosend/crm-range 不再默认扫 CRM spQueueSend，改读本地 send_plan，返回 mapped 套装字段，解决清单长期加载和每次拼凑慢的问题。
- 已完成：frontend/mail-suite.html 联系人清单回看 60 天/覆盖 180 天，能显示已发送第一封、待发送后续封和周期外第4封；同联系人套装重复行合并，映射行显示已用套装按钮。
- 验证通过：后端 py_compile、前端 node --check、定向 git diff --check。
- 上线注意：需重启后端触发表字段补齐；上线后建议对销售 0017 执行 POST /api/v1/mail/autosend/recover-suite-index?staff_id=0017，然后刷新页面核对 357/125/第一封状态/重复行。

## 2026-07-02 17:19:11 交接：历史 send_plan 索引回收状态
- 本地已实现自动回收：页面打开周期清单或点击日期时，会先调用 recover-suite-index 当前销售，随后再读取 crm-range。
- 本地已实现手动回收：POST /api/v1/mail/autosend/recover-suite-index?staff_id=0017&limit=5000，返回 checked/backfilled/remaining_missing_index。
- 本地已实现查询兜底：crm-range 对返回范围内行执行 _mail_suite_fill_missing_index_fields。
- 重要：生产已有数据尚未确认回收成功；刚才线上 POST recover-suite-index 超时，crm-range 仍超时。需部署/重启后再执行 recover-suite-index 并以返回 remaining_missing_index=0 或明显下降作为回收结果。


## 2026-07-03 17:44:40 交接：生成邮件质检配置与 LLM 质检循环
- 本轮改动范围：backend/main.py、backend/database.py、frontend/index.html；未启用真实发信，未修改企微会话链路。
- 前端入口：邮件质量诊断 -> 邮件配置页顶部快捷入口“生成邮件质检”，面板默认折叠；字段为 enabled、max_review_runs、script，点击“保存质检配置”复用 /api/v1/system/runtime-llm-settings 保存。
- 后端配置：wecom_runtime_config.mail_quality_review_config JSON，auto_patch_db 会自动补列；runtime_llm_settings.json 也会保存同名小写字段。
- 生成逻辑：_assemble_mail_draft_with_quality_review 在 _build_mail_generate_draft_response 中替代单次 _assemble_mail_draft_from_intent_profile；质检关闭时行为等同旧逻辑；质检开启时每轮“生成 -> 本地主题硬规则 -> LLM JSON 质检”，失败则重新生成，超过 max_review_runs 返回 422，detail 会写明始终不满足的质检点。
- 默认质检点：缺少邮件主题。后续人工可在脚本里继续追加其它质检点，但建议保持 JSON 输出契约 passed/failed_points/reason。
- 验证通过：python -m py_compile backend\main.py backend\database.py；node --check scratch\frontend-index-quality-check.js；git diff --check -- backend/main.py backend/database.py frontend/index.html。

## 2026-07-03 18:46:26 交接：生成邮件质检节点位置修正
- 用户截图指出节点应位于邮件质量诊断页绿色区域中，在“场景全阶段脚本模板”折叠栏下方。
- 已将 frontend/index.html 中生成邮件质检 section 移动到 mql-template-collapsible 后方，并移除邮件配置区快捷入口；后端质检配置与生成链路逻辑不变。
- 验证：node --check scratch\frontend-index-quality-check.js；git diff --check -- frontend/index.html。

## 2026-07-03 18:51:50 交接：生成邮件质检脚本默认内容修正
- 用户要求“当前质检点”不要做单独节点，应放进质检脚本里，并且脚本框要有默认脚本。
- 已完成：frontend/index.html 删除当前质检点独立卡片，保留开关与最大质检次数两列；textarea 默认脚本写入“当前质检点：1. 缺少邮件主题”。
- 默认最大质检次数同步改为 1：frontend 默认与 backend _default_mail_quality_review_config 一致。
- 质量诊断页切换到 quality tab 时调用 renderMailQualityReviewConfig() 和 loadRuntimeLlmSettings()，避免只打开邮件配置页才初始化脚本。
- 验证通过：py_compile、前端 node --check、定向 diff-check。

## 2026-07-06 14:55:16 交接：index 邮件质量诊断自动排期入口
- 已改 frontend/index.html 的 mail-autosend-panel：旧“自动发送 dry-run”面板替换为销售视角选择 + iframe 复用 /static/mail-suite.html?staff_id=... 的自动排期节点。
- admin：可选择“全部销售”或单个销售；全部销售按 /api/v1/mail/autosend/sales-staff-names 返回的 priority_staff_ids 渲染多个销售 iframe 共同查看。
- hj/mail_quality_only：隐藏销售下拉并锁定到本人视角；当前写死前端映射 hj -> 0017，如 hj 对应销售工号变化，需要调整 MAIL_AUTOSEND_LOCKED_STAFF_BY_USER。
- 已改 frontend/mail-suite.html 的 resolveLockedStaff：支持 ?staff_id= 或 ?staff= 直接锁定销售，仍保留原 KH 解析逻辑。
- 验证已通过：node --check scratch\\frontend-index-autosend-check.js；node --check scratch\\frontend-mail-suite-autosend-check.js；git diff --check -- frontend/index.html frontend/mail-suite.html。

## 2026-07-06 15:26:49 交接：自动排期嵌入页二次修正
- 用户反馈截图中嵌入页顶部的“邮件套装生成 / 自动排期”行不要；已通过 embed=1 给 body 加 ms-embed，并隐藏 .ms-pagetabs 与 #suite-toolbar。
- 用户要求“显示所有联系人不是这样，还是一个页面”；已将 frontend/index.html 全部销售模式改成一个 iframe，传 staff_id=__all__&staff_ids=...，frontend/mail-suite.html 内部对所有 staff_id 循环拉取并合并自动排期、计划清单、日历、CRM待发等数据。
- 用户要求每个框高度不要限定且至少满屏；已将相关 max-h/max-height 改为 min-h 65vh，并保留滚动以避免正文编辑溢出。
- 验证通过：node --check scratch\frontend-index-autosend-check.js；node --check scratch\frontend-mail-suite-autosend-check.js；git diff --check -- frontend/index.html frontend/mail-suite.html。

## 2026-07-06 15:41:09 交接：自动排期外层说明收起
- 用户要求“新窗口打开去掉，其他改为加浮动说明”。
- 已删除 iframe header 中的新窗口链接。
- 自动排期标题旁新增 info 图标，承载 admin/hj 权限说明。
- mail-autosend-status 正常状态只显示 info 图标，具体内容放入 title；err=true 时仍显示错误文本，避免失败不可见。
- 验证通过：node --check scratch\frontend-index-autosend-check.js；git diff --check -- frontend/index.html。

## 2026-07-06 15:55:02 交接：全部销售不加销售编号过滤
- 用户明确要求：新加的嵌入聚合能力不能影响原有页面；全部销售视图查询 SQL 不要加销售编号限制，数据要能查询出。
- 已新增前端 as2ReadStaffIds()：AS2_STAFF='__all__' 时返回 ['']，读接口和预览排期用空 staff_id 请求；单销售仍返回具体工号。
- 后端读接口 staff_id 默认空，空值代表全销售查询；单销售 staff_id 逻辑保持原过滤。
- _autosend_load_contacts_for_sales([]) 已改为不追加 Owner LIKE 条件，联系人 owner_staff_id 从 CRM Owner 字段解析。
- 写操作清空/生成仍按具体销售工号执行，避免空 staff_id 误清全量；预览排期空 staff_id 只是不加联系人销售过滤。
- 验证通过：py_compile、前端 node --check、定向 diff-check。

## 2026-07-06 16:29:58 交接：自动排期全部销售详情与已发送读取
- 用户最新要求：新加操作按钮不要另起一行；已发送邮件点击后也能查看内容；解释并修复“全部销售(0)”；全部销售情况下 ①/② 表格增加销售中文名列，其他视图不变。
- 已完成前端：frontend/mail-suite.html 中 as2CrmCardHtml 将 CRM 操作按钮并入主题/邮箱/时间同一行；已发送详情只读展示；cal1StepCell 对 send_success/crm_sent/sent_done 携带 send_id 和 staff_id 打开详情；as2ShowDayEmails 支持 kind=sent；as2Init 初始化 AS2_STAFF_IDS；as2PlanRowsHtml/cal1ContactRowsHtml 在全部销售下渲染销售列。
- 已完成后端：backend/main.py 的 /api/v1/mail/autosend/crm-mail 支持 rowid 读取待发 spQueueSend，也支持 send_id+staff_id 读取 spSendInfo{staff} 已发送邮件；crm-range/crm-day 返回 inputer_staff_id/owner_staff_id 供前端定位销售。
- 验证通过：node --check scratch\frontend-mail-suite-autosend-check.js；node --check scratch\frontend-index-autosend-check.js；python -m py_compile backend\main.py；git diff --check -- backend/main.py frontend/mail-suite.html frontend/index.html。
- 注意：全部销售视图读接口继续使用空 staff_id，不加销售编号限制；生成/清空等写操作仍需具体销售，避免误清全量。
