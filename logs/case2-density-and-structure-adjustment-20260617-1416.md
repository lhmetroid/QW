# 案例2邮件信息密度与结构修正记录

时间：2026-06-17 14:16

## 用户指出的问题

- 之前版本过度追求“安全/克制”，导致邮件像微信短句，信息量不足。
- Step2（一体化服务介绍）和 Step3（近期成功案例）本应适合使用短枚举、多个案例清单，但上一版没有保留这种结构。
- 黄金邮件库理论上应参与学习，但上一轮 case2 日志中 `gold_email_library.items` 为空，实际没有学习到优秀邮件的结构。
- 爱德华早期版本中有“我们可提供以下支持”的枚举结构，这类结构不应被误判为机械服务清单；关键是要嵌入客户业务场景。

## 本轮修正

- `docs/mail_multiturn_sales_email_generation_standard.md`
  - 增加信息密度要求：Step1/Step4 建议 300-450 字，Step2/Step3 建议 420-700 字。
  - 明确 Step2/Step3 可使用短枚举、场景清单、案例清单。
  - 明确“禁止机械服务清单”不等于禁止列表结构。

- `docs/mail_sequence_12_step_purpose_draft.md`
  - 增加黄金邮件库兜底规则：同场景不足时，可跨场景调用已审核 full_email 学习结构。
  - 增加信息密度与结构要求。
  - 在 case2 Step2/Step3 目标中补充短枚举和脱敏案例清单。

- `scratch/run_case2_reactivation_deepseek_with_kb.py`
  - 放宽并增强黄金邮件库检索：同场景为空时，兜底使用 approved full_email 或高分 full_email。
  - 增加 `content_excerpt` 长度，保留更多黄金邮件结构。
  - Round1/Round2 明确要求模型提取黄金邮件的短枚举、案例块和先总后分结构。
  - Round3/Round4 增加正文长度要求，Step2/Step3 允许短枚举。
  - Step3 强制输出 2-3 条脱敏案例清单，每条包含案例场景、参与环节、可借鉴点。
  - 将“董事会资料/董事会会议”限制为 CRM 原始事实，最终正文抽象为治理/披露/投资者沟通资料或股东大会、业绩发布会、投资者沟通会。
  - 收窄过严质量门：不再一刀切拦截“省去”，只保留更具体的风险表达。

## 最新通过样本

- Step2：`logs/case2-suite-deepseek-step2-kb-standard-20260617-141337.md`
  - 质量标记：pass
  - 特点：信息量提升，包含围绕金融/资管客户资料和活动场景的短枚举。

- Step3：`logs/case2-suite-deepseek-step3-kb-standard-20260617-141200.md`
  - 质量标记：pass
  - 特点：包含案例清单结构，已恢复“案例/枚举”表达。

## 注意点

- 当前合作案例库直接金融/资管案例不足，Step3 主要依赖跨行业活动案例做行业化迁移。
- 这能验证“让 AI 发挥 + 学黄金邮件结构”的方向，但后续要进一步稳定 Step3 质量，应补充金融/资管相关真实脱敏案例。

## 验证

- `python -m py_compile scratch\run_case2_reactivation_deepseek_with_kb.py` 通过。
- `git diff --check -- docs\mail_sequence_12_step_purpose_draft.md docs\mail_multiturn_sales_email_generation_standard.md scratch\run_case2_reactivation_deepseek_with_kb.py` 通过。

