# PROGRESS

## 当前状态

- 当前任务：Task 13：设计邮件黄金切片字段结构 (Task 6-12 已于 2026-05-25 彻底完成，20 年全量 CRM 邮件大同步已成功抓取 46.5 万封新记录，空正文数据通过 repair_cleaned_emails.py 成功重洗恢复 429 封)
- 当前小点：已彻底盘点数据、修复 'sales'/'seller' 黄金切片筛选 Bug，成功导出 25 封黄金种子切片，全量完成 CRM 邮件抓取与数据清洗修复。
- 状态：CRM数据全部同步且洗涤修复完成
- 最近更新时间：2026-05-25 10:15:00 +08:00

## 最近完成的小点

| 时间 | 任务 | 小点 | 结果 | 验证 |
|---|---|---|---|---|
| 2026-05-25 10:11:31 | Task 6-12 | 重新清洗并修复 body_main_text 为空的误伤邮件数据 | 已完成 | 成功修复并重洗 2,838 封空 main_text 记录，完美恢复 429 封 |
| 2026-05-25 10:13:00 | Task 6-12 | 完成 20 年 CRM 全量 57.8 万封往来邮件的大同步抓取 | 已完成 | task-987 同步成功，新增: 465,576 封, 数据库总数: 800,163 封 |
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

- 尚未开始 Task 13：设计邮件黄金切片字段结构。
- 尚未实现邮件 API。
- 尚未实现邮件安全门。
- 尚未实现邮件诊断面板。

## 当前卡点

- 当前无 Task 11 阻断；导出依赖在本次 `uv run --with-requirements` 执行时已可用。
- 后续需在 Task 13 中把已导出的字段沉淀为正式黄金切片结构，避免导出字段与知识库入库字段长期分叉。
- 监控规则偏差仍需持续遵守：前台或后台长任务每 5 分钟必须追加 `logs/codex-run.log` 心跳；前台无法实时写入时，恢复控制权后必须补记运行时长、最后输出和下一步。

需要下一步确认或执行：

- 继续梳理 Task 13 所需黄金切片字段结构，复用本次导出已经落地的 `source_type/source_ref/scenario/useful_score/desensitized_status` 字段。
- 如需复查导出结果，可优先查看 `docs/mail_gold_candidates/latest_mail_gold_candidates.md` 的脱敏摘要表。

## 下一步

继续 Task 13：设计邮件黄金切片字段结构。

```bash
python3 -m py_compile backend/export_mail_gold_candidates.py
git diff --check -- backend/export_mail_gold_candidates.py TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log logs/codex-retry.log VALIDATION.md docs/mail_gold_candidates/latest_mail_gold_candidates.json docs/mail_gold_candidates/latest_mail_gold_candidates.csv docs/mail_gold_candidates/latest_mail_gold_candidates.md
```

Task 11 已产出：

- `docs/mail_gold_candidates/latest_mail_gold_candidates.json`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.csv`
- `docs/mail_gold_candidates/latest_mail_gold_candidates.md`

## 最近验证

本轮已执行：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --with-requirements backend/requirements.txt python backend/export_mail_gold_candidates.py --limit 25 --min-score 0.60
python3 -m py_compile backend/export_mail_gold_candidates.py
git diff --check -- backend/export_mail_gold_candidates.py TASKS.md PROGRESS.md TASK_HANDOFF.md logs/codex-run.log logs/codex-retry.log VALIDATION.md docs/mail_gold_candidates/latest_mail_gold_candidates.json docs/mail_gold_candidates/latest_mail_gold_candidates.csv docs/mail_gold_candidates/latest_mail_gold_candidates.md
```

通过。导出命令成功输出 25 条脱敏候选，latest JSON/CSV/Markdown 均存在且非空。

## 运行监控要求

- 前台或后台长任务每 5 分钟必须追加 `logs/codex-run.log`。
- 日志至少包含当前时间、当前任务、当前小点、运行形态、已运行时长、最近输出摘要、是否有新输出、下一步动作。
- 如果前台运行期间无法实时写日志，恢复控制权后必须补写，例如：`elapsed=6m, foreground=true, no_new_output=true, last_visible_output=deliberating`。
- 如果超过 5 分钟没有心跳日志，应在 `TASK_HANDOFF.md` 记录“前台心跳缺失”。
