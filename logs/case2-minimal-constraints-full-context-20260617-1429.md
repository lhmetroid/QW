# 案例2最小限制与完整上下文复测

- 时间：2026-06-17 14:29
- 脚本：`scratch/run_case2_reactivation_deepseek_with_kb.py`
- 命令：`python scratch\run_case2_reactivation_deepseek_with_kb.py --steps 2,3`
- 模型：DeepSeek Chat Completions API 真实调用

## 本轮修改

按“原则上能不限制就不限制，还有案例、知识库内容给全”的要求，出口质检只保留硬风险：

- 内部编号：客户号、合同号、报价号、ContactId、CustomerId。
- 联系方式：电话、邮箱、联系方式、联系人信息。
- 商务风险：价格、折扣、免费、试译、样稿。
- 事实风险：前序邮件显性承接、客户反馈/客户说、编造近期项目。
- 串场风险：爱德华、Edwards、TAVR、经导管等其他案例专名。

已移除硬禁的内容：

- “完整解决方案”“一体化解决方案”“赋能”“链条”“流程优化”等风格词不再直接判失败。
- “期待您的回复”“董事会资料”“服务链”“省去逐一对接”等不再作为硬拦截。
- Step2/Step3 允许短枚举、案例块和更完整正文。

## 真实调用结果

### Step2：一体化服务介绍

- 文件：`logs/case2-suite-deepseek-step2-kb-standard-20260617-142714.md`
- 质量标记：pass
- 主题：围绕公司治理与投资者沟通，看看哪些环节可以一起配合
- 抽查结论：Round0 给到 20 条合作案例和 10 条黄金邮件长摘录；最终正文保留金融/资管资料、会议、视频、活动物料等业务场景，并使用短枚举，没有压成微信短句。

### Step3：近期成功案例

- 文件：`logs/case2-suite-deepseek-step3-kb-standard-20260617-142820.md`
- 质量标记：pass
- 主题：从文件到活动，一些可以配合的思路
- 抽查结论：最终正文使用 3 条脱敏案例清单，包含案例场景、事必达参与环节、可借鉴点；未写真实客户名、合同号、金额、具体日期，也未写成申万菱信当前项目。

## 仍需注意

黄金邮件库长摘录中仍可能包含未脱敏客户名、品牌名或旧模板占位符。当前最终输出未带出这些内容，但产品化时更稳的做法是：输入给模型前先做脱敏清洗，再保留长文本和结构，不要重新裁成短摘要。

## 验证

- `python -m py_compile scratch\run_case2_reactivation_deepseek_with_kb.py`：通过
- `git diff --check -- docs\mail_sequence_12_step_purpose_draft.md docs\mail_multiturn_sales_email_generation_standard.md scratch\run_case2_reactivation_deepseek_with_kb.py`：通过
