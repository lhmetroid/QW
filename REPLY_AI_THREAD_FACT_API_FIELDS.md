# 回复AI对接字段说明：thread_fact完成后的可用上下文

记录时间：2026-06-08

本文用于给“回复AI”所在项目做 API 调用代码对接准备。当前只是字段整理和示例，不代表回复AI已接入。本文件中的示例为对接样例，实际生产调用必须由运行时实时读取企微会话、CRM系统和 `thread_fact` 后填充，不应把示例常量写死为真实生产数据。

> 同内容详版已保存到 `docs/reply_ai_thread_fact_api_fields.md`。由于当前 `.gitignore` 忽略 `docs/` 目录，本根目录副本用于降低后续接力丢失风险。

## 调用时机

```text
构建 thread_fact 并落库完成后立即调用
```

此时系统已经具备：

- 会话 ID、销售 ID、客户 external_userid。
- LLM1 结构化摘要。
- CRM 客户画像。
- thread_fact 业务事实。
- 最近会话消息。
- 前置强信号扫描结果。

此时系统尚未依赖知识库检索结果和 LLM2 主模型生成结果。

## 推荐请求体总结构

```json
{
  "model_name": "reply-ai-model-name",
  "messages": [
    {
      "role": "system",
      "content": "回复AI系统指令"
    },
    {
      "role": "user",
      "content": "由下方字段拼成的中文业务上下文"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 300
}
```

## thread_fact完成前各环节输入输出字段

本节说明从“当前会话输入”到“构建 thread_fact 完成”之前，每一步实际有哪些输入、输出字段。回复AI后续调用点在 thread_fact 完成后，因此可以拿到本节所有输出。

### 环节0：数据库原始聊天记录

数据库表：`message_logs`

| 字段 | 中文说明 | 备注 |
| --- | --- | --- |
| `id` | 消息自增ID | 数据库内部定位 |
| `user_id` | 会话ID | 通常用于定位某个销售与客户的会话 |
| `sender_type` | 发送方类型 | `customer` 客户，`sales` 我方销售 |
| `content` | 原始聊天正文 | 企微消息文本，LLM1和回复AI上下文的核心来源 |
| `timestamp` | 消息时间 | 用于按时间排序 |
| `archive_msg_id` | 企微存档原始消息ID | 用于排查企微存档来源 |
| `archive_seq` | 企微存档增量游标 | 用于同步定位 |

### 环节1：当前会话输入

后端变量：`recent_logs`

前端/API字段：`input_messages`

中文含义：当前会话用于本轮AI链路的原始上下文消息列表。前端“当前会话输入”卡片显示的就是这个字段，页面再按配置显示最近 N 条。

后端典型来源：

```text
message_logs -> recent_logs -> input_messages
```

`input_messages` 推荐结构：

```json
[
  {
    "sender": "sales",
    "sender_type": "sales",
    "content": "好的，合同这边确认后我发您地址",
    "time": "2026-06-08T10:25:00+08:00"
  },
  {
    "sender": "customer",
    "sender_type": "customer",
    "content": "早，给我个地址，我把合同邮寄过去",
    "time": "2026-06-08T10:26:00+08:00"
  }
]
```

如果后续要明确“最近15条聊天记录”，建议在回复AI请求中固定为：

```json
{
  "recent_messages_limit": 15,
  "recent_messages": []
}
```

其中 `recent_messages` 就取自 `input_messages` 的最近15条，按时间正序排列。

### 环节2：LLM1 Prompt占位文本

Prompt占位符：`{{conversation_text}}`

后端临时变量：`conversation_text`

中文含义：LLM1调用前，后端把 `recent_logs` / `input_messages` 拼成一段纯文本，再替换到 `SYSTEM_PROMPT_LLM1` 的 `{{conversation_text}}`。

拼接形式类似：

```text
[销售]: 好的，合同这边确认后我发您地址
[客户]: 早，给我个地址，我把合同邮寄过去
```

注意：

- `conversation_text` 不是接口返回字段，也不是数据库字段。
- 它是 LLM1 调用时的 prompt 内部文本。
- 回复AI后续不一定要复用这个纯文本字段；更建议直接传结构化的 `recent_messages`，同时可附加一份 `conversation_text` 方便对方项目快速接入。

### 环节3：LLM1结构化摘要

