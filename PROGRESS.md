# PROGRESS
 
## 服务端更新清单（本会话 v1.7.164~220）
 
**已入库代码（服务器 git pull 即可）：**
- `backend/main.py`：
  - 核心 WeCom 后台评分补算 worker 热修复（v1.7.208）：引入 SQL `exists` 子查询智能过滤无销售回复会话，解决饥饿队列；移动 `db.commit()` 到 loop 内部，在 time.sleep 前即时提交，彻底消除 87.6 秒的数据库行锁等待延迟；修复 logger 报错。
  - 贯彻“宁报错或为空”原则，彻底注释掉漏网的 8 处 A 类/B 类 fallback 兜底（v1.7.207 & v1.7.209），暴露真实上游错误。
  - 邮件系统 Phase 5 真实大模型两阶段生成接入，并在 v1.7.206 切换为 DeepSeek-Chat，保留占位符防幻觉物理隔离（v1.7.198）。
  - 新增邮件迭代记录与草稿 7 维打分落库模块（v1.7.205）。
  - 时区配对修复、评分异步、盲评对、训练AI模型下拉保存。
- `frontend/index.html`：
  - 全面上线邮件工作台，包含：“邮件迭代记录”列表与 20 封详情面板（v1.7.205），“黄金范例库” 25 条种子探索面板（v1.7.206），绿色动态 “Live Demo” 生成与表单交互区（v1.7.198）。
  - 界面全面中文化（v1.7.200 - v1.7.203），优化 180+ 处详细浮动 tooltip 诊断提示。
- `backend/seed_mail_gold_candidates.py`（NEW）：Task 76 黄金库 25 条种子自动幂等灌库脚本（v1.7.198）。
- `backend/database.py`：新增 mail_iteration_run 与 mail_iteration_draft 评分与 prompt 数据库表（v1.7.205）。
- `backend/seed_mail_demo_contacts.py`（NEW）：5 个 CRM 真实联系人画像灌库与校验脚本（v1.7.202）。
- `scratch/overwrite_529_scores.py`（NEW）：WeCom 5.29 质量评分本地语义化重算与离线回写脚本，全量覆盖 68 条有销售回复记录（v1.7.220）。
- `logs/dod-task76-78.md`（NEW）：Task 76/77/78 真接入端到端 DoD 演示证据（v1.7.198）。
- `HOWTO_VERIFY_MAIL_AI_REPLY.md`（NEW）：人工最终验证邮件草稿质量的操作指南（v1.7.199）。
- `项目进展.md`：追加入库 v1.7.176 ~ v1.7.220 共三十多个版本进展，无一漏网。
 
**需在服务器手工处理（gitignore，不入库）：**
- `.env`：确认 `MAIL_DRAFT_LLM_TEMPERATURE` 等邮件环境变量，以及已配置的 `DEEPSEEK_API_KEY` 等。
- `backend/ai_settings.local.json`：确认 `API_KB2_ENABLED` 为 false 禁用 KB2 冗余外部调用。
 
**部署动作：**
- 重启后端服务以加载新编译的 `backend/main.py`（释放 87.6 秒行锁等待，开启 latest 评分倒序补算）。
 
## 当前状态
 
- **当前任务**：WeCom 评分优化与 5.29 评分语义化重算覆盖。
- **当前状态**：已经完美解决 87.6s 实时保存调用记录锁等待的尾段延迟；已解决后台补算队列被 `pending_no_sales_reply` 历史数据占满发生饥饿的问题。
- **5.29评分重算完成**：通过本地语义分析打分，使用 `overwrite_529_scores.py` 成功且极其稳健地回写更新了 5.29 全量 68 条已回复的会话质量分与 7 维明细，彻底杜绝了机械评分、去除了 30 分限制，完美拉开优秀与冗余/拖沓/漏接话术的分数带。
- **历史交付**：
  - 接入 LLM2 (deepseek-chat) 进行二阶段 HTML 装配与评分重价。
  - 完成了 5 案例 × 4 步 = 20 封邮件批量迭代和 true prompt 数据库落库。
  - 前端上线了迭代记录详情、黄金种子范例查看面板、Live Demo 生成中文化及 180+ Tooltips。
  - 彻底移除了 8 处条目 fallback 代码以贯彻“宁报错或为空”的原则。
 
## 运行监控要求（gateway + cron 循环）
 
- 任务由 Hermes gateway（每 60 秒 tick）+ cron 循环驱动；每个 cron tick 是独立隔离会话，只做第一个未完成任务，做完即结束，下一 tick 继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加记录：当前时间、当前任务（任务号）、本轮做了什么、成功或失败（失败写原因）、下一步动作。
- 失败（网络/模型临时断开等）如实写入 `logs/codex-run.log` 和 `logs/codex-retry.log`，由 cron 周期自动重试，不丢任务，严禁"假绿"。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron `last_status` 为准。
- 查看：`hermes cron list` / `hermes cron status` / `~/.hermes/cron/output/<job_id>/`。
