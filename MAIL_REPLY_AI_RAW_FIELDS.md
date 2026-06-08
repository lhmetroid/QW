# 邮件回复AI对接字段说明：原始邮件字段版

记录时间：2026-06-08

本文用于给“回复AI”所在项目整理邮件智能回复场景的可用字段。当前只是字段说明和对接样例，不代表已经接入回复AI。与企微实时回复不同，邮件侧当前没有 `thread_fact` 这样的会话事实层；邮件生成更接近“原始邮件/CRM字段 + 场景/Sequence步骤 + 草稿生成配置 + 安全门”的直接输入。

> 同内容副本保存到 `docs/mail_reply_ai_raw_fields.md`。当前 `.gitignore` 忽略 `docs/` 目录，因此根目录本文用于降低后续接力丢失风险。

## 总体判断

邮件侧目前可给回复AI的字段主要分三类：

1. 原始邮件字段：来自 `mail_raw_unified`，包括主题、发件人、收件人、抄送、发送时间、正文、附件标记、来源和原始payload路径。
2. 清洗辅助字段：来自 `mail_cleaned`，包括主正文、引用正文、清洗后正文、发件方识别、客户编号和清洗状态。虽然经过清洗，但仍是从原始邮件抽取出来的文本字段，不是LLM摘要。
3. 生成上下文字段：来自邮件草稿请求、CRM画像、Sequence策略、模板脚本、Few-Shot命中和安全门。后续回复AI如果逻辑未知，应尽量同时提供原始邮件字段和这些结构化上下文。

如果对方回复AI希望“直接根据原始邮件生成回复”，当前满足基础条件：可以提供 `subject`、`from_email`、`to_emails`、`cc_emails`、`sent_at`、`body_text`、`body_main_text`、`body_text_clean` 等字段。

## 当前主要接口与表

| 对象 | 作用 | 备注 |
| --- | --- | --- |
| `mail_raw_unified` | 邮件原始统一记录表 | 原始邮件来源，约80万行 |
| `mail_cleaned` | 邮件清洗表 | 去噪正文、发件方识别、客户编号等 |
| `GET /api/raw_comm/mail/messages/{mail_uid}` | 单封邮件原始详情接口 | 可取原始与清洗后的字段 |
| `POST /api/v1/mail/generate-draft` | 邮件草稿生成接口 | 当前主邮件草稿生成链路 |
| `GET /api/v1/mail/customer-suite?id=...` | 独立客户套装页接口 | 按客户编号生成4封套装草稿 |
| `mail_iteration_draft` | 邮件迭代逐封草稿明细 | 保存请求、prompt、响应、评分、安全门 |
| `mail_customer_suite_feedback` | 客户套装页人工反馈表 | 保存人工反馈和对应草稿快照 |

## 推荐给回复AI的请求体总结构

如果对方回复AI暂未提供固定协议，可先按 model-chat 风格预留：

```json
{
  "model_name": "mail-reply-ai-model-name",
  "messages": [
    {
      "role": "system",
      "content": "邮件回复AI系统指令"
    },
    {
      "role": "user",
      "content": "由原始邮件字段、CRM画像、邮件场景和输出要求拼成的中文上下文"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 800
}
```

更推荐后续给对方项目同时提供结构化JSON：

```json
{
  "mail_context": {},
  "crm_context": {},
  "sequence_context": {},
  "generation_constraints": {},
  "raw_payload": {}
}
```

## 环节1：原始邮件字段

数据来源：`mail_raw_unified`

单封详情接口：`GET /api/raw_comm/mail/messages/{mail_uid}`

当前接口返回字段：

