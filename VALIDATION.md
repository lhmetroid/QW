# VALIDATION

## 当前阶段

阶段一（邮件数据采矿与清洗）已交付：CRM 全量同步完成（`mail_raw_unified` 约 80 万、`mail_cleaned` 约 60 万），Task 11 已导出首批 25 条脱敏黄金候选。Task 17 已完成邮件 Few-Shot 检索准入阈值，默认 `useful_score >= 0.60`；Task 22 已完成邮件 Sequence 状态枚举与状态元数据沉淀；Task 23 已完成默认 Step 触发间隔沉淀（Step1 当天、Step2 7 天、Step3 10 天、Step4 10 天）；Task 24 已完成客户回复、CRM 状态变化、人工封印时的状态机物理切断规则沉淀；Task 25 已完成待发草稿销毁或锁定规则沉淀；Task 26 已完成 `POST /api/v1/mail/generate-draft` 脚手架接口；Task 27 已完成请求参数覆盖与额外字段禁止；Task 28 已完成响应参数覆盖核对；Task 29 已完成二阶段生成链路重构；Task 30 已完成价格、工期、折扣、账期后端物理占位符填充；Task 31 已完成生成结果默认进入草稿和审核且不默认真实发送；Task 32 已完成 `POST /api/v1/sequence/interrupt` review-only 中断预审接口；Task 33 已完成 CRM 状态变更触发支持与 `crm_state_change_trigger` 预览；Task 34 已完成销售手动强封印 review-only 支持与 `manual_seal_trigger` 预览；Task 35 已完成客户/域名/联系人维度中断预览；Task 37 已完成中断事件 review-only 操作日志预览与 `logger.info` 输出；Task 38 已完成财务价格底线门，低于底价时返回红牌硬拦截与阻断诊断信息；Task 39 已完成价格正则提取扩展，现可识别 RMB、元、USD、美元、per word、每千字、折扣等表达，并避免把折扣表达误判为底价穿透；Task 40 已完成履约工期 SLA 校准门，低于标准 SLA 时会物理拉正并黄牌锁定；Task 41 已完成收件域名与抄送域名防泄密门，命中竞对或风险收件/抄送域名时红牌硬拦截且不真实发信；Task 42 已完成竞对域名黑名单与客户域名白名单双校验，当前进入 Task 43：实现敏感词扫描，拦截内部底价、财务个人账户、非公开返点等高风险文本。

运行方式：Hermes gateway + cron 循环（每个 cron tick 独立只做第一个未完成任务，中文写日志，失败由 cron 周期（间隔 2 分钟）自动重试，近似连续）。

此阶段主要验证：

- 黄金切片字段结构是否清晰、可入库、与已导出字段（`source_type/source_ref/scenario/useful_score/desensitized_status`）对齐。
- 邮件系统是否明确与企微系统隔离。
- 当前任务是否明确排除四期规划。
- 每个 cron tick 是否用中文如实写入 `logs/codex-run.log`（成功与失败都写，不"假绿"）。

## 当前必须执行（只查本任务改动的文件，不跑全仓）

⚠️ **不要跑全仓 `git diff --check`**。仓库内有大量历史遗留的无关文件存在行尾空白（如 `_s03_section.txt` 等），全仓检查会一直失败——**这些无关历史文件的行尾空白不是本任务的失败项**，不得因此判定任务未完成、不得反复重试或反复去改无关文件。

只对**本任务实际改动/新增的文件**做定向检查（把 `<本任务改动文件>` 换成本轮真实改的文件清单）：

```bash
git diff --check -- <本任务改动文件>
```

如本任务改了 Python，再做语法检查：

```bash
python3 -m py_compile <本任务改动的.py>
```

## 当前建议执行

```bash
git status --short
```

## 当前通过标准

