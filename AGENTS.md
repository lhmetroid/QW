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

- 每次只处理一个明确的小任务，优先完成 `TASKS.md` 中第一个未完成任务。
- 修改前先确认当前 git 工作区状态，避免覆盖用户或其他 Agent 的改动。
- 修改代码或文档前先理解现有结构，不做无关重构。
- 修改完成后必须按 `VALIDATION.md` 运行对应验证。
- 每完成一个任务，必须更新 `PROGRESS.md`。
- 如果任务中断、失败、等待授权、上下文不足或需要交给其他工具继续，必须更新 `TASK_HANDOFF.md`。
- 不允许把 Mock 数据、推演数据、示例数据描述成真实生产数据。
- Git 提交、推送远程仓库、创建 tag、发布 release 可按任务需要执行，不需要额外人工授权；但不得在无任务需要时随意执行。

## Hermes 短启动指令

以后在 Hermes 中启动任务时，优先使用下面这段短指令，不要每次粘贴长规则：

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
11. 如果遇到登录失败、需要人工授权、危险命令、删除大量文件、修改生产环境配置、访问密钥、数据库迁移/清库/批量更新/批量删除，停止并写入 TASK_HANDOFF.md，不要自动继续。
12. 如果所有任务完成，生成 FINAL_REPORT.md，并在 logs/codex-run.log 末尾追加 ALL TASKS COMPLETED: 当前时间。

