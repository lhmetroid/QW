# case_company 占位重跑记录（2026-07-09）

## 口径

- 只统计客户可见内容：`subject`、`body_html`、`body_text`。
- 不统计 `llm_prompt`，因为它是生成脚本，不是实际邮件正文。
- 不把 `market2@speed-asia.com` 计入变量/占位；它属于签名邮箱残留。

## 重跑前核对

- 自动发送草稿未同步 CRM：5642 封。
- 其中真实 `case_company` 残留：358 封。
- 358 封全部属于销售 `0188`，场景集中在 `new_contact_intro` 第 3 封。
- 套装草稿当前未同步 CRM 且实际正文含 `case_company`：0 封。

## 执行动作

- 已备份 358 封原始记录到 `logs/case_company-rerun-backup-20260709-180736.json`。
- 已清空这 358 封的 `subject`、`body_html`、`llm_prompt`、`generated_at`、`llm_instance_id`，并将状态置为重新生成队列。
- 本机 `127.0.0.1:8071` 当前拒绝连接，未能通过 HTTP 接口启动；但数据库队列已置为 `queued`，后台 worker 已开始认领生成。
- 未写 CRM，未同步 ERP，未影响已转入 CRM 邮件。

## 重跑发起后状态

- 2026-07-09 18:07 初次置队列：358 封 `queued`。
- 后续复核时后台已开始处理：24 封 `drafted`，1 封 `drafting`，333 封 `queued`。
- 这批记录中客户可见内容剩余 `case_company`：0 封。

## 结论

之前“变量/占位 358”在自动发送草稿里确实就是 `case_company` 问题；之前“套装变量/占位 43”不是全部 `case_company`，当前按客户可见正文复核后套装 `case_company` 为 0。
