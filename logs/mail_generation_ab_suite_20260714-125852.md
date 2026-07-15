# A/B 实测 A：邮件套装生成（customer-suite test=1 单封）

- 执行时间（北京时间）：2026-07-14T12:58:52+08:00
- 记录来源：mail_autosend_plan_item.item_id=20c9a86c-7c6f-4a10-9c62-d8843f513500
- 客户/联系人编号：KH23722-005
- contact_id：KH23722-005
- 套装：new_business_promotion
- 封次：1
- 原排期生成时间：2026-07-14 10:41:07.825350
- 原排期状态：sent
- 原排期收件邮箱域名：danaher.com
- 原排期收件邮箱 SHA-256：2dfcc23f4ff9c84620aac30d9653d43db95ab6a1bfea4f3fb14b0df52d6e0151
- 调用方式：get_mail_customer_suite(test=True, step=固定封次) → _build_mail_generate_draft_response → 注入真实销售签名
- 是否覆盖现有草稿：否
- 是否写 CRM/发送：否

## 实际传给公共生成器的请求

```json
{
  "customer_key": "KH23722-005",
  "contact_email": "[REDACTED_EMAIL]",
  "cc_emails": [],
  "scenario": "new_business_promotion",
  "suite_step": 1,
  "current_seller_name": "事必达销售",
  "current_seller_signature": "事必达销售",
  "contact_email_domain": "danaher.com",
  "contact_email_sha256": "5efdc1e422bb2f4a340355bae2edffd61ca44289ff8c467c5a8f4fb1a6a1fe98"
}
```

## 实际生成器返回元数据

- status：drafted
- draft_status：drafted
- llm_status：success
- llm_model_used：deepseek:deepseek-v4-flash
- retrieved_fewshot_id：40d95f74-f533-41ed-8e4a-6943db97d81f
- fewshot_match_score：0.88
- safety.overall_outcome：passed
- safety.status：locked_for_approval
- safety.hard_block：False

## 最终发给 LLM 的 Prompt

- 原始 Prompt 长度：764 字符
- 原始 Prompt SHA-256：`214756e6bd8e075282b2f47eb27d50ba842ce758327160fc3b4a4e4193dc6156`
- 下方仅对个人邮箱、电话号码做脱敏，其余内容保持本次实际调用文本。

```text
撰写商务邮件，
只输出JSON格式，绝对不要包含任何 Markdown 格式包裹（如 ```json 等）：
{"subject": "邮件主题", "paragraphs": ["称呼段", "正文段落1", "正文段落2"]}

【当前邮件脚本】
【结构脚本】
第1封邮件目标：重新建立联系，不销售，不报价，只让客户重新记起事必达。
【正文路径】
1.	单独称呼 swin  ，不要翻译
2.	基于 为客户提供笔译，同传服务 中真实合作经历自然切入 
3.	表达对 丹纳赫商务服 业务的基础了解 
4.	结合 无明确记录 行业特点，提出一个可能持续存在的国际化沟通场景 
5.	简单介绍近期服务案例（仅1-2个） 
6.	低压力收尾 
【AI指令】
你是一名长期服务企业客户的资深客户经理。
根据以下信息：
•	客户姓名：swin 
•	公司名称：丹纳赫商务服 
•	行业：无明确记录 
•	历史合作：为客户提供笔译，同传服务 
•	成功案例：{case_studies} 
撰写一封老客户激活邮件。
要求：
•	像真人商务沟通，不像营销邮件 
•	用历史合作自然切入 
•	不提“最近整理客户资料” 
•	不提“许久未联系” 
•	不堆砌服务介绍 
•	只围绕一个业务场景展开 
•	案例引用1-2个即可 
•	结尾仅询问是否方便作为后续参考供应商