- 对**本任务改动文件**的定向 `git diff --check -- <改动文件>` 返回 0（全仓 `git diff --check` 因无关历史文件失败**不算**本任务失败，不得据此重试）。
- `AGENTS.md` 存在，并包含邮件/企微隔离规则。
- `TASKS.md` 存在，并包含可执行任务清单。
- `PROGRESS.md` 存在，并记录当前状态、已完成、未完成、下一步。
- `TASK_HANDOFF.md` 存在，并能让其他 Agent 恢复任务。
- `VALIDATION.md` 存在，并列出验证命令和通过标准。
- `logs/codex-run.log` 存在，并可记录运行进展。
- `logs/codex-retry.log` 存在，并可记录 token/rate limit 或失败重试。
- `TASKS.md` 明确说明当前暂不考虑四期规划。
- `AGENTS.md` 明确将“恢复、重试、不中断”作为最高优先级。
- `AGENTS.md` 包含 Hermes 短启动指令。
- 文件中没有真实 API Key、数据库密码或客户敏感信息。

## 日志与重试规则验证标准

- `AGENTS.md` 必须说明 token、rate limit、quota、429、usage limit、temporarily unavailable、网络临时错误的处理流程。
- `AGENTS.md` 必须说明 Codex CLI 意外退出后的恢复流程。
- `TASK_HANDOFF.md` 必须有最近中断记录区域。
- `TASK_HANDOFF.md` 必须有 Token / Rate Limit 记录区域。
- `PROGRESS.md` 必须记录当前任务、当前小点、状态、最近更新时间。
- `logs/codex-run.log` 和 `logs/codex-retry.log` 不要求有大量内容，但必须存在。
- 前台或后台长任务如果运行超过 5 分钟，`logs/codex-run.log` 必须存在对应心跳；如果没有实时心跳，`TASK_HANDOFF.md` 必须记录补记原因、运行时长和下一步。

## 后续代码阶段基础验证

如后续修改 Python 后端，至少执行（WSL 下用 `python3`；若 WSL 缺依赖，用 `uv run --with-requirements backend/requirements.txt python ...` 或改在 Windows Python 执行）：

```bash
python3 -m py_compile backend/main.py backend/intent_engine.py backend/config.py
```

Task 17 修改邮件 Few-Shot 检索准入时，至少执行：

```bash
python3 -m py_compile backend/main.py backend/database.py backend/config.py
git diff --check -- backend/main.py backend/database.py backend/config.py docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log
```

如新增邮件后端模块，按实际文件补充：

```bash
python3 -m py_compile backend/mail_models.py backend/mail_service.py backend/mail_safety.py backend/mail_sequence.py backend/mail_routes.py
```

如项目已有测试环境且依赖满足，执行：

```bash
python3 -m pytest
```

## 后续前端阶段验证

如修改纯 HTML/JS 前端，建议执行对应 JS 语法检查。

示例：

```bash
node --check frontend/index.html
```

如果前端是内联脚本，需按项目现有脚本抽取或使用已有验证方式，不要盲目新增复杂工具链。

## 邮件 API 阶段验证标准

> ⚠️ **2026-05-28 修正**：本节早期版本只断言"契约形态"和"`real_sending_enabled=false`"，导致 Task 26-45 被验收为"通过"但底层没接真 LLM、没查真 CRM、没检索真 Few-Shot。为切断这种"骨架=通过"的反馈环，验收标准必须**同时**覆盖 (A) 契约形态 和 (B) 真接入证据。两组都过才能算 ✅。

### (A) 契约形态（必要但不充分）

实现 `POST /api/v1/mail/generate-draft` 后，应验证：

- 缺少必填字段时返回清晰错误。
- 合法请求能生成草稿。
- 返回包含 `mail_uid`、`final_subject`、`final_body_html`、`safety_guardrail`。
- 低于底价的价格表达会被红牌拦截。
- 低于 SLA 的工期表达会被拉正并黄牌锁定。
- 竞对域名或敏感收件域名会被红牌拦截。
- SMTP 真发出口由 `MAIL_REAL_SENDING_ENABLED` 控制，默认 false（这是允许的运行时护栏，不是免接入借口）。

实现 `POST /api/v1/sequence/interrupt` 后，应验证：

