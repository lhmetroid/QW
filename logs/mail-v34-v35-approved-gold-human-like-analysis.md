# 邮件黄金库模板标准迭代验证：V34 / V35

时间：2026-06-12

## 目标

按邮件黄金库中人工认可的 `full_email` 模板作为标准，调整新业务推广四封邮件脚本与评分逻辑。评价标准改为：

- 是否像真人销售写的亲和商务邮件。
- 是否与人工认可黄金库 `full_email` 的场景、语气和业务表达相近。
- 暂不使用此前以 LLM 成功、fallback 痕迹、语言纯度为主的旧评分逻辑。

## 脚本与评分调整

- `new_business_promotion` 四封模板版本从 v52 升到 v53。
- 生成 prompt 优先注入同场景、人工认可、`full_email` 的黄金库邮件作为风格标准。
- 新评分方法为 `approved_gold_human_likeness_v1`，维度为：
  - `human_affinity`：亲和、自然称呼、低压力表达、少模板感。
  - `approved_gold_similarity`：与人工认可黄金邮件的业务/亲和关键词重合。
  - `scenario_specificity`：是否有具体业务场景。
  - `low_pressure_next_step`：是否低压力收口。
  - `cleanliness_and_safety`：无变量残留、无兜底模板、安全门无红牌。

## V34 首轮结果

- run_id：`37097a19-0bd5-4dcb-8d73-588d8ee8f1d5`
- label：`mail_v34_case1_4steps_approved_gold_human_like`
- provider/model：`openai:gpt-4.1`
- 结果：4/4 成功
- 平均分：64.25
- 模板版本：53

V34 正文已明显比旧脚本更亲和，能写出客户历史、同传设备、行业活动、低压力转发等内容。但验证时发现 `approved_gold_similarity=0`，原因是人工认可 `full_email` 被旧过滤条件漏掉：

- 评审表里是 `review_status=approved`。
- 资产表里部分旧标记 `publishable/allowed_for_generation/usable_for_reply=false`，导致样式参考被排除。
- `fragment_id` 类型不一致，需先转字符串再匹配。
- SQL 先取前 80 条再 Python 过滤 approved，认可样本未落在前 80 条内。

结论：V34 首轮只证明脚本方向有效，但没有真正把人工认可 full_email 注入生成与相似度评分，不能作为最终验证。

## 修正后样本来源

修正后同场景可命中 9 封人工认可 `new_business_promotion/full_email`，包括：

- `mail_gold_v2_077_mail_promo_promo`：Expanded Services from Shanghai Jiasai - Your Translation Partner
- `mail_gold_v2_194_mail_promo_recovered`：同传口译活动等案例分享
- `mail_gold_v2_134_mail_promo_recovered`：500强企业信赖的视频译制服务精选案例
- `mail_gold_v2_094_mail_promo_case_industry`：为您整理的我们27年的部分成功案例
- `mail_gold_v2_062_mail_promo_case_dept`：同传&活动案例
- `mail_gold_v2_099_mail_promo_case_industry`：我们深耕行业27年的部分同传口译案例分享
- `mail_gold_v2_232_mail_promo_recovered`：谢谢电话沟通，强生GSK诺华等都是我们公司的长期客户，希望有机会为您提供服务
- `mail_gold_v2_091_mail_promo_case_industry`：深耕27年的专业印刷服务，邀您探索我们的成功案例
- `mail_gold_v2_157_mail_promo_recovered`：一站式会议活动解决方案|案例展示与服务概览

## V35 修正版结果

因 V34 已落库，修正版自动递增为 V35。

- run_id：`6a247dcd-64ac-40f0-bf0f-b5857f8a4691`
- label：`mail_v35_case1_4steps_approved_gold_human_like_rerun`
- provider/model：`openai:gpt-4.1`
- 结果：4/4 成功
- 平均分：82.50
- 最低分：78.00
- 最高分：84.00
- 模板版本：53

| 步骤 | 分数 | 主题 | 命中黄金库 | 评价 |
|---|---:|---|---|---|
| 1 | 84 | 关于行业活动支持的一个小建议 | `mail_gold_v2_099_mail_promo_case_industry` | 有客户历史、同传设备、行业活动和低压力转发，亲和自然。 |
| 2 | 84 | 关于展会物料一站式支持的参考场景 | `mail_gold_v2_134_mail_promo_recovered` | 场景具体，展会物料、翻译、商务礼品和一站式表达接近黄金库。 |
| 3 | 78 | 关于推进新业务合作的简单建议 | `mail_gold_v2_094_mail_promo_case_industry` | 可用，但“我建议如果您有兴趣尝试其他业务”略像建议说明，亲和度弱于其他三封。 |
| 4 | 84 | 如需国际化沟通支持，欢迎随时联系 | `mail_gold_v2_134_mail_promo_recovered` | 收口自然，保留备选参考和转发给相关团队的低压力路径。 |

## 结论

修正版已起效。四封邮件都能使用人工认可黄金库 `full_email` 作为风格来源，输出比旧脚本更像真人销售写的亲和商务邮件，也能和黄金库中的活动、同传、资料、翻译、本地化、一站式支持等表达形成可解释匹配。

仍建议下一轮重点优化第 3 封，减少“建议说明/方案说明”口吻，改成更自然的“从一个小场景先看”的销售语气。

## 验证命令

```powershell
python -m py_compile backend/main.py
git diff --check -- backend/main.py
$env:PYTHONIOENCODING='utf-8'; python scratch/run_mail_case1_v25_v26.py --provider openai --label mail_v34_case1_4steps_approved_gold_human_like
$env:PYTHONIOENCODING='utf-8'; python scratch/run_mail_case1_v25_v26.py --provider openai --label mail_v35_case1_4steps_approved_gold_human_like_rerun
```

