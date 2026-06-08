# 回复AI与训练AI并发调用后续开发计划

记录时间：2026-06-08

本文只记录后续开发目标，不代表当前代码已经实现。后续真正改代码时，应先重新读取当前 `backend/main.py`、`backend/intent_engine.py`、`frontend/index.html`、`backend/config.py` 和本文件，避免遗漏本轮讨论结论。

> 同内容副本已保存到 `docs/reply_ai_followup_development_plan.md`。由于当前 `.gitignore` 忽略 `docs/` 目录，本根目录副本用于降低后续接力丢失风险。

## 背景

当前企微实时回复链路中，系统已经有主模型 LLM2 与训练AI两路输出。现有训练AI实现存在一个关键问题：训练AI调用虽然没有自己发起知识库检索，但它复用了 LLM2 的 `final_prompt`，因此 prompt 中已经包含 `knowledge_v2` 或“参考知识库匹配”内容。

后续目标是：

- 训练AI不再使用知识库检索结果。
- 在 `thread_fact` 构建完成后，立即发起训练AI调用。
- 同一时间点再接入第三路 AI 回复，命名为“回复AI”。
- 回复AI与训练AI调用时间点、输出位置、评分逻辑一致。
- 系统 API 输出候选从 2 个扩展为 3 个，随机盲评逻辑保留。

## 新目标链路

目标顺序如下：

1. 请求解析、会话 ID 解析、销售 ID / 客户 external_userid 解析。
2. 读取最近会话消息。
3. LLM1 生成结构化摘要。
4. CRM 画像查询。
5. 构建并保存 `thread_fact`。
6. 在 `thread_fact` 完成后立即并发发起：
   - 训练AI调用。
   - 回复AI调用。
   - 知识库检索 `knowledge_v2` / 可选外部知识库。
7. 知识库检索完成后，LLM2 使用知识库结果生成主回复。
8. 收集训练AI与回复AI结果；超时则记录 timeout，不阻塞主回复成功。
9. 将 LLM2、训练AI、回复AI 三路候选一起进入盲评、落库、详情展示和后续评分。

关键原则：

- 训练AI和回复AI都不应读取知识库检索结果。
- 训练AI和回复AI都只使用 `thread_fact` 完成时已经具备的上下文：会话摘要、CRM画像、线程事实、最近消息、回复风格和安全约束。
- LLM2仍然是知识库增强主链路，继续等待知识库检索完成后再生成。

## 回复AI接入目标

新增第三路 AI，产品命名为“回复AI”，用于与主模型和训练AI区分。

建议配置项预留：

```text
REPLY_AI_ENABLED=true
REPLY_AI_BASE_URL=<待回复AI项目提供>
REPLY_AI_API_KEY=<待配置>
REPLY_AI_MODEL=<待回复AI项目提供>
REPLY_AI_TIMEOUT_SECONDS=15
REPLY_AI_MAX_TOKENS=300
REPLY_AI_TEMPERATURE=0.2
```

默认超时上限：15秒。

回复AI调用时间点：

```text
thread_fact 构建并落库完成后立即发起
```

回复AI输入规则：

- 与训练AI相同，使用独立 prompt。
- 不包含知识库检索结果。
- 可复用训练AI prompt builder 的字段结构，但在系统指令中标识“回复AI”。
- 后续如果回复AI项目提供固定输入字段或输出字段，再按对方接口契约调整。

回复AI输出预留字段：

```json
{
  "reply": "回复AI生成的可发客户回复",
  "status": "success | timeout | failed | disabled",
  "latency_ms": 1234,
  "model": "reply-ai-model-name",
  "protocol": "reply_ai_api",
  "error": ""
}
```

## 三路输出与随机逻辑

当前前端类似显示为：

```text
第6步-AI生成回复（1/2）
```

后续应改为：

```text
第6步-AI生成回复（1/3）
```

三路候选来源：

```text
llm2：主模型，使用知识库检索结果。
train_ai：训练AI，不使用知识库检索结果。
reply_ai：回复AI，不使用知识库检索结果。
```

