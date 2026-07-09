# 已转入 CRM 邮件的销售改动率分析

时间：2026-07-09
范围：只读统计，不修改代码、不改数据库结构、不写 CRM。
口径：分母只计算已经转入 CRM 或已经写入 CRM 待发队列的邮件。

## 1. 分母定义

本次不再用全部 LLM 生成数做分母，而是使用“所有转入 CRM 邮件数”：

- 自动排期：`mail_autosend_plan_item` 中 `status in ('sent','committed','crm_sent','sent_done','send_success')`，或存在 `crm_send_id/committed_at`。
- 套装排期：`mail_customer_suite_send_plan` 中 `status='enqueued'`，或存在 `crm_send_id`。`duplicate_skipped` 不计入本次分母。

人工改动匹配方式：

- 自动排期：优先用 `llm_instance_id = mail_llm_edit_record.instance_id` 精确匹配。
- 套装排期：当前发送计划表没有保存 `llm_instance_id`，只能用 `customer_id + scenario + suite_step + inputer_staff_id` 业务键匹配人工编辑记录，因此属于近似统计。后续建议把 `llm_instance_id` 写入 `mail_customer_suite_send_plan`。

## 2. 总体结果

| 指标 | 数量 |
| --- | ---: |
| 已转入 CRM 邮件总数 | 4549 |
| 其中有人工作改动 | 968 |
| 按 CRM 分母计算改动率 | 21.3% |

## 3. 按来源

| 来源 | 转入 CRM 邮件数 | 有改动 | 改动率 |
| --- | --- | --- | --- |
| autosend | 1772 | 673 | 38.0% |
| mail_suite | 2777 | 295 | 10.6% |

## 4. 按销售改动率

| 销售 | 转入 CRM 邮件数 | 有改动 | 改动率 | 自动排期数 | 套装排期数 |
| --- | --- | --- | --- | --- | --- |
| 0017 | 1198 | 213 | 17.8% | 367 | 831 |
| 0188 | 990 | 180 | 18.2% | 474 | 516 |
| 1607 | 871 | 257 | 29.5% | 227 | 644 |
| 0002 | 835 | 155 | 18.6% | 405 | 430 |
| 0141 | 655 | 163 | 24.9% | 299 | 356 |

## 5. 改动类型汇总

说明：一封邮件可能同时命中多个类型，例如既改称呼又改签名，所以类型合计会大于“有改动邮件数”。类型判断基于原文和最终文之间的变化，不是只看邮件中是否出现关键词。

| 改动类型 | 命中次数 | 占有改动邮件比例 |
| --- | --- | --- |
| 正文改动 | 955 | 98.7% |
| 签名/联系方式调整 | 472 | 48.8% |
| 称呼/语言风格调整 | 171 | 17.7% |
| 业务线/服务描述调整 | 90 | 9.3% |
| 主题改动 | 86 | 8.9% |
| 结尾动作/语气调整 | 46 | 4.8% |
| 占位/测试痕迹处理 | 22 | 2.3% |
| 明显缩短 | 4 | 0.4% |
| 明显加长 | 2 | 0.2% |

## 6. 按销售 + 改动类型

| 销售 | 转入 CRM 邮件数 | 有改动 | 改动率 | 主要改动类型 |
| --- | --- | --- | --- | --- |
| 1607 | 871 | 257 | 29.5% | 正文改动 257；签名/联系方式调整 253；主题改动 17；称呼/语言风格调整 17；业务线/服务描述调整 15；结尾动作/语气调整 6；占位/测试痕迹处理 6；明显加长 1 |
| 0017 | 1198 | 213 | 17.8% | 正文改动 213；签名/联系方式调整 41；称呼/语言风格调整 24；结尾动作/语气调整 14；业务线/服务描述调整 5；主题改动 2；明显加长 1 |
| 0188 | 990 | 180 | 18.2% | 正文改动 180；称呼/语言风格调整 39；签名/联系方式调整 28；占位/测试痕迹处理 16；业务线/服务描述调整 10；主题改动 2；结尾动作/语气调整 2 |
| 0141 | 655 | 163 | 24.9% | 正文改动 163；签名/联系方式调整 146；称呼/语言风格调整 42；结尾动作/语气调整 5；业务线/服务描述调整 3 |
| 0002 | 835 | 155 | 18.6% | 正文改动 142；主题改动 65；业务线/服务描述调整 57；称呼/语言风格调整 49；结尾动作/语气调整 19；签名/联系方式调整 4；明显缩短 3 |

