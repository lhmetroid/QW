# AGENTS

## 0. 最高优先级：恢复、重试、不中断

本项目的最高优先级不是一次性快速完成，而是确保任务可恢复、可重试、不中断。

如果 Hermes 调度 Codex CLI，或任何 Agent 执行任务时出现以下情况，不允许直接放弃任务：

- token 不足
- rate limit
- quota
- temporarily unavailable
- 429
- usage limit
- 模型额度不足
- 上下文不足
- 网络临时错误
- Codex CLI 进程意外退出
- 终端会话中断
- 长任务无输出但进程仍存在

处理原则：

1. 先记录，再判断，再恢复。
2. 所有失败必须写入 `TASK_HANDOFF.md`。
3. 所有重试必须写入 `logs/codex-retry.log`。
4. 所有运行进展必须写入 `logs/codex-run.log`。
5. 每次恢复前必须重新读取 `TASKS.md`、`PROGRESS.md`、`TASK_HANDOFF.md`、`git status` 和 `git diff`。
6. 不依赖上一次聊天记忆恢复任务，必须依赖项目文件和 Git 状态恢复。
7. 未经用户明确要求，不回滚当前改动，不清理临时文件。

## 1. 角色分工

- Hermes 是本项目的任务主管、调度器和恢复器。
- Codex CLI 是代码执行员。
- 不控制 Windows 的 Codex 插件、Codex 桌面版、VS Code 插件、Cursor、Antigravity 或任何图形界面。
- 所有自动化开发任务都通过当前环境中的 Codex CLI 执行。

## 项目定位

本项目当前包含两个业务方向：

- 企微智能回复：现有主系统，包含企微会话采集、意图识别、RAG、侧边栏辅助回复、案例库评分与迭代。
- 邮件智能回复：新增独立开发轨道，聚焦邮件历史数据采矿、客户激活邮件草稿生成、邮件 Sequence、邮件安全门、邮件质量诊断与 CRM 邮件侧联调。

邮件智能回复必须尽量与企微智能回复区分，便于各自调整、独立验证和独立部署，避免邮件功能构建或调试影响企微现有使用。

## Agent 启动规则

所有 AI Agent 开始任务前必须先读取：

- `AGENTS.md`
- `TASKS.md`
- `PROGRESS.md`
- `TASK_HANDOFF.md`
- `VALIDATION.md`
- `git status`
- `git diff`
- `logs/codex-run.log`
- `logs/codex-retry.log`

如果以上文件或 `logs/` 目录不存在，必须先创建并初始化。

如任务涉及邮件智能回复，还必须读取：

- `邮件智能回复实现方案.md`
- `文件创建要求.md`

如任务涉及企微智能回复，还必须读取：

- `项目进展.md`
- `企微记录入知识库标准定义.md`
- 相关后端、前端或 docs 文件

## 工作方式

- 每次只处理 `TASKS.md` 中第一个未完成任务，完成并按 VALIDATION.md 验证后更新状态再结束。
- 修改前先确认当前 git 工作区状态，避免覆盖用户或其他 Agent 的改动。
- 修改代码或文档前先理解现有结构，不做无关重构。
- 修改完成后必须按 `VALIDATION.md` 运行对应验证。
- 每完成一个任务，必须更新 `PROGRESS.md`。
- 如果任务中断、失败、等待授权、上下文不足或需要交给其他工具继续，必须更新 `TASK_HANDOFF.md`。
- 不允许把 Mock 数据、推演数据、示例数据描述成真实生产数据。
- Git 提交、推送远程仓库、创建 tag、发布 release 可按任务需要执行，不需要额外人工授权；但不得在无任务需要时随意执行。

## 完成定义 (Definition of Done)

任何任务标记 `[x]` 之前，必须**同时**满足下面三个条件，缺一不可。只过 (1) 不过 (2)(3) 的任务必须改写成 `[~] 契约骨架完成，待真接入` 而不是 `[x]`。

