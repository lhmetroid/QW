# TASK_HANDOFF

## 当前目标

根据《邮件智能回复实现方案.md》和《文件创建要求.md》，建立邮件智能回复独立开发的标准项目状态文件，便于后续多个 AI 工具接力开发。

## 当前任务

Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库。

当前小点：Task 17 已完成，邮件 Few-Shot 检索准入默认阈值已落地为 `useful_score >= 0.60`，并提供只读检索接口 `/api/v1/mail/fewshot/retrieve`。

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

- 尚未开始 Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库。
- 未实现邮件 API。
- 未实现邮件安全门。
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
- `docs/mail_gold_snippet_schema.md`

## 最近中断记录

| 时间 | 类型 | 原因 | 当前任务 | 下一步 |
|---|---|---|---|---|
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
| 2026-05-22 16:45:35 +08:00 | 网络临时错误 | `uv` 安装项目声明依赖时访问 `https://pypi.org/simple/openpyxl/` 失败：`Temporary failure in name resolution` | 1 | 2026-05-22 17:29 +08:00（cron `fb402953d033`） | 否 |
| 2026-05-22 17:42:17 +08:00 | 恢复成功 | 同一导出命令本次成功安装/解析声明依赖并完成 25 条脱敏候选导出 | 2 | 无 | 是 |

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

继续 Task 18：实现人工纠偏后的高质量切片反哺逻辑，暂不自动污染黄金库。

```bash
python3 -m py_compile backend/main.py backend/database.py backend/config.py
git diff --check -- backend/main.py backend/database.py backend/config.py docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log logs/codex-retry.log
```

Task 11 完成后可复查：

1. `docs/mail_gold_candidates/latest_mail_gold_candidates.json`
2. `docs/mail_gold_candidates/latest_mail_gold_candidates.csv`
3. `docs/mail_gold_candidates/latest_mail_gold_candidates.md`

Task 17 通过标准已满足：邮件 Few-Shot 默认准入阈值为 `useful_score >= 0.60`；只读接口 `/api/v1/mail/fewshot/retrieve` 会同时过滤 `status`、`publishable`、`allowed_for_generation`、`usable_for_reply`，并兼容衔接 `source_snapshot` 中的 `retrieval_enabled`、`is_safe_for_fewshot`、`review_status`、`desensitized_status`。本轮 Python 语法检查和目标文件定向 `git diff --check` 通过；全仓 `git diff --check` 仍受既有无关历史行尾空白影响。Task 18 尚未实现。

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