随机逻辑保留：

- 前端展示位置仍随机，不直接暴露哪个是 LLM2、训练AI、回复AI。
- 可以显示为 `1：...`、`2：...`、`3：...`。
- 后端需要保留 blind map，例如：

```json
{
  "reference1": "reply_ai",
  "reference2": "llm2",
  "reference3": "train_ai"
}
```

内部落库仍必须保留真实来源，供后续揭盲、评分、统计。

## 评分逻辑

回复AI评分逻辑等同训练AI：

- 使用同一套销售回复质量评分标准。
- 使用同一套维度，如 `overall`、`low_barrier`、`non_repetition`、`safety`、`conciseness`、`style_match`、`context_alignment`。
- 与 LLM2 候选一起进入同一轮评分输入。
- 训练AI与回复AI的评分结果应从 `ai_candidates` 主候选池中单独拆出，避免污染“主AI质量分”的统计口径。

建议新增字段：

```json
{
  "training_ai_candidate": {},
  "reply_ai_candidate": {}
}
```

## 耗时统计新口径

后续需要同步修改后端 `timings_ms`、`node_timings_ms` 和前端浮层说明。

### 主回复可输出耗时

```text
pipeline_total_ms 或 fetch_to_output_ms
```

包含请求解析、会话读取、LLM1摘要、CRM画像、thread_fact构建、知识库检索、LLM2主回复生成、必要校验。

不包含训练AI/回复AI晚返回等待、盲评映射、写轻量调用记录、二阶段 timing 回写。

### 完整记录总墙钟耗时

```text
wall_total_ms 或 total_ms
```

包含主回复可输出耗时、训练AI结果收集或超时、回复AI结果收集或超时、盲评映射、JSON清洗、ApiAssistInvocation写入、timing二阶段回写。

### 并发分支耗时

```json
{
  "parallel_after_thread_fact_ms": {
    "knowledge_retrieve_ms": 1523,
    "knowledge_v2_ms": 1462,
    "knowledge_external_api_ms": 61,
    "train_ai_ms": 1355,
    "reply_ai_ms": 820,
    "llm2_generate_ms": 1436
  }
}
```

关系说明：

- 训练AI起点 = thread_fact完成后。
- 回复AI起点 = thread_fact完成后。
- 知识库检索起点 = thread_fact完成后。
- LLM2起点 = 知识库检索完成后。
- 训练AI和回复AI不阻塞知识库检索。
- 训练AI和回复AI不参与 LLM2 prompt。
- 如果训练AI或回复AI晚于 LLM2完成，只影响完整记录耗时，不应计入 LLM2生成耗时。

## 前端浮层说明调整

截图中的耗时浮层后续建议改为：

```text
【当前触发耗时拆分】

第一行：主回复可输出耗时。
含：请求解析、会话读取、LLM1摘要、CRM画像、thread_fact构建、知识库检索、LLM2主回复生成。
不含：训练AI/回复AI晚返回等待、盲评落库、二阶段耗时回写。

第二行：完整记录总墙钟耗时。
含：主回复耗时 + 训练AI结果收集/超时 + 回复AI结果收集/超时 + 盲评映射 + 结果落库 + timing回写。
```

## 后续实现检查点

1. 训练AI是否还会复用 `IntentEngine.build_sales_assist_request(..., knowledge_v2, ...)`。
2. 回复AI是否完全不接触 `knowledge_v2`。
3. `REPLY_AI_TIMEOUT_SECONDS` 是否默认15秒且可配置。
4. 训练AI和回复AI是否在 `thread_fact` 落库后立即 submit。
5. 非流式与流式路径是否都只调用一次训练AI和回复AI，不能重复调用。
6. 详情页是否从 `(1/2)` 改成 `(1/3)`。
7. 三路候选是否随机展示，但真实来源可在后台揭盲。
8. 三路评分是否进入同一评分模型，且训练AI/回复AI评分不污染主AI分。
9. 耗时浮层是否明确说明训练AI/回复AI与知识库并发，不使用知识库。