现在开始执行第一个未完成任务。目标是保证任务持续推进和可恢复，最终完成全部计划代码修改。
```

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

建议表或模型边界：

- `mail_raw_messages`：邮件原始记录或外部邮件 ID 映射
- `mail_cleaned_messages`：去噪后的邮件正文
- `mail_gold_snippets`：邮件黄金 Few-Shot 切片
- `mail_customer_profiles`：邮件侧 CRM 画像缓存或映射
- `mail_sequences`：客户邮件激活状态机
- `mail_sequence_steps`：4 轮套装步骤执行记录
- `mail_drafts`：邮件草稿
- `mail_safety_events`：价格、工期、收件域名、安全门事件
- `mail_feedback_events`：人工纠偏、点赞、差评、反哺记录
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

- 物理隔离防幻觉：价格、工期、折扣、账期等高风险内容不得完全交给大模型自由生成。
- 断点续传防崩溃：邮件采矿、清洗、向量化、打分等批处理必须支持断点续跑。
- 宽进严出避错杀：原始邮件清洗允许保留候选，但生成出口必须强校验。
- 人环协作兜底线：销售或运营必须能审核、修正、锁定、终止邮件草稿。
- 先质量验证后 API 联调：先证明邮件质量、Few-Shot、清洗和安全门稳定，再开放 CRM 联调。

## 文档维护规则

- `项目进展.md` 是历史版本日志，严禁删除、重排或覆盖既有历史内容。
- 如需要记录新进展，应在 `项目进展.md` 末尾追加新版本节点。
- `TASKS.md` 只记录当前可执行任务，不写长篇方案正文。
- `PROGRESS.md` 记录当前状态、已完成、卡点、下一步。
- `TASK_HANDOFF.md` 记录交接上下文，保证其他 Agent 可恢复。
- `VALIDATION.md` 记录验证命令和通过标准。

## Codex CLI 权限策略

Hermes 调度 Codex CLI 或其他 Agent 接力执行时，必须遵守以下策略：

- 默认使用 `codex exec --full-auto` 执行开发任务。
- `--full-auto` 是本项目默认自动执行模式；正常开发任务不应再逐次请求人工授权。
- 在当前 Git 项目根目录内，普通文件读取、普通文件写入、Markdown 更新、代码修改、测试、lint、build、代码生成脚本和只读检查脚本应自动执行。
- 依赖安装规则：`requirements*.txt`、`pyproject.toml`、`package.json`、锁文件或项目文档中已经声明的依赖，属于项目已知依赖，可自动安装；未在项目中声明、来源不明或需要外网下载非包管理器资源的依赖，才需要人工确认。
- 只有本节下方“必须停止并请求人工确认”的高风险操作才需要人工确认。
- 调用 Codex CLI 时必须直接调用 `codex exec --full-auto "任务内容"`，不要通过 `python -c`、`python - <<EOF`、`node -e`、`perl -e`、shell command substitution、动态 eval、临时脚本执行等方式拼接或生成 Codex 命令。
- 如果任务提示过长，优先精简为短任务说明；不要用 `python -c` 读取文件再拼成命令。
- 如果 Hermes 因长提示生成了带 `-c`、`-e`、`eval`、`$()`、反引号或 heredoc 的 Codex 启动命令，应视为命令构造错误，立即改用直接 `codex exec --full-auto "短任务内容"`，而不是请求授权。
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
- 如果环境对普通安全任务的 `codex exec --full-auto` 返回 `BLOCKED: User denied. Do NOT retry.`，这表示 Hermes/Codex CLI 运行环境没有按本项目默认策略放行 `--full-auto`，属于环境授权配置问题，不代表该普通安全任务需要逐次人工确认。
- 对 `BLOCKED: User denied. Do NOT retry.` 不进入 30 分钟自动重试，不改用危险参数绕过；应提示用户在当前环境中允许 `codex exec --full-auto` 执行本项目内普通开发任务。
- 用户放行 `codex exec --full-auto` 后，Hermes 可以重新调用 Codex CLI 继续同一个任务。
- 如果 Codex CLI 只是可选执行员，而当前 Agent 能直接完成同一个安全任务，可以记录阻断原因后由当前 Agent 继续完成；不得因此跳过必要验证、状态更新或交接记录。
- 如果环境提示 `Dangerous Command` 的原因是 `script execution via -e/-c flag`，通常说明 Hermes 把 Codex CLI 调用包装成了 `python -c`、`node -e` 等动态脚本。不要选择永久允许这类模式；应改写命令，直接调用 `codex exec --full-auto "任务内容"`。

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

## 运行监控规则

Codex CLI 长任务必须后台运行并监控。

监控频率：

- 每 2 分钟检查一次 Codex CLI 进程状态。
- 每 5 分钟读取一次 Codex 日志。
- 每 5 分钟将当前状态追加到 `logs/codex-run.log`。
- 每 5 分钟更新 `PROGRESS.md`。
- 如果 Codex 没有新输出，也要记录“仍在运行，无新日志”。

`logs/codex-run.log` 每条记录必须尽量包含：

- 时间
- 当前任务
- 当前小点
- Codex CLI 状态
- 最近输出摘要
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
5. 每 30 分钟尝试一次 Codex CLI 是否恢复。
6. 每次重试前必须重新读取 `TASKS.md`、`PROGRESS.md`、`TASK_HANDOFF.md`、`git status`、`git diff`、`logs/codex-retry.log`。
7. 如果恢复，继续 `TASKS.md` 中第一个未完成任务。
8. 如果连续失败 6 次，停止继续重试，并在 `TASK_HANDOFF.md` 中记录需要人工处理。
9. 停止后不要清理临时文件，不要回滚代码，等待人工确认。

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
6. 如果是普通中断，重新调用 Codex CLI 继续当前小任务。
7. 如果是 token/rate limit，进入 30 分钟重试策略。
8. 如果是登录失败、授权、危险命令、权限不足或未知异常，停止并等待人工处理。

## Full-Auto 环境阻断处理规则

如果 Codex CLI 或 Hermes 执行环境返回 `BLOCKED: User denied. Do NOT retry.`：

1. 立即停止该 Codex CLI 调用，不要进入 30 分钟自动重试。
2. 不要改用 `--dangerously-bypass-approvals-and-sandbox` 或 `--sandbox danger-full-access`。
3. 读取 `git status`、`git diff` 和最近 `logs/codex-run.log`。
4. 更新 `TASK_HANDOFF.md`，记录阻断时间、命令、返回信息、当前任务和下一步。
5. 追加 `logs/codex-run.log`，标记为 `BLOCKED_USER_DENIED`。
6. 如果被拦截的是项目内普通开发任务，应提示用户：本项目默认允许 `codex exec --full-auto`，请在 Hermes/Codex CLI 环境中放行该自动执行模式。
7. 用户放行后，重新执行同一个 `codex exec --full-auto` 任务。
8. 如果当前任务不需要外部 Codex CLI 也能由当前 Agent 安全完成，可以记录“Codex CLI full-auto 被环境阻断，改由当前 Agent 继续”，然后继续执行同一个任务。
9. 不得把该任务自动标记完成，除非实际产出已完成且通过 `VALIDATION.md` 中的验证。

## Codex CLI 命令构造规则

允许的调用形态：

```bash
codex exec --full-auto "请执行 TASKS.md 中第一个未完成任务，并按 AGENTS.md 更新状态文件。"
```

禁止的调用形态：

```bash
codex exec --full-auto "$(python -c '...')"
codex exec --full-auto "$(node -e '...')"
codex exec --full-auto "$(cat logs/codex-task2-prompt.txt)"
python -c "..." | codex exec --full-auto
eval "codex exec --full-auto ..."
```

原因：

- 这些写法会触发环境的 `Dangerous Command` 检查。
- `--full-auto` 只代表 Codex 在安全范围内自动执行任务，不代表允许 Hermes 用动态脚本拼接 shell 命令。
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
- 邮件发信相关能力必须默认关闭真实发送，先使用草稿或 Mock 模式验证。