后端调用：`IntentEngine._run_llm1(session_id, context)`

输入字段：

| 字段 | 中文说明 |
| --- | --- |
| `session_id` | 当前会话ID |
| `context` | 最近聊天记录数组，每条包含 `content` 和 `sender_type` |
| `conversation_text` | 由 `context` 拼出的LLM1 prompt文本 |
| `SYSTEM_PROMPT_LLM1` | 第一阶段特征提取脚本 |

LLM1输出字段：`summary_json`

```json
{
  "topic": "合同邮寄地址请求",
  "core_demand": "客户要我方收件地址，用于邮寄合同",
  "key_facts": ["客户准备邮寄合同", "当前需要收件地址"],
  "todo_items": ["提供收件地址、收件人和电话"],
  "risks": "不要扩展报价、工期或知识库案例",
  "to_be_confirmed": "客户是否需要同步电子版",
  "status": "success"
}
```

字段说明：

| 字段 | 中文说明 | 给回复AI的用途 |
| --- | --- | --- |
| `topic` | 当前主线话题 | 帮助回复AI把话题聚焦 |
| `core_demand` | 客户核心诉求 | 判断回复要解决什么 |
| `key_facts` | 关键事实 | 防止回复AI遗漏事实 |
| `todo_items` | 待跟进事项 | 生成下一步动作 |
| `risks` | 风险/顾虑 | 避免越权承诺 |
| `to_be_confirmed` | 待确认信息 | 信息不足时只问一个问题 |
| `status` | LLM1摘要状态 | 非 success 时应保守回复 |

### 环节4：Fast-Track强信号扫描

后端变量：`fast_track_signals`

输入字段：`recent_logs` 中的 `content`、`sender_type`。

输出字段示例：

```json
[
  {
    "rule_id": "file_request",
    "label": "文件发送",
    "matched": true,
    "reason": "客户提到文件/地址/合同等强信号"
  }
]
```

中文说明：Fast-Track用于快速识别明显场景，比如地址、文件、合同、报价、时间确认等。回复AI可把它作为辅助提示，但不能替代最近客户消息和 LLM1摘要。

### 环节5：CRM画像查询

后端调用：`IntentEngine.get_crm_context(external_userid)`

输入字段：

| 字段 | 中文说明 |
| --- | --- |
| `external_userid` | 企微客户外部联系人ID |

输出字段：`crm_context`

```json
{
  "crm_external_userid": "wmS8sICwAAaDvJxZ_Z...",
  "crm_contact_name": "李雅琪",
  "company_name": "上海某医疗器械企业",
  "company_industry": "医疗器械/生命科学",
  "recent_opportunities": "最近商机摘要",
  "recent_quote_summary": "最近报价摘要",
  "ongoing_contracts": "近期合同摘要",
  "contact_recent_followup": "最近跟进记录",
  "customer_lifecycle_stage": "老联系人",
  "customer_tier": "common",
  "payment_risk_level": "low",
  "high_risk_flags": [],
  "crm_profile_status": "success"
}
```

当前还建议后续补充：

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

### 环节6：构建thread_fact

后端调用：`_upsert_thread_business_fact(...)`

输入字段：

```json
{
  "session_id": "当前会话ID",
  "summary_json": {},
  "crm_context": {},
  "messages": [],
  "external_userid": "客户external_userid",
  "sales_userid": "销售userid"
}
```

字段说明：

| 字段 | 中文说明 |
| --- | --- |
| `session_id` | 当前会话ID |
| `summary_json` | LLM1结构化摘要 |
| `crm_context` | CRM画像 |
| `messages` | 最近聊天记录，来源于 `recent_logs` 正序化 |
| `external_userid` | 客户 external_userid |
| `sales_userid` | 销售 userid |

输出字段：`thread_fact_payload` / `ThreadBusinessFact`