【输出格式硬性要求】
1. 只输出一个 JSON 对象，不要 Markdown，不要代码块，不要解释。
2. JSON 必须同时包含 subject 和 paragraphs 两个字段。
3. subject 必须是可直接发送给客户的中文邮件主题，不能为空，不能是“-”“无主题”“邮件主题”等占位内容，长度建议 12-36 个中文字符。
4. 输出不要有字母表达的变量
```

## 最终包装层输出

### Subject

Swin，事必达翻译服务回顾与近期案例分享

### Body HTML

```html
<p>Swin 您好，</p><p>之前为丹纳赫商务服提供过笔译和同传服务，合作中我们配合得比较顺畅，也让我对贵司的业务有了初步了解。</p><p>考虑到国际化沟通中，无论是内部会议还是对外资料，语言支持往往是一个持续存在的需求，所以想借此机会简单分享两个近期服务案例：我们为一家跨国制造企业提供了全年的同传支持，也为一家生物科技公司完成了紧急笔译项目。</p><p>如果您方便的话，希望将事必达列为后续翻译服务的参考供应商，不知是否合适？期待您的反馈。</p><div class="mail-signature" style="margin-top:16px;color:#004080;font-size:13px;line-height:1.7;"><strong>盛晔 Joyce</strong><br><br>大客户部<br>上海嘉赛科技有限公司(事必达)<br>Phone: +86 21 5489 6060-105,[REDACTED_PHONE]<br>www.speed-asia.com [REDACTED_EMAIL]<br>中国上海徐汇区肇嘉浜路1065号飞雕国际大厦1409室</div>
```

- 原始 Subject SHA-256：`adf8366242c3a4e786c1235d4a02d881fce27f385f9555771b4e6aa721d774f6`
- 原始 Body HTML SHA-256：`386ee50ba6556a8f05ff24c639d3a19476c155de698ba3e7dd22c284ffdbd44a`

## 跨链路核对结论

### 1. Prompt 是否不同

- 本报告邮件套装生成 Prompt：764 字符，SHA-256 `214756e6bd8e075282b2f47eb27d50ba842ce758327160fc3b4a4e4193dc6156`。
- 同客户、同套装、同封次的自动排期 Prompt：764 字符，SHA-256 同为 `214756e6bd8e075282b2f47eb27d50ba842ce758327160fc3b4a4e4193dc6156`。
- 今天 10:41 原自动排期记录保存的 Prompt：764 字符，SHA-256 仍为同一值。
- 结论：这三个实际调用的 Prompt 逐字一致；本次新生成差异不是两条链路存在隐藏 Prompt 分支造成的。

### 2. 排期邮箱是否真的没有进入生成上下文

- 原排期目标邮箱 SHA-256：`2dfcc23f4ff9c84620aac30d9653d43db95ab6a1bfea4f3fb14b0df52d6e0151`。
- 两条生成链路实际请求邮箱 SHA-256：`5efdc1e422bb2f4a340355bae2edffd61ca44289ff8c467c5a8f4fb1a6a1fe98`。
- 两者域名均为 `danaher.com`，但完整邮箱不是同一个。
- 代码原因：排期时选中的 `mail_autosend_plan_item.recipient_email` 没有传给 `_autosend_generate_one`；生成器仅收到 customer_id/scenario/step，随后重新从 CRM 画像取另一邮箱。
- 影响：最终发送邮箱仍是排期邮箱，但 Prompt 中客户称呼可能按另一邮箱的本地部分生成。本次 Prompt 使用了 `swin`，它来自生成器重新取到的邮箱/CRM 画像，并不能证明就是排期目标邮箱对应的人。

### 3. 安全门结果是否真的被包装层丢失

已用不写库的确定性注入验证：让公共生成器返回 `status=blocked_by_recipient_domain_confidentiality_gate`、`hard_block=true`。

- 邮件套装生成外层仍返回 `item.status=success`；blocked 只藏在内层 draft 中。
- 自动排期 `_autosend_generate_one` 最终只返回 `subject/body_html/llm_prompt/recipient_email` 四个字段，完全没有 `status` 或 `safety_guardrail`。
- 后台 worker 随后会把该内容无条件更新为 `mail_autosend_plan_item.status='drafted'`。
- 转 CRM worker只检查正文是否为空，没有重新执行或检查 safety_guardrail。
- 结论：问题真实存在，而且不是理论推测。

### 4. 影响质量但两条新生成链路共同存在的问题

- 返回元数据声称命中了 Few-Shot `40d95f74-f533-41ed-8e4a-6943db97d81f`，分数 0.88；但最终 764 字符 Prompt 中没有该 Few-Shot 的正文。
- 后端也查询并装载了完整黄金邮件和合同案例，但 `_build_mail_draft_llm_full_prompt` 最终只拼接 system prompt、当前模板、输出格式，没有拼接这些范例。
- 当前模板中的 `{case_studies}` 没有替换，原样进入 LLM Prompt。
- `new_business_promotion` 第1封模板正文却写着“老客户激活邮件”“重新建立联系，不销售”，如果使用者期待的是明确的新业务推广，这个模板目标本身会造成系统性偏差。
- 生成邮件质检配置当前 `enabled=false`；而且公共生成器目前直接调用 `_assemble_mail_draft_from_intent_profile`，没有调用已经存在的 `_assemble_mail_draft_with_quality_review`。

### 5. 为什么日常使用会出现“一个长期好、一个长期坏”

本次从头生成证明公共生成器相同，但日常页面不是同一种数据状态：

- 邮件套装生成正常模式优先读取 `mail_customer_suite_draft_edit` 的历史保存稿/人工修改稿，有内容就不重新调用 LLM。
- 自动排期不读取上述保存稿，每个排期项重新生成原始 LLM 草稿。
- 因此使用者实际比较的经常是“经过人工修改或历史筛选的套装稿”与“未经质检的批量原始稿”，而不是同输入的两次新生成。
- 自动排期还可能按规则选择不同套装或只补剩余封次；这些会进一步放大批量质量差异。