1. **契约通过**：`python -m py_compile`、`node --check` 等基础语法检查通过；该任务对应的 `*_checks.py` 或单元测试通过。
2. **端到端可演示**：能用一条 curl 或浏览器操作真实跑通这个任务覆盖的功能路径，并且输出的数据来源是真实的（真 LLM 调用 / 真数据库查询 / 真 Few-Shot 检索 / 真 CRM 读取），不是 Mock 拼装、静态常量、页面内 dict。演示截图或 curl 输出必须贴到 `logs/dod-task<N>.md`。
3. **推进可用性**：一句话能说清楚——"做完这个任务后，人工最终使用该模块的路径上，又少了哪一步障碍"。如果说不出来，说明任务定义错了，应该回到 TASKS.md 重新写任务标题，而不是硬着头皮做完。

**反模式（曾出现过，必须避免）**：

- 把 `real_sending_enabled=false`、`review_only=true` 写死在响应里就算"安全门完成"——这只证明骨架在，不证明门后面接了 LLM。
- 前端面板做了静态 HTML + 假徽章就算"诊断面板完成"——必须能 fetch 后端真实数据并渲染。
- 用 Mock dict 替代 CRM 查询就算"CRM 联调完成"——必须真连 SQL Server 或至少真连一个独立的 mock CRM 服务，而不是 import 一个 Python 常量。
- 任务括号里写"review-only Mock，不调用后端、不写数据库、不发信"就当通过验收——这一句话本身就是 DoD (2) 不达标的自我承认。

## 运行机制：Hermes gateway + cron 循环

无人值守长任务由 Hermes gateway + cron 循环驱动，不依赖单次前台聊天会话。

- gateway 是常驻调度引擎，每 60 秒 tick 一次到期 cron 任务（已配为 systemd 用户服务，开机/登录自启、注销不掉、崩溃自拉起）。聊天会话本身不是调度器，会话结束不影响 cron。
- 每个 cron tick 在独立隔离会话里运行：读状态文件 → 只做第一个未完成任务 → 按 VALIDATION.md 验证 → 用中文写日志 → 更新状态 → 结束；下一 tick 继续。间隔取 2 分钟（≈每个 tick），近似连续推进；下一轮 = 这轮结束 + 间隔。
- 网络/模型临时断开时本轮失败，cron 下一周期自动再来，不丢任务（适配国内翻墙不稳定）。
- 超时已用 systemd drop-in 固化：`HERMES_CRON_TIMEOUT=0`、`HERMES_AGENT_TIMEOUT=0`，长任务不被不活动超时杀掉。

### 建立循环任务（必须在 WSL 终端用 `hermes cron create` 并带 `--workdir`）

聊天框 `/cron add` 不认 `--workdir`，会让任务跑错目录（默认 `~/.hermes/hermes-agent`）。所以建任务一律在 WSL 终端：

```bash
hermes cron create "every 2m" '请加载 codex skill。当前目录是 Git 项目，通过 Codex CLI 执行任务，不要控制 Windows 的 Codex 插件或桌面版。读取 TASK_HANDOFF.md、TASKS.md、PROGRESS.md、VALIDATION.md 和 git diff，只继续第一个未完成任务。硬性顺序：先在 logs/codex-run.log 用中文写一条 START(时间/任务号/将做什么)，再开始干；完成后先按 VALIDATION.md 验证，再更新 TASKS.md/PROGRESS.md/TASK_HANDOFF.md，最后在 logs/codex-run.log 用中文写一条 DONE(成功或失败/验证结果/下一步)。START 和 DONE 两条日志不可省略，报错另写 logs/codex-retry.log。写任何文件只写真实内容，严禁在行首加 行号| 前缀(如 12|)，更新前先读真实内容、更新后自检首行不是数字加竖线。若 TASKS.md 全部完成则生成 FINAL_REPORT.md 并在 logs/codex-run.log 末尾追加 ALL TASKS COMPLETED 加当前时间，然后停止；不要再新建其他 cron 任务。' --workdir /mnt/d/items/QW --deliver local
```

建完用 `hermes cron list` 确认 `Workdir: /mnt/d/items/QW`、`Schedule: every 2m`，再 `hermes cron run <ID>` 立即开跑。间隔 2 分钟≈近似连续：一轮结束约 2 分钟后接下一轮，失败也约 2 分钟后自动重试。