| 字段 | 中文说明 | 是否原始字段 | 备注 |
| --- | --- | --- | --- |
| `mail_uid` | 邮件唯一ID | 是 | 后续反馈、检索、清洗、附件解析都可用 |
| `subject` | 邮件原始主题 | 是 | 生成回复时必须传 |
| `from_email` | 发件人邮箱 | 是 | 判断客户/我方/内部 |
| `to_emails` | 收件人邮箱列表 | 是 | 判断回复对象和域名安全 |
| `cc_emails` | 抄送邮箱列表 | 是 | 防泄密和上下文判断 |
| `sent_at` | 邮件发送时间 | 是 | 判断时效和先后顺序 |
| `body_text` | 原始正文文本 | 是 | 最接近原始邮件正文，回复AI可直接读取 |
| `has_attachment` | 是否有附件 | 是 | 附件未必已解析，只表示存在 |
| `source_type` | 来源类型 | 是 | 如 SQL、EML、MSG 等 |
| `ingested_at` | 入库时间 | 是 | 数据采集时间 |
| `raw_payload_path` | 原始payload路径或SQL来源标记 | 是 | 排查原始邮件来源 |

建议给回复AI保留的原始字段包：

```json
{
  "mail_uid": "mail_xxx",
  "subject": "合同盖章版及邮寄地址确认",
  "from_email": "customer@example.com",
  "to_emails": ["sales@speedasia.com"],
  "cc_emails": [],
  "sent_at": "2026-06-08T09:30:00+08:00",
  "body_text": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
  "has_attachment": false,
  "source_type": "sqlserver",
  "ingested_at": "2026-06-08T09:35:00+08:00",
  "raw_payload_path": "sqlserver://..."
}
```

## 环节2：清洗辅助字段

数据来源：`mail_cleaned`

这些字段不是LLM处理结果，而是正文清洗、引用分离和规则识别结果。若对方回复AI希望完全基于原始邮件生成，可只传 `body_text`；若希望减少签名、历史引用干扰，建议同时传清洗字段。

当前单封详情接口返回：

| 字段 | 中文说明 | 备注 |
| --- | --- | --- |
| `body_main_text` | 邮件主正文 | 去除部分历史引用和签名后的正文主体 |
| `body_quoted_text` | 历史引用/盖楼正文 | 可帮助理解上下文，但不宜直接当客户最新诉求 |
| `body_text_clean` | 清洗后正文 | 更适合给模型读取 |
| `sender_side` | 发件方识别 | `seller` / `customer` / `internal` 等 |
| `customer_key` | 邮件侧客户编号 | 可用于CRM联查 |
| `clean_status` | 清洗状态 | pending/success/failed 等 |
| `clean_error` | 清洗错误 | 清洗失败时排查用 |

建议回复AI输入：

```json
{
  "body_main_text": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
  "body_quoted_text": "历史邮件引用内容...",
  "body_text_clean": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
  "sender_side": "customer",
  "customer_key": "KH15411-117",
  "clean_status": "success",
  "clean_error": null
}
```

## 环节3：多封邮件上下文

如果回复AI逻辑未知，建议不要只给单封邮件，还应预留最近邮件线程字段。当前代码已有单封原始邮件详情，后续可按同一 `customer_key`、邮箱、主题归并或邮件线程ID补充最近 N 封邮件。

建议字段：

```json
{
  "recent_mail_messages_limit": 10,
  "recent_mail_messages": [
    {
      "mail_uid": "mail_001",
      "direction": "customer_to_seller",
      "subject": "合同盖章版及邮寄地址确认",
      "from_email": "customer@example.com",
      "to_emails": ["sales@speedasia.com"],
      "cc_emails": [],
      "sent_at": "2026-06-08T09:30:00+08:00",
      "body_text": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
      "body_text_clean": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
      "sender_side": "customer"
    }
  ]
}
```

当前是否满足：单封原始邮件字段已满足；“同一线程最近N封邮件”需要后续按客户、邮箱、主题或邮件线程规则组装。

## 环节4：邮件草稿生成请求字段

接口：`POST /api/v1/mail/generate-draft`

请求模型：`MailGenerateDraftRequest`

| 字段 | 中文说明 | 备注 |
| --- | --- | --- |
| `customer_key` | 客户编号 | 必填，可为KH开头CRM ContactId或邮件侧客户键 |
| `contact_email` | 联系人邮箱 | 可为空；为空时只生成模板，不真实发信 |
| `cc_emails` | 抄送邮箱列表 | 用于防泄密门 |
| `scenario` | 邮件场景 | `re_activation` / `new_business_promotion` / `new_contact_intro` |
| `suite_step` | Sequence第几封 | 1-4 |
| `current_seller_name` | 当前销售姓名 | 写入署名和上下文 |
| `current_seller_signature` | 当前销售签名 | 后端统一拼入正文 |

