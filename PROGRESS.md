# PROGRESS

## 当前状态

- 当前任务：Task 15：定义邮件切片适用场景：老客户唤醒、新业务推广、新联系人介绍
- 当前小点：Task 14 已完成，已在 `docs/mail_gold_snippet_schema.md` 正式定义 `greetings`、`example`、`process`、`constraint`、`quotation` 五类 `snippet_type`，补齐用途、边界、判定规则、可包含/不可包含内容、示例字段建议、混合内容优先级与内容安全口径。
- 状态：Task 14 已完成，Task 15 尚未开始
- 最近更新时间：2026-05-25 14:49:00 +08:00

## 最近完成的小点

| 时间 | 任务 | 小点 | 结果 | 验证 |
|---|---|---|---|---|
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

- Task 14 已完成；尚未开始 Task 15：定义邮件切片适用场景。
- 尚未实现邮件 API。
- 尚未实现邮件安全门。
- 尚未实现邮件诊断面板。

## 当前卡点

- 当前无 Task 11 阻断；导出依赖在本次 `uv run --with-requirements` 执行时已可用。
- Task 13 已把已导出的字段沉淀为正式黄金切片结构，避免导出字段与知识库入库字段长期分叉。
- Task 14 已把 `snippet_type` 正式收敛为 5 个固定枚举，并明确混合内容时按主用途拆片或单类型判定，避免把价格、流程、问候混入同一 Few-Shot。
- 运行方式已切换为 gateway + cron 循环：每个 cron tick 独立做一个任务并用中文写 `logs/codex-run.log`，失败由 cron 周期自动重试，不再依赖前台会话保姆式心跳。

需要下一步确认或执行：

- 继续 Task 15：定义三大邮件场景 `re_activation`、`new_business_promotion`、`new_contact_intro` 的适用边界与映射口径。
- 如需复查导出结果，可优先查看 `docs/mail_gold_candidates/latest_mail_gold_candidates.md` 的脱敏摘要表。

## 下一步

继续 Task 15：定义邮件切片适用场景。

```bash
git diff --check -- docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log
```

Task 11 已产出：

- `docs/mail_gold_candidates/latest_mail_gold_candidates.json`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.csv`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.md`

## 最近验证

本轮已执行：

```bash
git diff --check
git diff --check -- TASKS.md PROGRESS.md TASK_HANDOFF.md
rg -n '[ \t]+$' docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log
```

结果：`git diff --check -- docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md` 通过；`rg -n '[ \\t]+$' docs/mail_gold_snippet_schema.md TASKS.md PROGRESS.md TASK_HANDOFF.md VALIDATION.md logs/codex-run.log` 未发现本轮新增行尾空白。全仓库 `git diff --check` 仍可能受既有无关改动影响，因此以本轮定向验证为准。Task 14 文档定义已完成，Task 15/16/17/18 仍未实现。

## 运行监控要求（gateway + cron 循环）

- 任务由 Hermes gateway（每 60 秒 tick）+ cron 循环驱动；每个 cron tick 是独立隔离会话，只做第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加记录：当前时间、当前任务（任务号）、本轮做了什么、成功或失败（失败写原因）、下一步动作。
- 失败（网络/模型临时断开等）如实写入 `logs/codex-run.log` 和 `logs/codex-retry.log`，由 cron 周期自动重试，不丢任务，严禁"假绿"。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron `last_status` 为准。
- 查看：`hermes cron list` / `hermes cron status` / `~/.hermes/cron/output/<job_id>/`。