### 监控与停止

- `hermes cron list`：看任务在不在、跑了几次。
- `hermes cron status`：看 gateway 是否在运行（决定 cron 会不会自动触发）。
- 每轮执行记录：`~/.hermes/cron/output/<job_id>/<时间>.md`。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron 的 `last_status` 为准（可能"假绿"）。
- 全部完成会生成 `FINAL_REPORT.md` 并在 `logs/codex-run.log` 追加 `ALL TASKS COMPLETED`；确认后用 `hermes cron remove <job_id>` 删除任务。

### 强制人工 checkpoint（防自治闭环自我繁殖）

cron 自治模式有一个已知风险：每个 tick 是隔离会话，没有全局视角，agent 自己回填 TASKS.md 的完成括号，再自己写 PROGRESS.md，再自己跑 VALIDATION 盖章——一旦某个 tick 走偏（比如把"默认关闭真发"误解成"代码层不接入"），后续 tick 会把上一 tick 的产物当成 ground truth 继承下去，错误在闭环里被反复放大，最后整个项目变成空壳但 ✅ 全勾。

为了切断这个反馈环，必须强制：

- **每完成 10 个 task，cron 必须暂停**，写一份 `logs/checkpoint-N.md`（N = 第几次 checkpoint），内容至少包括：
  - 把这 10 个 task 加起来，离 "人工能在浏览器跑通真实功能" 还差几步？
  - 用 curl 或浏览器演示一次端到端：能看到真 LLM 输出吗？能拿到真 DB 数据吗？前端面板是真接后端还是页面内常量？
  - 如果答案是"还差很多 / 还没接 / 还是 Mock"，**必须停下等人工 review，不能让 cron 自己继续**。等人工在 `TASK_HANDOFF.md` 写明"已审核，继续"后 cron 才能继续。
- checkpoint 不通过时，cron 不允许在 TASKS.md 上勾新的 `[x]`，只能把当前 task 改成 `[~]` 并写明卡点。
- 这一条比"每个 tick 只做一个任务"优先级更高，违反它的 tick 必须把已做的修改 revert。

## 邮件系统隔离规则

邮件智能回复是独立业务轨道，默认不得影响企微现有运行链路。

### 命名隔离

邮件相关对象建议使用独立命名：

- 后端模块：`backend/mail_*`、`backend/email_*`、`backend/sequence_*`
- API 路由：`/api/v1/mail/*`、`/api/v1/sequence/*`
- 数据表：`mail_*`、`email_*`、`mail_sequence_*`
- 配置项：`MAIL_*`、`EMAIL_*`、`mail_*`
- 前端页面：邮件独立入口或独立页面，不直接塞入企微侧边栏主工作流

### 运行隔离

- 邮件调试不得要求企微侧边栏停服。
- 邮件测试不得依赖企微真实回调。
- 邮件任务队列、批处理、采矿脚本不得阻塞企微实时辅助回复。
- 如需要复用 FastAPI、PostgreSQL、RAG、LLM 客户端等基础能力，必须通过清晰模块边界调用，不把邮件业务状态写入企微会话状态机。
- 邮件配置热加载、缓存、批处理开关必须有独立前缀，避免误改企微配置。

### 数据隔离

邮件历史数据、邮件黄金切片、邮件草稿、Sequence 状态和邮件安全日志应独立存储。

表或模型边界（⚠️ 已落地的表以实际名为准，不要再用旧的建议名）：

已实际落地：

- `mail_raw_unified`：邮件原始统一记录（约 80 万行）。旧文档曾写 `mail_raw_messages`，已不使用。
- `mail_cleaned`：去噪清洗后的邮件正文（约 60 万行，含 `sender_side`=seller/customer/internal、`clean_status`、`is_auto_mail` 等字段）。旧文档曾写 `mail_cleaned_messages`，已不使用。
- `mail_import_batch`：同步批次台账（`import_type`/`success_count`/`failed_count`/`import_status`/`created_at`）。

后续规划（尚未落地，命名以实现时为准）：