请求示例：

```json
{
  "customer_key": "KH15411-117",
  "contact_email": "customer@example.com",
  "cc_emails": [],
  "scenario": "new_business_promotion",
  "suite_step": 1,
  "current_seller_name": "何玮",
  "current_seller_signature": "何玮\nSpeedAsia"
}
```

## 环节5：邮件CRM画像字段

当前邮件侧通过 `_lookup_mail_crm_profile(customer_key, contact_email)` 查询CRM画像。

输入字段：

| 字段 | 中文说明 |
| --- | --- |
| `customer_key` | 客户编号、ContactId、CustomerId、公司名或其他可匹配键 |
| `contact_email` | 联系人邮箱 |

输出建议字段：

| 字段 | 中文说明 |
| --- | --- |
| `contact_name` | 联系人姓名 |
| `contact_email` | 联系人邮箱 |
| `company_name` | 公司名称 |
| `customer_key` | 客户编号 |
| `company_industry` | 行业 |
| `recent_opportunities` | 最近3条商机/报价摘要 |
| `recent_quote_summary` | 最近报价摘要 |
| `ongoing_contracts` | 最近3条销售合同 |
| `contact_recent_followup` | 最近跟进记录 |
| `customer_lifecycle_stage` | 新联系人/老联系人/熟联系人 |
| `customer_tier` | 客户等级 |
| `payment_risk_level` | 付款风险 |
| `customer_domains` | 客户邮箱域名白名单 |
| `crm_profile_lookup_status` | CRM查询状态 |
| `crm_profile_source` | CRM来源说明 |

为回复AI对接建议补充保留：

```json
{
  "crm_contact_id": "KH15411-117",
  "crm_customer_id": "真实CRM CustomerId",
  "contact_status": "正常",
  "customer_status": "正常",
  "contact_staff_name": "何玮",
  "contact_owner_name": "何玮",
  "customer_owner_name": "客户负责人"
}
```

## 环节6：Sequence与模板字段

邮件生成不是单次自由回复，而是三大场景 × 4轮 Sequence。

| 字段 | 中文说明 |
| --- | --- |
| `scenario` | 场景编码 |
| `scenario_label` | 场景中文名 |
| `suite_step` | 第几封 |
| `step_key` | 步骤键 |
| `objective` | 本封邮件目标 |
| `cta_style` | CTA方式 |
| `subject_hint` | 主题建议 |
| `recommended_snippet_types` | 推荐Few-Shot类型 |
| `retrieval_filter_requirements` | 检索过滤要求 |
| `forbidden_boundaries` | 禁止边界 |
| `interval_delay_days` | 与上一封间隔天数 |
| `sequence_template_script` | 生产脚本模板 |
| `sequence_template_ai_instruction` | 给AI的指令脚本 |
| `sequence_template_purpose` | 当前模板目的说明 |
| `sequence_template_send_timing` | 发送日期/间隔说明 |

如果回复AI负责邮件正文生成，应把这些字段尽量传给对方，否则它不知道当前是第1封破冰、第2封案例、第3封方案还是第4封收口。

## 环节7：Few-Shot与知识库字段

邮件当前主生成链路会检索黄金范例/Few-Shot。回复AI是否使用这些字段待讨论。

如果回复AI目标是“完全根据原始邮件字段生成”，可不传 Few-Shot。

如果要和现有邮件主链路效果一致，可传：

| 字段 | 中文说明 |
| --- | --- |
| `admitted_fewshot_id` / `retrieved_fewshot_id` | 命中的范例ID |
| `admitted_fewshot_score` / `fewshot_match_score` | 范例匹配分 |
| `admitted_fewshot_title` | 范例标题 |
| `admitted_fewshot_content` | 范例内容 |

## 环节8：商业条款与安全门字段

