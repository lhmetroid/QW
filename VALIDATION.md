# VALIDATION

## 当前阶段

阶段一（邮件数据采矿与清洗）已交付：CRM 全量同步完成（`mail_raw_unified` 约 80 万、`mail_cleaned` 约 60 万），Task 11 已导出首批 25 条脱敏黄金候选。Task 17 已完成邮件 Few-Shot 检索准入阈值，默认 `useful_score >= 0.60`；当前进入 Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库（P0 知识库与 Few-Shot 结构）。

运行方式：Hermes gateway + cron 循环（每个 cron tick 独立只做第一个未完成任务，中文写日志，失败由 cron 周期（间隔 2 分钟）自动重试，近似连续）。

此阶段主要验证：

- 黄金切片字段结构是否清晰、可入库、与已导出字段（`source_type/source_ref/scenario/useful_score/desensitized_status`）对齐。
- 邮件系统是否明确与企微系统隔离。
- 当前任务是否明确排除四期规划。
- 每个 cron tick 是否用中文如实写入 `logs/codex-run.log`（成功与失败都写，不"假绿"）。

## 当前必须执行

```bash
git diff --check
```

当前只验证本轮新增状态文件时，可以执行：

```bash
git diff --check -- AGENTS.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log
```

## 当前建议执行

```bash
git status --short
```

## 当前通过标准

- `git diff --check` 返回 0。
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

实现 `POST /api/v1/mail/generate-draft` 后，应验证：

- 缺少必填字段时返回清晰错误。
- 合法 Mock 请求能生成草稿。
- 返回包含 `mail_uid`、`final_subject`、`final_body_html`、`safety_guardrail`。
- 低于底价的价格表达会被红牌拦截。
- 低于 SLA 的工期表达会被拉正并黄牌锁定。
- 竞对域名或敏感收件域名会被红牌拦截。
- 默认只生成草稿，不真实发送邮件。

实现 `POST /api/v1/sequence/interrupt` 后，应验证：

- 客户维度中断有效。
- 联系人维度中断有效。
- 域名维度中断有效。
- 中断后待发草稿被锁定或删除。
- 响应包含 `deleted_pending_drafts_count` 或等价字段。
- 操作日志可追踪。

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