- `mail_gold_snippets`：邮件黄金 Few-Shot 切片
- `mail_customer_profiles`：邮件侧 CRM 画像缓存或映射
- `mail_sequences` / `mail_sequence_steps`：客户邮件激活状态机与 4 轮套装步骤
- `mail_drafts`：邮件草稿
- `mail_safety_events`：价格、工期、收件域名、安全门事件
- `mail_feedback_events`：人工纠偏、反哺记录
- `mail_system_configs`：邮件侧配置项

不得把邮件 Sequence 状态写入企微会话摘要表。

## 邮件系统当前实施范围

当前纳入实施范围：

- 邮件历史数据采矿与清洗
- 邮件黄金 Few-Shot / RAG 语料库
- 三大邮件激活场景
  - 老客户唤醒 `re_activation`
  - 新业务推广 `new_business_promotion`
  - 新接手联系人介绍 `new_contact_intro`
- 4 轮 Sequence 套装
- 邮件草稿生成 API
- Sequence 中断 API
- 三重安全门
  - 财务价格底线门
  - 履约工期 SLA 校准门
  - 收件域名与防泄密门
- 邮件质量诊断与人工纠偏面板
- 邮件全局配置管理台
- CRM 邮件侧轻量联调

当前暂不纳入实施范围：

- `四期规划：前瞻性商业化深度优化建议 (以 ROI 与客情关系为中心)`
- ROI 归因看板
- 发信域名信誉保护与高斯随机延迟
- LTV 流失预测
- 跨国客户本土文化风格过滤器
- 大规模生产灰度发信

四期内容可以保留在方案文档中，后续稳定上线后再拆为新任务。

## 邮件系统工程原则

- 物理隔离防幻觉：价格、工期、折扣、账期等高风险内容不得完全交给大模型自由生成，必须通过后端占位符 + PostgreSQL `PricingRule` 强制填充。
- 断点续传防崩溃：邮件采矿、清洗、向量化、打分等批处理必须支持断点续跑。
- 宽进严出避错杀：原始邮件清洗允许保留候选，但生成出口必须强校验。
- 人环协作兜底线：销售或运营必须能审核、修正、锁定、终止邮件草稿。
- 先质量验证后 API 联调：先证明邮件质量、Few-Shot、清洗和安全门稳定，再开放 CRM 联调。
- **真接入优先于审慎收口**：上面这些"防 / 兜 / 避"的护栏是**运行时**的安全开关，不是**代码层**的接入借口。LLM SDK、CRM 查询、Few-Shot 检索、SMTP 客户端、前端到后端的 fetch 调用——这些代码层连线必须真实存在并跑通；安全护栏的作用是在这些连线之上加 `default-off` 开关、人工审核队列、占位符强制替换，而不是用 Mock 字典/静态 HTML/契约骨架取代连线本身。如果某个任务做完后"代码层没多接通任何一根线"，那就是 DoD (2) 不达标，应记为 `[~]` 而不是 `[x]`。

## 文档维护规则

- `项目进展.md` 是历史版本日志，严禁删除、重排或覆盖既有历史内容。
- 如需要记录新进展，应在 `项目进展.md` 末尾追加新版本节点。
- `TASKS.md` 只记录当前可执行任务，不写长篇方案正文。
- `PROGRESS.md` 记录当前状态、已完成、卡点、下一步。
- `TASK_HANDOFF.md` 记录交接上下文，保证其他 Agent 可恢复。
- `VALIDATION.md` 记录验证命令和通过标准。

## Codex CLI 权限策略

Hermes 调度 Codex CLI 或其他 Agent 接力执行时，必须遵守以下策略：