邮件回复AI必须避免自由编造高风险内容。建议传入后端已解析或强制约束字段：

| 字段 | 中文说明 |
| --- | --- |
| `commercial_terms` | 价格、工期、折扣、账期等商业条款占位符或规则值 |
| `price_placeholder` | 价格占位符 |
| `delivery_sla_placeholder` | 工期/SLA占位符 |
| `discount_placeholder` | 折扣占位符 |
| `payment_terms_placeholder` | 账期/付款条件占位符 |
| `safety_guardrail` | 安全门结果 |
| `real_sending_enabled` | 是否允许真实发送，默认false |
| `review_required` | 是否需要人工审核，默认true |
| `review_mode` | 审核模式 |

要求：

- 回复AI可以写自然语言，但不能编造价格、底价、折扣、账期、工期。
- 这些内容应使用后端占位符或明确规则值。
- 真实发送仍由主系统安全门控制。

## 环节9：邮件草稿响应字段

当前 `MailGenerateDraftResponse` 返回：

| 字段 | 中文说明 |
| --- | --- |
| `status` | 生成状态 |
| `draft_status` | 草稿状态 |
| `review_required` | 是否需要人工审核 |
| `review_mode` | 审核模式 |
| `real_sending_enabled` | 是否开启真实发信 |
| `mail_uid` | 草稿唯一ID |
| `final_subject` | 最终主题 |
| `final_body_html` | 最终HTML正文 |
| `retrieved_fewshot_id` | 命中的Few-Shot ID |
| `fewshot_match_score` | Few-Shot匹配分 |
| `safety_guardrail` | 安全门结果 |
| `llm_status` | LLM状态 |
| `llm_model_used` | 使用模型 |
| `llm_error` | LLM错误 |
| `review_metadata` | 审稿辅助信息 |

后续接入回复AI时，可新增同企微侧类似字段：

```json
{
  "reply_ai": {
    "subject": "回复AI生成主题",
    "body_html": "回复AI生成正文",
    "status": "success",
    "latency_ms": 1200,
    "model": "mail-reply-ai-model-name",
    "error": ""
  }
}
```

## 推荐给邮件回复AI的完整字段包

在对方逻辑未知时，建议尽量完整传：

```json
{
  "request_meta": {
    "request_id": "mail_reply_ai_20260608_demo_001",
    "called_at": "2026-06-08T11:30:00+08:00",
    "source": "mail_generate_draft",
    "real_sending_enabled": false,
    "review_required": true
  },
  "raw_mail": {
    "mail_uid": "mail_demo_001",
    "subject": "合同盖章版及邮寄地址确认",
    "from_email": "customer@example.com",
    "to_emails": ["sales@speedasia.com"],
    "cc_emails": [],
    "sent_at": "2026-06-08T09:30:00+08:00",
    "body_text": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
    "has_attachment": false,
    "source_type": "sqlserver",
    "ingested_at": "2026-06-08T09:35:00+08:00",
    "raw_payload_path": "sqlserver://..."
  },
  "cleaned_mail": {
    "body_main_text": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
    "body_quoted_text": "",
    "body_text_clean": "您好，请发我一下合同邮寄地址，我们今天安排寄出。",
    "sender_side": "customer",
    "customer_key": "KH15411-117",
    "clean_status": "success"
  },
  "recent_mail_messages_limit": 10,
  "recent_mail_messages": [],
  "crm_context": {
    "crm_contact_id": "KH15411-117",
    "crm_customer_id": "customer_id_from_crm",
    "contact_name": "李雅琪",
    "contact_email": "customer@example.com",
    "company_name": "上海某医疗器械企业",
    "company_industry": "医疗器械/生命科学",
    "recent_opportunities": "最近商机摘要",
    "ongoing_contracts": "最近合同摘要",
    "contact_recent_followup": "最近跟进记录",
    "customer_lifecycle_stage": "老联系人",
    "customer_tier": "common",
    "payment_risk_level": "low",
    "customer_domains": ["example.com"],
    "crm_profile_lookup_status": "matched_crm_contact_email_or_customer_key"
  },
  "sequence_context": {
    "scenario": "new_business_promotion",
    "scenario_label": "老客户其他业务介绍",
    "suite_step": 1,
    "objective": "承接历史合作，低压力介绍翻译以外的多业务能力",
    "cta_style": "低压力下一步",
    "sequence_template_purpose": "第1封破冰",
    "sequence_template_send_timing": "第1天发送",
    "sequence_template_script": "生产脚本模板文本",
    "sequence_template_ai_instruction": "给AI的指令脚本文本"
  },
  "generation_constraints": {
    "language": "中文说明内部使用，邮件正文可按业务需要输出英文",
    "must_not_fabricate": ["价格", "折扣", "账期", "付款方式", "工期", "内部底价", "返点"],
    "commercial_terms": {
      "price": "[PRICE_REVIEW_REQUIRED]",
      "delivery_sla": "[SLA_REVIEW_REQUIRED]",
      "discount": "[DISCOUNT_REVIEW_REQUIRED]",
      "payment_terms": "[PAYMENT_TERMS_REVIEW_REQUIRED]"
    },
    "real_sending_enabled": false,
    "review_required": true
  }
}
```