- 客户 / 联系人 / 域名维度中断都有效。
- 销售手动强封印可通过 `manual_seal` 或 `manual_sealed_by_sales` 归一到邮件侧 manual-seal 规则。
- 中断后待发草稿被锁定或删除。
- 响应包含 `deleted_pending_drafts_count` 或等价字段。
- 操作日志可追踪。

### (B) 真接入证据（充分条件，缺一不算完成）

下面任何一条不达标，任务必须降级为 `[~] 契约骨架完成，待真接入`，不能标 `[x]`：

- **LLM 真调用**：同一个 `customer_key` + `scenario` + `suite_step` 调两次 generate-draft，`final_body_html` 文本内容不应一字不差地一致（LLM 有 temperature，纯模板拼装会一字不差）。响应或日志里必须能看到实际调用的 LLM model 名（如 `gpt-4o-mini`），不是字符串常量。
- **Few-Shot 真检索**：`retrieved_fewshot_id` 必须真实指向 `email_fragment_asset` 表的某一行，用 `psql -c "SELECT id, snippet_type FROM email_fragment_asset WHERE id = '<返回值>'"` 能查到。如果该表为空，先证明 seed loader 跑过。
- **CRM 真查询**：返回的 `company_industry`、`payment_risk_level` 等字段必须来自真 CRM 数据源（SQL Server 或独立的 mock CRM 服务），不能来自 `backend/mail_crm_mock_data.py` 这种 Python 常量。验收时把 CRM 里某个客户的 industry 字段改一下，再调接口看是否跟着变。
- **前端真渲染**：浏览器打开邮件质量诊断面板（`#mail-quality`），打开 Network 面板，必须能看到对 `/api/v1/mail/generate-draft` 的真实请求；面板上的草稿内容必须随后端返回变化，不是页面内 Mock 常量。
- **演示证据落盘**：上述每条验收要把 curl 命令或浏览器截图贴到 `logs/dod-task<N>.md`，且必须包含响应中能体现"真"的字段（model 名、fewshot id、CRM 来源标识）。

### 反模式速查

下面这些短语在任务完成描述里出现，就是 (B) 不达标的红灯信号，应当被审查：

- "review-only Mock"
- "不调用后端"
- "不写数据库"
- "页面内预览"
- "Mock dict 替代 CRM"
- "硬编码模板"
- "复用既有 mock 数据源"

## 邮件采矿阶段验证标准

邮件采矿与清洗完成后，应验证：

- 支持断点续传。
- 退信、广告、自动回复、历史引用盖楼被排除。
- HTML 正文清洗后仍保留业务语义。
- `useful_score >= 0.60` 的候选切片可导出。
- 首批黄金候选切片有来源、场景、质量分和脱敏状态。
- Mock 数据与真实数据标注清楚。

## 邮件安全门对抗测试标准

至少覆盖以下攻击：

- 低价穿透：诱导生成低于底价的单价。
- 折扣穿透：诱导承诺未审批折扣。
- 工期穿透：诱导承诺 24 小时完成大项目。
- 占位符绕过：诱导直接输出 `XX`、`xxxx@xx.com`、`POxxxx` 等占位符。
- 同业钓鱼：收件人或抄送包含竞对域名。
- 敏感信息泄露：正文包含内部底价、非公开返点、财务个人账户等。

通过标准：

- 红牌场景 100% 阻断。
- 黄牌场景必须物理拉正并锁定发送。
- 拦截原因可在诊断面板或日志中追踪。

## 完成任务后的文档要求

每完成一个任务，必须更新：

- `PROGRESS.md`
- `TASK_HANDOFF.md`
- `logs/codex-run.log`

如果任务前台运行超过 5 分钟，还必须在恢复控制权后补写：

- 前台运行总时长
- 最后可见输出
- 是否被 Ctrl+C 中断
- 是否产生文件变更
- 下一步动作

如完成功能迭代，还应按 `项目进展.md` 的历史规范在末尾追加版本日志，不得修改或删除旧版本内容。

如果所有任务完成，还必须生成：

- `FINAL_REPORT.md`

并在 `logs/codex-run.log` 末尾追加：

```text
ALL TASKS COMPLETED: 当前时间
```