- 默认使用 `codex exec --sandbox workspace-write` 执行开发任务（旧的 `--sandbox workspace-write` 已废弃，等价于 `--sandbox workspace-write`）。
- `--sandbox workspace-write` 是本项目默认自动执行模式；正常开发任务不应再逐次请求人工授权。
- 在当前 Git 项目根目录内，普通文件读取、普通文件写入、Markdown 更新、代码修改、测试、lint、build、代码生成脚本和只读检查脚本应自动执行。
- 依赖安装规则：`requirements*.txt`、`pyproject.toml`、`package.json`、锁文件或项目文档中已经声明的依赖，属于项目已知依赖，可自动安装；未在项目中声明、来源不明或需要外网下载非包管理器资源的依赖，才需要人工确认。
- 只有本节下方“必须停止并请求人工确认”的高风险操作才需要人工确认。
- 调用 Codex CLI 时必须直接调用 `codex exec --sandbox workspace-write "任务内容"`，不要通过 `python -c`、`python - <<EOF`、`node -e`、`perl -e`、shell command substitution、动态 eval、临时脚本执行等方式拼接或生成 Codex 命令。
- 如果任务提示过长，优先精简为短任务说明；不要用 `python -c` 读取文件再拼成命令。
- 如果 Hermes 因长提示生成了带 `-c`、`-e`、`eval`、`$()`、反引号或 heredoc 的 Codex 启动命令，应视为命令构造错误，立即改用直接 `codex exec --sandbox workspace-write "短任务内容"`，而不是请求授权。
- 不使用 `--dangerously-bypass-approvals-and-sandbox`。
- 不使用 `--sandbox danger-full-access`。
- 所有任务必须在当前 Git 项目根目录中运行。
- 当前项目 Windows 路径为 `D:\items\QW`。
- 当前项目 WSL 路径为 `/mnt/d/items/QW`。
- Hermes 与 Codex CLI 必须在 WSL 路径 `/mnt/d/items/QW` 下运行。
- 执行任务前必须确认当前目录存在 `.git`。
- 允许自动读写当前项目文件。
- 允许运行测试、lint、build、代码生成脚本和只读检查脚本。
- 允许创建任务要求内的 Markdown、Python、前端、配置样例和测试文件。
- 允许读取项目内日志、文档、源码和测试输出。
- 不允许越过当前 Git 项目根目录读写无关文件，除非用户明确指定。
- 不允许使用危险绕过参数换取便利。
- 如果环境对普通安全任务的 `codex exec --sandbox workspace-write` 返回 `BLOCKED: User denied. Do NOT retry.`，这表示 Hermes/Codex CLI 运行环境没有按本项目默认策略放行 `--sandbox workspace-write`，属于环境授权配置问题，不代表该普通安全任务需要逐次人工确认。
- 对 `BLOCKED: User denied. Do NOT retry.` 不进入 30 分钟自动重试，不改用危险参数绕过；应提示用户在当前环境中允许 `codex exec --sandbox workspace-write` 执行本项目内普通开发任务。
- 用户放行 `codex exec --sandbox workspace-write` 后，Hermes 可以重新调用 Codex CLI 继续同一个任务。
- 如果 Codex CLI 只是可选执行员，而当前 Agent 能直接完成同一个安全任务，可以记录阻断原因后由当前 Agent 继续完成；不得因此跳过必要验证、状态更新或交接记录。
- 如果环境提示 `Dangerous Command` 的原因是 `script execution via -e/-c flag`，通常说明 Hermes 把 Codex CLI 调用包装成了 `python -c`、`node -e` 等动态脚本。不要选择永久允许这类模式；应改写命令，直接调用 `codex exec --sandbox workspace-write "任务内容"`。

遇到以下操作必须停止并请求人工确认：

- 删除大量文件。
- 批量移动或重命名大量文件。
- 修改生产环境配置。
- 访问、输出、复制或上传密钥、token、密码。
- 执行数据库迁移、清库、批量更新、批量删除。
- 安装未知来源依赖。
- 修改系统级环境变量、注册表、计划任务或系统服务。
- 访问外部网络下载依赖、模型、脚本或二进制文件。
- 启用真实邮件发送、真实客户触达或生产 CRM 写入。
- 对真实客户数据做不可逆清洗、覆盖、合并或脱敏替换。
- 用 `python -c`、`node -e`、`perl -e`、`eval`、`$()`、反引号或 heredoc 动态拼接并执行 Codex CLI 启动命令。

以下操作在本项目中不需要额外人工确认，可按任务需要自动执行：

- Git 提交。
- 推送远程仓库。
- 创建 Git tag 或发布 release。
- 普通数据库写入。
- 安装项目已声明依赖，例如 `pip install -r backend/requirements.txt` 或等价命令。