## 中文调用示例

系统指令可先预留为：

```text
你是邮件回复AI。你只根据原始邮件字段、清洗正文、CRM画像、邮件Sequence上下文和安全约束，生成一封可供销售审核的邮件草稿。

硬性要求：
1. 优先回应客户最新邮件正文，不要跳回历史引用。
2. 不要编造价格、折扣、账期、付款方式、工期、返点、内部底价。
3. 涉及商业条款时使用系统提供的占位符或要求人工确认。
4. 邮件正文要自然、商务、具体，不要写“根据知识库”。
5. 如果CRM画像缺失，要保守生成，不编造公司、人名、历史合作。
6. 只输出主题和正文，不输出分析过程。
```

用户消息示例：

```text
【原始邮件】
主题：合同盖章版及邮寄地址确认
发件人：customer@example.com
收件人：sales@speedasia.com
抄送：无
发送时间：2026-06-08 09:30
正文：您好，请发我一下合同邮寄地址，我们今天安排寄出。

【清洗后正文】
您好，请发我一下合同邮寄地址，我们今天安排寄出。

【CRM画像】
客户编号：KH15411-117
联系人：李雅琪
公司：上海某医疗器械企业
行业：医疗器械/生命科学
生命周期：老联系人
客户等级：common
付款风险：low
最近合同：历史有翻译/本地化相关合作记录
最近跟进：近期正在推进合同盖章与邮寄

【邮件任务】
场景：老客户其他业务介绍
当前阶段：第1封
回复目标：先承接客户邮寄合同诉求，给出收件信息占位，提醒寄出后同步快递单号。不要扩展报价、工期或新业务介绍。

【安全约束】
真实发信关闭，必须人工审核。不要编造真实地址，本次用[收件地址]、[收件人]、[联系电话]占位。

请输出：
Subject: ...
Body HTML: ...
```

期望输出示例：

```text
Subject: Re: 合同盖章版及邮寄地址确认

Body HTML:
<p>您好，合同可以寄到以下地址：</p>
<p>[收件地址]<br>[收件人]<br>[联系电话]</p>
<p>您寄出后也可以把快递单号发我一下，我这边收到后会及时跟进。谢谢。</p>
```

## 当前是否满足“原始字段直接生成”

当前满足：

- 单封邮件原始主题、发件人、收件人、抄送、发送时间、正文。
- 清洗正文、主正文、历史引用正文。
- 客户编号、发件方识别、清洗状态。
- 邮件草稿生成所需场景、Sequence步骤、销售姓名、销售签名。
- CRM画像的公司、联系人、商机、合同、跟进、生命周期、客户等级和风险。

当前仍建议后续补强：

- 同一邮件线程最近N封邮件的统一字段包。
- 附件解析后的正文摘要和附件清单。
- CRM ContactId / CustomerId / 联系人状态 / 客户状态 / 负责人字段在邮件主生成链路中统一透传。
- 回复AI输出字段契约，如 `subject/body_html/status/latency_ms/model/error`。