```json
{
  "session_id": "当前会话ID",
  "thread_id": "当前线程ID",
  "external_userid": "客户external_userid",
  "sales_userid": "销售userid",
  "topic": "合同邮寄地址请求",
  "core_demand": "客户要我方收件地址，用于邮寄合同",
  "scenario_label": "process",
  "intent_label": "process",
  "language_style": "wechat_brief",
  "business_state": "inquiry",
  "stage_signals": {
    "has_formal_quote": false,
    "awaiting_customer_reply": false,
    "sales_only_conversation": false,
    "followup_after_no_reply": false
  },
  "merged_facts": {
    "last_sender": "customer",
    "latest_customer_message": "早，给我个地址，我把合同邮寄过去",
    "latest_customer_reply_type": "request_info",
    "latest_sales_message": "好的，合同这边确认后我发您地址",
    "recent_sales_messages": ["好的，合同这边确认后我发您地址"],
    "sales_message_count": 1,
    "customer_message_count": 1
  },
  "reply_guard_reason": "当前只需流程承接，不要新增价格、工期、折扣、账期承诺",
  "usable_for_reply": true,
  "allowed_for_generation": true
}
```

这一步完成后，回复AI和训练AI即可并发调用。此时仍不应传入知识库检索结果。

## 可用字段清单

### 请求与会话标识

| 字段 | 中文说明 | 当前来源 |
| --- | --- | --- |
| `request_id` | 本次API调用请求ID，用于日志串联 | 当前请求生成 |
| `session_id` | 系统内部会话ID，通常由销售ID和客户 external_userid 组合 | `ThreadBusinessFact.session_id` |
| `thread_id` | 线程ID，当前通常与 session_id 一致 | `ThreadBusinessFact.thread_id` |
| `external_userid` | 企微客户外部联系人ID，用于查CRM画像 | `ThreadBusinessFact.external_userid` |
| `sales_userid` | 销售企微用户ID | `ThreadBusinessFact.sales_userid` |
| `trigger_source` | 触发来源，如实时侧边栏、案例库验证、强制刷新 | 当前请求上下文 |
| `snapshot_id` | 可选，会话快照ID，用于防重复触发和定位本轮上下文 | 当前请求上下文 |

### CRM主键与客户身份字段

| 字段 | 中文说明 | 当前来源 |
| --- | --- | --- |
| `crm_external_userid` | CRM画像使用的企微 external_userid | `crm_context.crm_external_userid` |
| `crm_contact_id` | CRM联系人ID，例如 `KH15411-117` 这种 KH 开头编号 | CRM `usrCustomerContact.ContactId` |
| `crm_customer_id` | CRM客户ID | CRM `usrCustomer.CustomerId` |
| `crm_contact_name` | CRM联系人姓名 | `crm_context.crm_contact_name` |
| `company_name` | 客户公司名称 | `crm_context.company_name` |
| `contact_status` | 联系人状态 | CRM联系人表 |
| `customer_status` | 客户状态 | CRM客户表 |
| `contact_staff_name` | 联系人负责销售/负责人 | CRM联系人相关字段 |
| `contact_owner_name` | 联系人owner | CRM联系人相关字段 |
| `customer_owner_name` | 客户负责人 | CRM客户相关字段 |

当前企微实时主链路的 `IntentEngine.get_crm_context()` 已返回：

```json
{
  "crm_external_userid": "...",
  "crm_contact_name": "...",
  "company_name": "...",
  "company_industry": "...",
  "recent_opportunities": "...",
  "recent_quote_summary": "...",
  "ongoing_contracts": "...",
  "contact_recent_followup": "...",
  "customer_lifecycle_stage": "...",
  "customer_tier": "...",
  "payment_risk_level": "...",
  "high_risk_flags": [],
  "crm_profile_status": "success"
}
```

后续为了满足回复AI对接，建议在企微CRM画像中补充并透传：

```json
{
  "crm_contact_id": "KH15411-117",
  "crm_customer_id": "真实CRM CustomerId",
  "contact_status": "联系人状态",
  "customer_status": "客户状态",
  "contact_staff_name": "销售/负责人",
  "contact_owner_name": "联系人负责人",
  "customer_owner_name": "客户负责人"
}
```

### CRM画像字段