如果任务因权限、网络、登录、数据库、密钥或人工确认卡住：

- 立即停止高风险动作。
- 在 `TASK_HANDOFF.md` 记录卡点、已完成步骤、未完成步骤、需要人工确认的具体事项。
- 在 `PROGRESS.md` 更新当前状态和下一步建议。
- 不得通过危险参数或绕过沙箱继续执行。

## 运行监控规则（gateway + cron 循环）

无人值守由 gateway 每 60 秒 tick 驱动，每个 cron tick 是一次性独立执行，不需要也无法在单次会话里自我轮询。规则：

- 每个 tick 只做 `TASKS.md` 第一个未完成任务，按 VALIDATION.md 验证、更新状态与日志后结束，下一 tick 自动继续（间隔 2 分钟，近似连续）。
- 每个 tick 必须用中文向 `logs/codex-run.log` 追加记录（至少开始一条、结束或失败一条），tick 内多步时关键节点都应中文记录。
- 失败（含网络/模型临时断开、进程退出）也必须如实写入 `logs/codex-run.log` 和 `logs/codex-retry.log`，不得写成成功；严禁"假绿"。
- 真实进度以 `TASKS.md` 勾选 + `logs/codex-run.log` 实际内容 + 产出文件为准，不以 cron `last_status` 为准。
- 查看运行：`hermes cron list`、`hermes cron status`、`~/.hermes/cron/output/<job_id>/`。

`logs/codex-run.log` 每条记录必须用中文，尽量包含：

- 时间
- 当前任务（任务号）
- 本轮做了什么
- 成功或失败（失败要写原因）
- 下一步动作

## Token / Rate Limit 自动重试规则

如果 Codex CLI 返回以下错误：

- token 不足
- rate limit
- quota
- temporarily unavailable
- 429
- usage limit
- 模型额度不足
- 上下文不足
- 网络临时错误

必须执行以下流程：

1. 不要放弃任务。
2. 立即记录当前时间、错误类型、错误内容、当前任务、当前 git diff 摘要。
3. 更新 `TASK_HANDOFF.md`。
4. 追加 `logs/codex-retry.log`。
5. 不在会话内死等重试：本轮失败就如实记录后结束，由 gateway 的 cron 周期（如 every 2m）在下一轮自动重试——这正是循环存在的意义，断网不丢任务。
6. 每轮（每个 cron tick）开始前必须重新读取 `TASKS.md`、`PROGRESS.md`、`TASK_HANDOFF.md`、`git status`、`git diff`、`logs/codex-retry.log`。
7. 恢复后继续 `TASKS.md` 中第一个未完成任务。
8. 如果同一任务连续多轮（建议 6 轮）都失败，在 `TASK_HANDOFF.md` 记录需要人工处理；是否暂停 cron（`hermes cron pause <job_id>`）由人工决定。
9. 失败后不要清理临时文件，不要回滚代码。

以下情况不得按本节自动重试：

- `BLOCKED: User denied. Do NOT retry.`
- 登录失败
- 需要人工授权
- 危险命令被拦截
- 权限不足且无法判断风险

这些情况必须进入“Full-Auto 环境阻断处理规则”。

`logs/codex-retry.log` 每条记录必须尽量包含：

- 时间
- 错误类型
- 错误内容
- 当前任务
- 重试次数
- 下一次重试时间
- 是否恢复

## Codex CLI 意外停止恢复规则

如果 Codex CLI 进程异常退出、终端中断、无结果返回或长任务停止：

1. 读取最近 `logs/codex-run.log`。
2. 查看 `git status`。
3. 查看 `git diff`。
4. 更新 `TASK_HANDOFF.md`。
5. 判断已完成内容和未完成内容。
6. 如果是普通中断，本轮记录后结束，由下一个 cron tick 继续当前任务。
7. 如果是 token/rate limit/网络临时错误，本轮如实记录后结束，由 cron 周期自动重试。
8. 如果是登录失败、授权、危险命令、权限不足或未知异常，停止并等待人工处理。

## Full-Auto 环境阻断处理规则

