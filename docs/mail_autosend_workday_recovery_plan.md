# 自动排期工作日跳过与存量回收分析方案

## 目标

- 后续新增自动排期默认跳过周六、周日和配置的中国法定节假日。
- 存量排期本轮只做只读分析, 不回写本地库, 不修改 CRM 待发队列。
- 后续如人工确认执行回收, 原则为每个销售独立、原日期靠前优先、往后移到最近工作日、每天上限 50 封。

## 新增配置

- `mail_autosend_config.skip_non_workdays`: 是否跳过非工作日, 默认 `true`。
- `mail_autosend_config.holiday_dates_csv`: 额外跳过日期, 格式 `YYYY-MM-DD`, 支持逗号或空白分隔。
- 前端自动排期区新增“跳过周末/节假日”开关和“节假日”输入框。

说明: 中国法定节假日每年由国家公布并可能调休, 当前实现不硬编码年度假日表, 由配置写入需要跳过的具体日期, 确保后续每年可按官方安排更新。

## 后续新增排期规则

新增自动排期调用 `_autosend_schedule()` 时会先把目标日移动到最近工作日:

1. 如果目标日是周六、周日或配置节假日, 向后找最近工作日。
2. 如果该销售在该日已有排期达到每日上限, 继续逐日向后找最近工作日。
3. 每个销售的每日上限独立计算, 不与其他销售混用。
4. 只影响新生成/预览的排期, 不自动改动已存在的本地 plan item 或 CRM OutBox 行。

## 存量回收只读分析接口

新增只读接口:

```text
GET /api/v1/mail/autosend/workday-recovery-analysis?daily_cap=50&days=180
```

常用参数:

- `staff_id`: 为空时分析全部销售, 填销售工号时只分析该销售。
- `start`: 起始日期, 默认北京时间当天。
- `days`: 分析天数, 默认 180, 最大 366。
- `daily_cap`: 每销售每日上限, 默认 50。
- `include_local`: 是否纳入本地 `mail_autosend_plan_item`, 默认 1。
- `include_crm`: 是否纳入 CRM `spQueueSend` 待发, 默认 1。
- `skip_non_workdays`: 覆盖配置开关, `1` 跳过, `0` 不跳过。
- `holiday_dates`: 覆盖配置节假日, 格式 `YYYY-MM-DD,YYYY-MM-DD`。

接口返回:

- `mode=analysis_only`
- `wrote_to_db=false`
- `updated_crm=false`
- `changes`: 需要变化的记录清单, 含来源、原日期、新日期、原因。
- `staff_summaries`: 每个销售独立汇总。
- `day_load`: 模拟回收后的每销售每日封数。

## 回收排序原则

每个销售单独排序:

1. 原计划日期靠前的优先。
2. 同一天内原计划时间靠前的优先。
3. 本地预排记录优先于 CRM 待发行。
4. 再按创建时间和记录 ID 保持稳定排序。

模拟回收时, 每条记录从原日期开始往后找最近工作日; 如果当天已满 50, 继续逐天往后找下一工作日。

## 后续人工确认后可能涉及的数据变化

本轮不执行以下变化。若后续人工明确下令回收, 预计只变更排期时间相关字段:

- 本地 `mail_autosend_plan_item.plan_date`
- 本地 `mail_autosend_plan_item.seq_in_day`
- 本地 `mail_autosend_plan_item.updated_at`
- CRM `spQueueSend.PlanSendTime`
- 如存在本地发送计划镜像, 需同步对应计划发送时间字段

不应修改:

- 收件人、主题、正文、附件、销售归属
- 已实发邮件
- 非本系统 AI 入队的 CRM 邮件
- 已经人工确认不调整的记录

实际回收前建议先导出接口返回的 `changes` 作为人工审核清单, 再按销售分批执行。