| 字段 | 中文说明 | 用法 |
| --- | --- | --- |
| `company_industry` | 行业判断 | 帮助回复AI选择行业语境 |
| `recent_opportunities` | 最近商机摘要 | 判断客户当前机会和正在咨询方向 |
| `recent_quote_summary` | 最近报价摘要 | 判断是否已有报价历史；禁止回复AI编造价格 |
| `ongoing_contracts` | 近期合同摘要 | 判断历史合作类型和客户成熟度 |
| `contact_recent_followup` | 最近跟进记录 | 判断之前销售已说过什么，避免重复 |
| `customer_lifecycle_stage` | 生命周期阶段，如新联系人、老联系人、熟联系人 | 决定语气和推进方式 |
| `customer_tier` | 客户等级 | 决定谨慎程度和服务优先级 |
| `payment_risk_level` | 欠款/付款风险等级 | 决定是否保守承诺 |
| `high_risk_flags` | 高风险标记列表 | 触发更保守回复 |
| `crm_profile_status` | CRM查询状态 | success/not_found/error/empty |

### LLM1结构化摘要字段

| 字段 | 中文说明 |
| --- | --- |
| `topic` | 当前主线话题 |
| `core_demand` | 客户核心诉求 |
| `key_facts` | 关键事实列表或对象 |
| `todo_items` | 待跟进事项 |
| `risks` | 风险、顾虑或限制 |
| `to_be_confirmed` | 仍需确认的信息 |
| `status` | LLM1摘要状态 |
| `fast_track_signals` | 前置规则扫描结果 |

### thread_fact字段

| 字段 | 中文说明 |
| --- | --- |
| `fact_id` | 业务事实记录ID |
| `session_id` | 会话ID |
| `thread_id` | 线程ID |
| `external_userid` | 客户 external_userid |
| `sales_userid` | 销售用户ID |
| `topic` | 主线话题 |
| `core_demand` | 核心诉求 |
| `scenario_label` | 业务场景标签，如 capability/process/pricing/example |
| `intent_label` | 意图标签 |
| `language_style` | 建议语言风格，如 wechat_brief |
| `business_state` | 当前业务状态，如 inquiry/followup/quoted |
| `stage_signals` | 阶段信号，例如是否已有正式报价、是否等待客户资料 |
| `merged_facts` | 合并后的会话事实，是回复AI最关键输入之一 |
| `attachment_summary` | 附件/邮件资产摘要 |
| `fact_source` | 事实来源说明 |
| `quality_score` | 事实质量分 |
| `effect_score` | 后验效果分 |
| `outcome_feedback` | 人工反馈或结果反馈 |
| `usable_for_reply` | 是否可用于回复 |
| `allowed_for_generation` | 是否允许生成 |
| `reply_guard_reason` | 回复门禁原因 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### merged_facts建议重点使用字段

| 字段 | 中文说明 |
| --- | --- |
| `last_sender` | 最后一条消息发送方，customer 或 sales |
| `sales_message_count` | 当前窗口内销售消息数 |
| `customer_message_count` | 当前窗口内客户消息数 |
| `consecutive_sales_messages` | 连续销售消息数，用于判断是否追问过多 |
| `awaiting_customer_reply` | 是否正在等客户回复 |
| `latest_sales_message` | 最近一条销售消息 |
| `recent_sales_messages` | 最近若干条销售消息 |
| `latest_customer_message` | 最近一条客户消息，回复AI应优先回应 |
| `latest_customer_reply_type` | 客户最新回复类型，如 question/ack_only/schedule_confirmation |
| `latest_customer_time_mentions` | 客户最新消息中的时间表达 |
| `crm_has_quote_history` | CRM是否有报价历史 |

## 回复AI中文脚本要求预留

```text
你是企微销售回复AI。你只根据会话摘要、CRM画像、thread_fact线程事实和最近聊天内容，生成一条可以直接发给客户的中文微信回复。

硬性要求：
1. 优先回应客户最新一句，不要跳回更早问题。
2. 语气自然、亲和、像真人销售，不要像机器人。
3. 默认80字以内，除非客户问题复杂。
4. 不要引用知识库案例，不要说“根据知识库”。
5. 不要编造价格、折扣、账期、付款方式、工期、返点、内部底价。
6. 如果客户在确认时间或资料，先承接，再给下一步。
7. 如果信息不足，只提一个低压力问题。
8. 只输出最终回复文本，不输出分析过程。
```

## 2026-06-08 对接示例

以下示例用于说明“今天一次实际企微回复调用在 thread_fact 完成后应如何拼字段”。示例中的客户编号采用当前项目已用于CRM联调的 KH 编号格式；真实调用时必须由 CRM 实时查询填充，不能把示例写死。

### 示例业务背景