如果 Codex CLI 或 Hermes 执行环境返回 `BLOCKED: User denied. Do NOT retry.`：

1. 立即停止该 Codex CLI 调用，不要进入 30 分钟自动重试。
2. 不要改用 `--dangerously-bypass-approvals-and-sandbox` 或 `--sandbox danger-full-access`。
3. 读取 `git status`、`git diff` 和最近 `logs/codex-run.log`。
4. 更新 `TASK_HANDOFF.md`，记录阻断时间、命令、返回信息、当前任务和下一步。
5. 追加 `logs/codex-run.log`，标记为 `BLOCKED_USER_DENIED`。
6. 如果被拦截的是项目内普通开发任务，应提示用户：本项目默认允许 `codex exec --sandbox workspace-write`，请在 Hermes/Codex CLI 环境中放行该自动执行模式。
7. 用户放行后，重新执行同一个 `codex exec --sandbox workspace-write` 任务。
8. 如果当前任务不需要外部 Codex CLI 也能由当前 Agent 安全完成，可以记录“Codex CLI full-auto 被环境阻断，改由当前 Agent 继续”，然后继续执行同一个任务。
9. 不得把该任务自动标记完成，除非实际产出已完成且通过 `VALIDATION.md` 中的验证。

## Codex CLI 命令构造规则

允许的调用形态：

```bash
codex exec --sandbox workspace-write "请执行 TASKS.md 中第一个未完成任务，并按 AGENTS.md 更新状态文件。"
```

禁止的调用形态：

```bash
codex exec --sandbox workspace-write "$(python -c '...')"
codex exec --sandbox workspace-write "$(node -e '...')"
codex exec --sandbox workspace-write "$(cat logs/codex-task2-prompt.txt)"
python -c "..." | codex exec --sandbox workspace-write
eval "codex exec --sandbox workspace-write ..."
```

原因：

- 这些写法会触发环境的 `Dangerous Command` 检查。
- `--sandbox workspace-write` 只代表 Codex 在安全范围内自动执行任务，不代表允许 Hermes 用动态脚本拼接 shell 命令。
- 长提示应写进状态文件，由 Codex 读取；启动命令本身保持短、直接、可审计。

## 完成规则

如果 `TASKS.md` 中所有任务都完成：

1. 运行 `VALIDATION.md` 中的所有最终验证命令。
2. 更新 `TASKS.md`，确认所有任务完成。
3. 更新 `PROGRESS.md`，记录最终完成时间。
4. 生成 `FINAL_REPORT.md`。
5. `FINAL_REPORT.md` 必须包含完成时间、完成任务列表、修改文件列表、验证命令、验证结果、未解决风险、建议下一步。
6. 在 `logs/codex-run.log` 末尾追加 `ALL TASKS COMPLETED: 当前时间`。
7. 停止继续调用 Codex CLI，等待人工确认。

## 安全与权限规则

- 不允许删除大量文件。
- 不允许重置 git 历史或丢弃未确认改动。
- 不允许修改生产环境配置或密钥。
- 不允许在文档中暴露真实 API Key、数据库密码、客户敏感信息、内部底价、未脱敏客户报价。
- 真实客户案例进入邮件知识库前必须脱敏。
- 邮件 SMTP 真实发件出口必须由环境变量 `MAIL_REAL_SENDING_ENABLED` 控制，默认 false，仅人工灰度审批后才能置 true。

  **⚠️ 关键区分（防止把"运行时关闭"误读成"代码层不接入"，从而把整个系统做成空壳）：**

  - 必须做：SMTP 真发出口默认关闭、草稿默认进入人工审核队列、生产 CRM 写入要人工确认。
  - **不能做**：以"默认关闭真实发送"为由，把 LLM 调用、CRM 查询、Few-Shot 检索、前端面板绑后端 API、数据库种子灌库等代码层接入也跳过。这些是产品可用的前提，不可以用 Mock 拼装、静态字典、页面内常量、契约骨架替代。
  - 判断准则：一个任务做完后，如果"打开浏览器看到的界面"和"任务做之前"在数据来源上没有任何变化（还是写死的 Mock），那这个任务就没真做完——哪怕单测和契约校验全部通过。