## 7. 按来源/场景/轮次

| 来源 | 场景 | 轮次 | 转入 CRM 邮件数 | 有改动 | 改动率 |
| --- | --- | --- | --- | --- | --- |
| autosend | new_business_promotion | 1 | 124 | 75 | 60.5% |
| autosend | new_contact_intro | 1 | 118 | 56 | 47.5% |
| autosend | re_activation | 1 | 203 | 94 | 46.3% |
| autosend | new_business_promotion | 2 | 123 | 51 | 41.5% |
| autosend | new_business_promotion | 3 | 122 | 49 | 40.2% |
| autosend | new_contact_intro | 2 | 118 | 47 | 39.8% |
| autosend | new_business_promotion | 4 | 123 | 45 | 36.6% |
| autosend | new_contact_intro | 3 | 119 | 43 | 36.1% |
| autosend | re_activation | 2 | 202 | 65 | 32.2% |
| autosend | re_activation | 3 | 201 | 58 | 28.9% |
| autosend | re_activation | 4 | 200 | 57 | 28.5% |
| autosend | new_contact_intro | 4 | 119 | 33 | 27.7% |
| mail_suite | re_activation | 2 | 373 | 60 | 16.1% |
| mail_suite | re_activation | 4 | 359 | 52 | 14.5% |
| mail_suite | new_business_promotion | 4 | 174 | 21 | 12.1% |
| mail_suite | re_activation | 3 | 357 | 39 | 10.9% |
| mail_suite | new_business_promotion | 3 | 178 | 18 | 10.1% |
| mail_suite | new_business_promotion | 2 | 180 | 16 | 8.9% |
| mail_suite | re_activation | 1 | 336 | 27 | 8.0% |
| mail_suite | new_contact_intro | 2 | 163 | 13 | 8.0% |
| mail_suite | new_business_promotion | 1 | 163 | 12 | 7.4% |
| mail_suite | new_contact_intro | 3 | 162 | 11 | 6.8% |
| mail_suite | new_contact_intro | 4 | 162 | 11 | 6.8% |
| mail_suite | new_contact_intro | 1 | 165 | 11 | 6.7% |

## 8. 结论

1. 用“已转 CRM 邮件”为分母后，整体人工改动率为 21.3%，比用全部生成数更贴近真实落地质量。
2. 销售维度差异需要结合转入数量看：低分母销售的高改动率不一定代表脚本更差，优先看转入量较大的销售。
3. 改动类型里“正文改动”占绝大多数；签名/联系方式、称呼、业务线和结尾动作是后续脚本最值得拆细优化的方向。
4. 套装排期的匹配目前是业务键近似，不如自动排期的 `llm_instance_id` 精确；后续脚本/表结构应补上该字段，否则销售维度统计会有误差。

## 9. 建议脚本调整方向

1. 先把签名和正文彻底分离，避免不同销售反复改联系方式和署名。
2. 按销售统计高频改动类型，给销售个性化默认签名、称呼语言和 CTA 风格。
3. 对新业务推广按业务线生成，不要一封邮件堆太多服务。
4. 每日统计只纳入已转 CRM 邮件，排除未落地草稿和清空排期记录。
5. 为 `mail_customer_suite_send_plan` 增加 `llm_instance_id` 或编辑记录外键，再做精确的销售改动率看板。

## 10. 本次输出文件

- 明细 JSON：`logs/mail_llm_crm_sales_edit_stats_20260709.json`
- 当前报告：`logs/mail_llm_crm_sales_edit_stats_20260709.md`
