import urllib.request
import json
import urllib.error

url = 'http://127.0.0.1:8071/api/case_lib/iterations/716914b9-1cdb-43de-b007-bba5ca68112b/analysis'
content = '''
## V4测试结果分析

### 1. 核心阻碍与发现
- **外部LLM依赖不稳定**：在真实的 v4 测试链路中，发现大量因 `HTTPConnectionPool(host='zjsphs.2288.org', port=11599): Read timed out. (read timeout=100)` 导致的超时，造成 `real_conn_fail` 和 AI 回复打分机制大面积失效。这也是目前销售原始回复分为空值（状态为 `llm1_failed`）的根本原因。
- **打分机制需调优**：部分案例在最终打分阶段存在“虚高”（如得到92分但实际话术难以复用）。原因是目前 `IntentEngine.score_reply_candidates` 维度的评判标准未完全贴合实际销售场景。

### 2. 知识库检索与生成链路优化建议
- **知识库召回**：目前只要关键词匹配即可召回，但销售实战中经常会出现“无效资料”的情况。建议在知识库接入时，扩展“语义检索(Vector)”与“规则分类(Rule)”的结合，不仅匹配产品词，还要匹配 `core_demand` 意图。若确实无对应数据，必须在后台增加相应 QA 对。
- **客户画像穿透**：如果此节点的客户画像没有找到对应的，通常是因为取id取错或没有绑定关联。必须验证 `external_userid` 的关联逻辑，确保调用 CRM API 前正确提取了企微 ID。
- **生成链路约束**：目前的 AI 回复有时不够简练。建议在 `SYSTEM_PROMPT_LLM2` 中加强对“长篇大论、过度客套”的惩罚机制，确保输出内容“直接能复制就用”。

### 3. 下一步执行计划
1. **修复 LLM-1 超时**：建议调整服务器资源或换用更稳定的备用模型（如 API 超时重试机制）。
2. **优化评分 prompt**：成倍增加 `conciseness` (微信感简练) 和 `low_barrier` (易回复) 的权重，从而压低不合格长文本的得分。
3. **闭环修复画像与打分**：修正客户 ID 解析逻辑，针对前期空值案例，在 LLM 服务稳定后重新执行 `_rescore_sales_replies.py` 补充评分。
'''
data = json.dumps({'source': 'antigravity', 'content': content.strip()}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='PUT')
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except urllib.error.URLError as e:
    print('Error:', getattr(e, 'reason', e))
