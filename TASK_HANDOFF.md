# TASK_HANDOFF

## 当前目标

根据《邮件智能回复实现方案.md》和《文件创建要求.md》，建立邮件智能回复独立开发的标准项目状态文件，便于后续多个 AI 工具接力开发。

## 当前任务

Task 2：梳理邮件智能回复与企微智能回复的模块边界。

当前小点：已完成前置读取；尝试通过 Codex CLI 后台执行 Task 2 时被环境拦截。已明确 `--full-auto` 是默认自动执行模式，需在 Hermes/Codex CLI 环境放行普通项目内任务，或由当前 Agent 继续安全任务。

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

## 未完成

- 未进入代码实现。
- 未设计邮件表结构。
- 未实现邮件采矿。
- 未实现邮件 API。
- 未实现邮件安全门。
- 未实现邮件前端。
- 未追加 `项目进展.md` 版本日志。

## 已修改文件

- `AGENTS.md`
- `TASKS.md`
- `PROGRESS.md`
- `TASK_HANDOFF.md`
- `VALIDATION.md`
- `logs/codex-run.log`
- `logs/codex-retry.log`

## 最近中断记录

| 时间 | 类型 | 原因 | 当前任务 | 下一步 |
|---|---|---|---|---|
| 2026-05-22 15:30:52 +08:00 | 权限/执行拦截 | 启动 `codex exec --full-auto ...` 后台任务时返回 `BLOCKED: User denied. Do NOT retry.` | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 需要人工确认是否允许在当前环境放行 Codex CLI 执行；未放行前不要自动重试 |
| 2026-05-22 15:38:23 +08:00 | 规则澄清 | 已确认 `BLOCKED: User denied. Do NOT retry.` 不是 token/rate/network 临时错误，不能自动重试或危险绕过 | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 可由用户在 Hermes 环境放行 `codex exec --full-auto`；若当前 Agent 能安全完成，可记录后继续执行同一任务 |
| 2026-05-22 15:39:26 +08:00 | 权限策略修正 | 用户明确 `--full-auto` 是默认自动执行模式，普通安全任务不要逐次授权 | Task 2：梳理邮件智能回复与企微智能回复的模块边界 | 已更新 AGENTS.md，明确普通项目内开发任务默认自动执行；仅高风险清单需要人工确认 |

## Token / Rate Limit 记录

| 时间 | 错误类型 | 错误内容 | 重试次数 | 下一次重试 | 是否恢复 |
|---|---|---|---|---|---|
| 无 | 无 | 无 | 0 | 无 | 不适用 |

## 建议下一步

继续 `TASKS.md` 中第一个未完成任务：

Task 2：梳理邮件智能回复与企微智能回复的模块边界。

具体建议：

1. 读取 `backend/` 目录结构，标出现有企微入口、RAG、LLM、配置、数据库模型。
2. 读取 `frontend/` 目录结构，标出现有企微侧边栏页面和可新增邮件页面的位置。
3. 设计邮件新增模块的建议路径，例如：
   - `backend/mail_models.py`
   - `backend/mail_service.py`
   - `backend/mail_safety.py`
   - `backend/mail_sequence.py`
   - `backend/mail_routes.py`
   - `frontend/mail/` 或独立邮件页面入口
4. 明确哪些通用能力可以复用，哪些业务状态必须隔离。
5. 形成一份邮件/企微边界说明，再进入数据库和 API 设计。

## 重要约束

- 不要删除或改写 `项目进展.md` 既有历史内容。
- 不要把邮件 Sequence 状态写入企微会话状态机。
- 不要让邮件测试阻塞企微 8071 后端现有使用。
- 不要默认开启真实邮件发送。
- 不要把 Mock 数据描述为真实生产数据。
- 不要暴露真实客户敏感信息、API Key、数据库密码或内部底价。
- `codex exec --full-auto` 是默认自动执行模式；项目内普通读写、测试、lint、build、代码生成脚本不应逐次请求授权。
- `BLOCKED: User denied. Do NOT retry.` 对普通安全任务而言属于环境未放行 `--full-auto`，不得自动重试，不得用危险参数绕过；用户放行 `--full-auto` 后应继续同一任务。
- 如果 Codex CLI 委派被拒绝，但任务可由当前 Agent 安全完成，可以记录阻断原因后继续同一个任务，仍需运行验证并更新状态文件。

## 恢复提示词建议

```text
请加载 codex skill。当前目录是 Git 项目。

最高优先级：任务必须可恢复、可重试、不中断。不要因为 Codex CLI token 不足、rate limit、quota、429、usage limit、temporarily unavailable、网络临时错误或进程意外退出而放弃任务。

请先读取：
- AGENTS.md
- TASKS.md
- PROGRESS.md
- TASK_HANDOFF.md
- VALIDATION.md
- git status
- git diff
- logs/codex-run.log
- logs/codex-retry.log

如果上述文件或 logs 目录不存在，请先创建并初始化。

你作为任务主管，通过 Codex CLI 执行任务，不要控制 Windows 的 Codex 插件、桌面版、VS Code 插件、Cursor、Antigravity 或任何图形界面。

请严格按 AGENTS.md 的规则执行，重点遵守：
1. 只处理 TASKS.md 中第一个未完成任务。
2. 调用 Codex CLI 时默认使用 --full-auto。
3. Codex CLI 长任务必须后台运行并监控。
4. 每 2 分钟检查一次 Codex CLI 状态。
5. 每 5 分钟更新 PROGRESS.md，并追加 logs/codex-run.log。
6. 每完成一个小点，必须记录完成时间。
7. 当前小任务完成后，运行 VALIDATION.md 中的验证命令。
8. 验证通过后，更新 TASKS.md、PROGRESS.md、TASK_HANDOFF.md。
9. 如果遇到 token 不足、rate limit、quota、429、usage limit、temporarily unavailable 或网络临时错误，立即写入 TASK_HANDOFF.md 和 logs/codex-retry.log，并每 30 分钟重试一次；恢复后继续当前未完成任务；连续失败 6 次才停止。
10. 如果 Codex CLI 意外退出，读取日志、git status、git diff，更新 TASK_HANDOFF.md，并尝试恢复当前小任务。
11. 如果遇到登录失败、需要人工授权、危险命令、删除大量文件、推送远程仓库、修改生产环境配置、访问密钥、数据库写操作，停止并写入 TASK_HANDOFF.md，不要自动继续。
12. 如果所有任务完成，生成 FINAL_REPORT.md，并在 logs/codex-run.log 末尾追加 ALL TASKS COMPLETED: 当前时间。

现在开始执行第一个未完成任务。目标是保证任务持续推进和可恢复，最终完成全部计划代码修改。
```