```text
调用日期：2026-06-08
客户编号 / CRM ContactId：KH15411-117
CRM CustomerId：运行时由CRM返回，例如 customer_id_from_crm
联系人：李雅琪
公司：上海某医疗器械企业
销售：何玮
客户最新消息：早，给我个地址，我把合同邮寄过去
当前主线：合同邮寄地址请求
回复目标：给客户收件信息，并提醒可同步发电子版或快递单号；不要引入知识库内容。
```

### 推荐发给回复AI的请求体示例

```json
{
  "model_name": "reply-ai-model-name",
  "messages": [
    {
      "role": "system",
      "content": "你是企微销售回复AI。你只根据会话摘要、CRM画像、thread_fact线程事实和最近聊天内容，生成一条可以直接发给客户的中文微信回复。优先回应客户最新一句；语气自然、亲和；默认80字以内；不要引用知识库案例；不要编造价格、折扣、账期、付款方式、工期、返点、内部底价；只输出最终回复文本。"
    },
    {
      "role": "user",
      "content": "【调用信息】\n调用日期：2026-06-08\n请求ID：api_reply_20260608_demo_001\n会话ID：wmS8sICwAAaDvJxZ_Z...::KH15411-117\n客户external_userid：wmS8sICwAAaDvJxZ_Z...\n销售userid：hewei\n\n【CRM身份】\n客户编号/CRM ContactId：KH15411-117\nCRM CustomerId：customer_id_from_crm\n联系人：李雅琪\n公司：上海某医疗器械企业\n联系人状态：正常\n客户状态：正常\n销售/负责人：何玮\n行业：医疗器械/生命科学\n客户级别：老客户\nCRM生命周期阶段：老联系人\n欠款风险等级：low\n高风险标记：无\n\n【CRM画像】\n最近商机摘要：合同邮寄与项目执行资料确认\n最近报价摘要：无本轮可直接承诺价格；如涉及价格，以正式报价单为准\n近期合同摘要：历史有翻译/本地化相关合作记录\n最近跟进：近期正在推进合同盖章与邮寄\n\n【LLM1摘要】\n主线话题：合同邮寄地址请求\n客户核心诉求：客户要我方收件地址，用于邮寄合同\n关键事实：客户已经准备邮寄合同；当前只需要回复收件信息和下一步\n待跟进事项：提供收件地址、收件人和电话；可提醒客户发快递单号\n风险：不要扩展报价、工期或知识库案例\n待确认信息：客户是否需要电子版同步发送\n\n【thread_fact】\nscenario_label：process\nintent_label：process\nlanguage_style：wechat_brief\nbusiness_state：inquiry\nreply_guard_reason：当前只需流程承接，不要新增价格、工期、折扣、账期承诺\nstage_signals：has_formal_quote=false, awaiting_customer_reply=false, sales_only_conversation=false, followup_after_no_reply=false\nmerged_facts.last_sender：customer\nmerged_facts.latest_customer_message：早，给我个地址，我把合同邮寄过去\nmerged_facts.latest_customer_reply_type：request_info\nmerged_facts.latest_sales_message：好的，合同这边确认后我发您地址\nmerged_facts.recent_sales_messages：['好的，合同这边确认后我发您地址']\n\n【最近聊天】\n销售：好的，合同这边确认后我发您地址\n客户：早，给我个地址，我把合同邮寄过去\n\n【回复任务】\n请生成一条可直接发给客户的企微中文回复。必须包含：收件地址、收件人、电话这三个占位信息。由于真实地址后续由系统配置或人工确认填充，本次用[收件地址]、[收件人]、[联系电话]占位，不要编造真实地址。可轻量提醒客户寄出后发快递单号。"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 300
}
```

### 期望回复AI输出示例

```text
好的，寄到这个地址就行：[收件地址]，收件人：[收件人]，[联系电话]。您寄出后把快递单号发我一下，我这边收到后马上跟进。
```

## 后续需要回复AI项目确认的输出字段

主系统接入时先只依赖：

```json
{
  "reply": "最终回复文本",
  "status": "success",
  "latency_ms": 800,
  "model": "reply-ai-model-name",
  "error": ""
}
```

可选扩展字段：

```json
{
  "confidence": 0.86,
  "safety_flags": [],
  "reason": "简短说明为什么这样回复",
  "raw_response": {}
}
```
