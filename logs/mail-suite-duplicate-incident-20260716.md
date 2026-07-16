# KH12934-018 套装时间与重复发送只读核查（2026-07-16）

## 结论

- 第1封计划时间：2026-07-15 12:30:00。
- 第1封真实发送成功时间：2026-07-15 13:36:49（CRM `spSendInfo1607.Status=SendSuccess`）。
- 第2、3、4封当前均未实发，状态为 `WaitSend`；ERP/CRM 待发时间分别是 2026-08-03 13:50、2026-08-20 11:50、2026-09-10 09:30。
- 当前没有重复发送，也没有重复待发：该联系人 CRM 待发队列跨所有销售账号恰好3行；销售1607实发分表恰好1条 SendSuccess；待发同主题同计划日重复分组为0。
- 未修改 CRM/ERP、本地排期或真实发送状态。

## 三方状态差异

- `mail_autosend_plan_item` 四行均为 `status=sent`。此处 `sent` 的实际业务含义是“已转入CRM”，不是“已真实发送”。
- `mail_customer_suite_send_plan` 四行均为 `status=enqueued`；第1封本地缓存仍为 `WaitSend`，`status_synced_at=2026-07-15 11:17:01`，早于真实发送时间 13:36:49，因此缓存滞后。
- 第1、4封的 `mail_autosend_plan_item.crm_send_id` 为空，但对应 send_plan/CRM 行已有 SendId；第2、3封本地 plan_item 有 SendId。读接口会再用 send_plan 对齐，所以页面出现“有的已同步、有的待同步/有的能读到ID、有的靠对齐”的混合表现。

## 问题点

1. 状态语义混用：`mail_autosend_plan_item.status='sent'` 表示已入CRM，UI/代码部分位置却按“已发送”理解。
2. 状态缓存滞后：真发发生在最近一次 `sync_send_status` 之后，导致第1封本地仍显示 WaitSend。
3. 读层只对齐状态，不对齐时间：`_autosend_align_crm_status` 命中 send_plan 后把本地行标成 sent/crm_synced，但仍保留本地 `plan_date/plan_time`，因此本地重排时间可能与 ERP 真实 PlanSendTime 同屏冲突。
4. 重排范围过大：`autosend_commit` 调 `_autosend_reschedule_plan` 时按销售重排所有 movable 行，而随后 `_autosend_commit_enqueue` 才按本次 `item_ids` 选择同步；未选中的本地行可能被改期但不会写 ERP。
5. 已入CRM行不会由重排函数更新 ERP：代码明确把 `sent` 当 fixed，不改 CRM `spQueueSend.PlanSendTime`。因此“本地日期变了、ERP日期没变”是现有设计必然结果，不是 ERP 写入延迟。
6. 本联系人入CRM时间早于重排功能提交时间：四封在 2026-07-14 09:42~09:43（北京时间语义）完成入CRM；重排功能提交于 2026-07-14 14:41:24+08:00，因此本联系人最初入队不是由该新功能重排造成。

## 建议修复顺序（本轮未实施）

1. 发送安全：同步前以 `销售+联系人/邮箱+scenario+step` 查询 CRM 队列/实发，存在即禁止再次入队；不要只按主题+计划日去重。
2. 重排隔离：`_autosend_reschedule_plan` 接收并严格限制为本次 `item_ids`，不得改动未选中的行。
3. 权威时间：已入CRM/已发送行展示 CRM `PlanSendTime/FactSendTime`；本地时间只用于未同步行。
4. 状态拆分：至少区分 `crm_enqueued`、`wait_send`、`send_success`、`send_failed/deleted`，停止用 `sent` 同时代表入队和实发。
5. 状态刷新：打开“已用套装”或排期页时先只读刷新目标联系人/SendId，避免使用过期缓存。

## 界面状态复核（第一问题）

- 当前生产接口对 KH12934-018 返回恰好 4 步，四步 status 均为 sent。
- 按当前前端 as2StepBtn 映射，sent/committed 必须显示蓝色“日期+待发”，且不显示选择框。截图中的绿色日期+选择框对应 drafted，与当前后端及 CRM 事实不符。
- 当前接口日期为 07-15、08-03、08-20、09-10；截图显示 07-16、08-04、08-24、09-11。只能确认截图与当前接口不一致；尚无证据判定截图数据来自浏览器缓存、历史接口响应还是当时的后台记录。
- 业务最终状态应为：第1封实际已发送，显示绿色“已发送”；第2至4封仍在 CRM WaitSend，显示蓝色“待发”。当前代码会把第1封继续显示为蓝色，因为本地一旦标记 sent 后状态对齐逻辑会跳过，不再补录 CRM 实际发送状态。

记录时间：2026-07-16 10:18:11

