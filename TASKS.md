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
- [ ] Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库

### P0：三大邮件场景与 4 轮 Sequence

- [ ] Task 19：落地老客户唤醒 `re_activation` 的 4 轮策略
- [ ] Task 20：落地新业务推广 `new_business_promotion` 的 4 轮策略
- [ ] Task 21：落地新接手联系人介绍 `new_contact_intro` 的 4 轮策略
- [ ] Task 22：定义 Sequence 状态枚举，如 `pending`、`drafted`、`approved`、`sent`、`replied`、`interrupted`、`blocked`
- [ ] Task 23：定义 Step 触发间隔，默认 Step1 当天生成，Step2 间隔 7 天，Step3 间隔 10 天，Step4 间隔 10 天
- [ ] Task 24：实现客户回复、CRM 状态变化、人工封印时的状态机物理切断规则
- [ ] Task 25：实现待发草稿销毁或锁定规则，避免已回复客户继续收到追问邮件

### P0：邮件草稿生成 API

- [ ] Task 26：设计并实现 `POST /api/v1/mail/generate-draft`
- [ ] Task 27：请求参数覆盖 `customer_key`、`contact_email`、`scenario`、`suite_step`、`current_seller_name`、`current_seller_signature`
- [ ] Task 28：响应参数覆盖 `mail_uid`、`final_subject`、`final_body_html`、`retrieved_fewshot_id`、`fewshot_match_score`、`safety_guardrail`
- [ ] Task 29：生成逻辑采用二阶段内容生成：先结构化意图/画像，再组装邮件草稿
- [ ] Task 30：邮件正文中的价格、工期、折扣、账期必须优先使用后端物理占位符填充
- [ ] Task 31：生成结果默认进入草稿和审核，不默认真实发送

### P0：Sequence 中断 API

- [ ] Task 32：设计并实现 `POST /api/v1/sequence/interrupt`
- [ ] Task 33：支持 CRM 状态变更触发中断，如 `CRM_STAGE_CHANGED_TO_WON`
- [ ] Task 34：支持销售手动强封印
- [ ] Task 35：支持按客户、域名、联系人维度中断
- [ ] Task 36：中断后返回被删除或锁定的待发草稿数量
- [ ] Task 37：中断事件写入邮件安全或操作日志

### P0：三重物理安全门

- [ ] Task 38：实现财务价格底线门，低于底价红牌硬拦截
- [ ] Task 39：实现价格正则提取，识别 RMB、元、USD、美元、per word、每千字、折扣等表达
- [ ] Task 40：实现履约工期 SLA 校准门，低于标准 SLA 时物理拉正并黄牌锁定
- [ ] Task 41：实现收件域名与抄送域名防泄密门
- [ ] Task 42：实现竞对域名黑名单与客户域名白名单
- [ ] Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本
- [ ] Task 44：实现红牌、黄牌、通过三种安全门结果结构
- [ ] Task 45：实现 20 个黑盒对抗测试用例，覆盖价格穿透、交期逼迫、同业钓鱼、占位符绕过

### P1：邮件质量诊断与人工纠偏面板

- [ ] Task 46：设计邮件质量诊断面板独立入口
- [ ] Task 47：展示草稿 ID、场景、Sequence Step、邮件主题
- [ ] Task 48：展示 SQL 粗筛、HTML 去噪、CRM 画像、RAG Few-Shot、安全门链路轨迹
- [ ] Task 49：展示 AI 生成版本与运营专家修正版双栏对比
- [ ] Task 50：支持专家编辑后保存为候选高质量切片
- [ ] Task 51：支持点赞、差评、拉黑 Few-Shot、保存并反哺
- [ ] Task 52：反哺进入黄金库前必须保留人工审核或赢单状态门槛，避免劣质销售习惯污染知识库

### P1：邮件配置管理台

- [ ] Task 53：设计邮件全局配置管理入口
- [ ] Task 54：支持 Sequence 多轮触发间隔配置
- [ ] Task 55：支持翻译产品线、印刷产品线底价配置
- [ ] Task 56：支持大客户加急工期最低阈值配置
- [ ] Task 57：支持 RAG 准入阈值与 LLM 温度配置
- [ ] Task 58：支持配置变更审计日志
- [ ] Task 59：配置热加载必须只影响邮件系统，不影响企微配置

### P1：CRM 邮件侧联调

- [ ] Task 60：确认 CRM 客户 Key、联系人邮箱、行业、账期、销售负责人、签名字段
- [ ] Task 61：实现 CRM 画像联查和域名级 fallback
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

Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库。

## 任务执行规则

- 每次只执行第一个未完成任务，完成并验证后更新本文件与日志再结束。
- 每个任务完成后必须更新本文件。
- 不允许跳过未完成任务。
- 如果任务需要拆分，请在本文件中新增子任务。
- 如果遇到 token、rate limit、quota、429、usage limit、temporarily unavailable 或网络临时错误，不要把任务标记失败；本轮如实记录后结束，由 gateway 的 cron 周期（如 every 2m）自动重试，断网不丢任务。
- 任务通过 Hermes gateway + cron 循环驱动：每个 cron tick 是独立隔离会话，只做第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加进展或报错（含时间/任务号/做了什么/成功或失败/下一步）；失败如实写，严禁"假绿"。
- 如果所有任务完成，必须生成 `FINAL_REPORT.md`，并在 `logs/codex-run.log` 末尾追加 `ALL TASKS COMPLETED: 当前时间`。

