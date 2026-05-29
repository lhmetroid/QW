# 邮件 AI 回复 - 人工操作与验证说明

> 适用版本: v1.7.198 起
> 本文档面向: 销售主管 / 测试同事 / 试用产品的真实用户
> 目的: 让人工一步步操作, 确认"邮件 AI 回复"模块是真在干活, 不是 Mock 空壳

---

## 0. 一句话现状

**当前可演示**: 触发一次 API → 真调 LLM → 真查黄金库 Few-Shot → 真跑六道安全门 → 浏览器面板看到真草稿。
**当前不能做**: 真把邮件发到客户邮箱 (Task 79 SMTP 通道按规划本轮未做)。
**最终闭环还差**: SMTP 真发 + IMAP 监听客户回复 + 真 CRM 数据替换 Mock dict。

---

## 1. 当前能力清单

| 能力 | 状态 | 证据看哪 |
|---|---|---|
| 后端真调 LLM 生成草稿 | 真接入 | 响应里 `llm_model_used="qwen14b"` |
| Few-Shot 真查黄金库 25 条种子 | 真接入 | 响应里 `retrieved_fewshot_id` 是 UUID |
| 六道安全门真校验 (收件域/SLA/价格/敏感词/占位符/欠款) | 真接入 | 响应 `safety_guardrail.gate_results` |
| 占位符强制保护 (价格/工期/折扣/账期) | 真接入 | body_html 含 `{{MAIL_PRICE_RESOLVED_*}}` |
| 前端面板真渲染后端数据 | 真接入 | 浏览器 Network 面板有 POST 请求 |
| 默认关闭真发邮件 | 真接入 | 响应 `real_sending_enabled=false` |
| SMTP 真发出去 | **未做** | Task 79 待启 |
| IMAP 监听客户回复触发 Sequence | **未做** | Task 79+ |
| 真 CRM (SQL Server) 联查 | **未做** | 当前读 backend/mail_crm_mock_data.py 静态 dict |

---

## 2. 启动后端

任选其一即可。

### 方式 A: 一键启动脚本 (推荐, 端口 8071)

```powershell
pwsh -File start_backend.ps1 -Port 8071
```

启动成功标志:
```
INFO:     Started server process
INFO:     Application startup complete
INFO:     Uvicorn running on http://localhost:8071
```

### 方式 B: 测试用直接 uvicorn (端口 8088, 不抢生产 8071)

```bash
cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8088
```

下面所有 curl 示例默认 8071, 用方式 B 时把端口换成 8088 即可。

---

## 3. 三步冒烟检查 (确认基础设施在跑)

### 3.1 健康检查

```bash
curl http://127.0.0.1:8071/health
```

通过标志: 返回 JSON 里 `"status":"ok"` 且 `checks.postgres.status="ok"`。

### 3.2 黄金库种子在不在

```bash
cd backend && python -c "from database import SessionLocal, EmailFragmentAsset; db=SessionLocal(); print('mail_gold_seed rows:', db.query(EmailFragmentAsset).filter(EmailFragmentAsset.source_type=='mail_gold_seed').count()); db.close()"
```

期望输出: `mail_gold_seed rows: 25`

如果是 0: 跑灌库脚本 `python backend/seed_mail_gold_candidates.py`, 看到 `inserted=25` 即可。

### 3.3 CRM Mock 接口在不在

```bash
curl http://127.0.0.1:8071/api/v1/mail/crm/mock-profiles
```

期望: 返回 `"profile_count":2` 和两个 mock 客户 (`CUST-DEMO-MULTI-DOMAIN` 低风险 / `CUST-HIGH-RISK-DEMO` 高欠款风险)。

---

## 4. 命令行真生成一封草稿

```bash
curl -X POST http://127.0.0.1:8071/api/v1/mail/generate-draft \
  -H "Content-Type: application/json" \
  -d '{
    "customer_key": "CUST-DEMO-MULTI-DOMAIN",
    "contact_email": "buyer@customer-domain.mailmock.test",
    "cc_emails": ["legal@customer-domain-cn.mailmock.test"],
    "scenario": "re_activation",
    "suite_step": 1,
    "current_seller_name": "Mock Sales Owner",
    "current_seller_signature": "Mock Sales Owner"
  }'
```

5-25 秒后返回 JSON。重点看下面 9 个字段对不上号:

| 字段 | 期望值 | 含义 |
|---|---|---|
| `status` | `drafted` | 草稿生成成功 |
| `llm_status` | `success` 或 `fallback_template` | LLM 真路径走完了 |
| `llm_model_used` | `qwen14b` | 真用的模型名 (来自 .env `LLM1_MODEL`) |
| `llm_error` | null (success) 或 超时/JSON 错误 (fallback) | fallback 时这里能看到真失败原因 |
| `retrieved_fewshot_id` | 36 位 UUID | Few-Shot 真命中黄金库某一条 |
| `fewshot_match_score` | 0.60-0.99 | 命中种子的真实 `useful_score` |
| `real_sending_enabled` | `false` | 真发件出口默认关 (永远是 false 直到 Task 79) |
| `review_required` | `true` | 必须人工审核 |
| `final_body_html` | 含 `<p>` 和占位符 `{{MAIL_PRICE_RESOLVED_*}}` | 真草稿; 占位符不是漏洞, 是设计 |

### llm_status 三种结果怎么解读

- `success`: LLM 上游正常返回, 草稿正文是 LLM 真写的英文。
- `fallback_template`: LLM 上游超时或返回非法 JSON, 走老硬编码模板。**草稿仍可读, 接口仍 200**, 只是文字风格固定。
- 既不是这两个值: bug, 报修。

LLM 上游目前是 `zjsphs.2288.org:11599`, 测试时段不稳定, 经常 fallback。这是环境问题不是代码问题。

---

## 5. 浏览器手测 (主推荐验证路径)

### 5.1 打开面板

1. 后端跑起来 (§2)
2. 浏览器打开前端 (file:// 直接打开 frontend/index.html, 或本地静态服务器托管)
3. 顶部导航条找到 **邮件质量诊断** 按钮, 点进去

### 5.2 找 Live Demo 区

进入邮件质量诊断面板后, **最顶部一块绿色边框卡片**就是 v1.7.198 加的真接入演示区:
- 标题: **真实草稿生成（连 LLM + 真查 Few-Shot 黄金库）**
- 右上角徽章: **Real backend** (绿底白字)
- 副标题写: "这一段是 Task 78 真接入..."

如果**没看到这块绿色卡片**, 是浏览器缓存了旧版本。**强刷一下**: `Ctrl+Shift+R` (Mac: `Cmd+Shift+R`)。

### 5.3 提交一次真请求

1. 6 个表单字段全部用默认值 (已预填 `CUST-DEMO-MULTI-DOMAIN` 等)
2. 点绿色 **生成草稿（真调后端）** 按钮
3. 按钮变灰, 旁边状态文本变成 "调用中..."
4. 等 5-25 秒

### 5.4 看结果

请求成功后, 按钮变回绿色, 状态显示 "成功 HTTP 200, XXXms", 下方出现:

**8 个结果卡片** (一行 4 个 x 2 行):
- status / llm_status / llm_model_used / retrieved_fewshot_id
- fewshot_score / mail_uid / real_sending_enabled / safety overall_outcome

**真主题卡片**: 显示 `final_subject` 真值
**真正文卡片**: 渲染 `final_body_html` 真 HTML, 多段 `<p>...</p>`
**折叠的原始 JSON 审计区**: 点 "原始 JSON 响应（用于审计）" 看完整后端返回

### 5.5 真假鉴别 (核心)

**怀疑这是 Mock 数据? 三步排除**:

1. **浏览器 F12 打开 DevTools → Network 面板**
2. 重新点 **生成草稿（真调后端）**
3. Network 列表应出现一条 `POST /api/v1/mail/generate-draft`, Status `200`, Time 5-25s
4. 点这条请求 → **Payload** 标签看请求体, **Response** 标签看真后端响应

如果 Network 看不到这条请求 → 前端代码版本错, 强刷或查 git log。
如果能看到 + Response 跟面板上显示的一致 → 真接入, 没毛病。

---

## 6. 真假鉴别 cheat sheet

每条都是独立可验证, 任意一条不通就有问题。

| # | 验证项 | 操作 | 真接入证据 |
|---|---|---|---|
| 1 | 后端真在跑 | `curl /health` | `status=ok` |
| 2 | 黄金库真有数据 | python ORM 查 | `source_type='mail_gold_seed'` 行数 = 25 |
| 3 | LLM 真发出请求 | 看 `backend/logs/app.log` | grep `LLM_PROMPT_KB_ASSIST_DIFY` 有近期记录 |
| 4 | LLM 真路径走完 | 看响应 | `llm_model_used` 非 null |
| 5 | Few-Shot 真检索 | 看响应 | `retrieved_fewshot_id` 是 UUID, 能在表里查到该行 |
| 6 | 安全门真校验 | 看响应 | `safety_guardrail.gate_results` 列出 6 道门各自结果 |
| 7 | 占位符真保护 | 看 body_html | 含 `{{MAIL_PRICE_RESOLVED_*}}` 字面字符串 |
| 8 | 前端真绑后端 | DevTools Network | 真有 `POST /api/v1/mail/generate-draft` 请求 |
| 9 | 没有真发邮件 | 看响应 | `real_sending_enabled=false` |

### 怎么看后端日志

```bash
tail -f backend/logs/app.log | grep -E "LLM_PROMPT|MAIL_DRAFT_LLM|SLOW_REQUEST"
```

LLM 调用真发出时, 日志会出现:
```
LLM_PROMPT_KB_ASSIST_DIFY {"model": "qwen14b", "url": "http://zjsphs...", "prompt_chars": 1610, ...}
```

LLM 上游超时 fallback 时, 会有:
```
MAIL_DRAFT_LLM_FALLBACK reason=HTTPConnectionPool... Read timed out (read timeout=25)
```

### 怎么在 DB 里查命中的 Few-Shot 种子

拿响应里的 `retrieved_fewshot_id` 值 (UUID 字符串), 跑:

```bash
cd backend && python -c "
from database import SessionLocal, EmailFragmentAsset
db = SessionLocal()
row = db.query(EmailFragmentAsset).filter(EmailFragmentAsset.fragment_id=='这里粘贴UUID').first()
if row:
    print(f'source_ref={row.source_ref} score={row.useful_score} scenario={row.scenario_label}')
    print(f'content[:200]={row.content[:200]}')
db.close()
"
```

能查到这一行 + 内容是真实邮件文本 → Few-Shot 真接入。

---

## 7. 反向验证 - 安全门真会拦截

不只看正常路径走通, 还要看异常路径真拦得住。三个建议测:

### 测试 A: 竞争对手域名收件人 (期望红卡硬阻断)

```bash
curl -X POST http://127.0.0.1:8071/api/v1/mail/generate-draft \
  -H "Content-Type: application/json" \
  -d '{
    "customer_key": "CUST-DEMO-MULTI-DOMAIN",
    "contact_email": "buyer@transperfect-partner.com",
    "scenario": "re_activation",
    "suite_step": 1,
    "current_seller_name": "Sales",
    "current_seller_signature": "Sales"
  }'
```

期望响应:
- `status=blocked_by_recipient_domain_confidentiality_gate`
- `safety_guardrail.status=red_card_hard_block`
- `draft_status=blocked`

### 测试 B: 高欠款客户 (期望黄卡锁定)

把上面的 `customer_key` 换成 `CUST-HIGH-RISK-DEMO`, `contact_email` 换成 `buyer@risk-customer.mailmock.test`, `scenario` 改 `new_business_promotion`。

期望响应:
- `safety_guardrail.status=yellow_card_manual_finance_review_locked`
- `review_mode=manual_finance_review_required`
- 草稿可生成, 但锁定到人工财务审核

### 测试 C: 没真发邮件 - 永远不变

每次调用响应都应是 `real_sending_enabled=false`。即使上面所有路径都跑通了, 邮件也只在内存里, 没出客户邮箱。这是设计, 不是 bug。

---

## 8. 端到端模拟 - 假装 AI 自动回复了一封客户来信

虽然没有 SMTP 真发件、没有 IMAP 真收件, 但完整业务逻辑能在本地走一遍:

### 步骤 1: 模拟"收到客户来信" (CRM 触发)

未来这一步由 CRM 在收到客户来信时自动调。当前手动模拟:

```bash
# 第一封触发
curl -X POST http://127.0.0.1:8071/api/v1/mail/generate-draft \
  -H "Content-Type: application/json" \
  -d @customer_request.json > draft.json
```

### 步骤 2: 销售在面板审稿

1. 销售浏览器打开邮件质量诊断面板
2. Live Demo 区显示 AI 真生成的草稿
3. 审稿: 看 `safety_guardrail.overall_outcome`, 是 `passed` 就 OK, 是 `yellow_card_*` 看 lock_reason 决定改不改, 是 `red_card_*` 必须改或弃稿
4. 复制 `final_body_html` 到邮箱客户端, 把占位符 `{{MAIL_PRICE_RESOLVED_*}}` 手工替换成真实价格 (Task 79 完成后这一步会自动)
5. 销售在自己的邮箱客户端点发送

### 步骤 3: 模拟"客户回复了" (中断 Sequence)

未来这一步由 CRM/IMAP 监听到客户回复时自动调:

```bash
curl -X POST http://127.0.0.1:8071/api/v1/sequence/interrupt \
  -H "Content-Type: application/json" \
  -d '{
    "customer_key": "CUST-DEMO-MULTI-DOMAIN",
    "interrupt_reason": "customer_replied",
    "operator_name": "Mock System",
    "reply_channel": "email"
  }'
```

期望响应: `audit_preview` 含 `customer_reply_trigger`, 说明本来在排队的后续 Sequence 草稿已被标记为停发。

---

## 9. 常见故障排查

| 现象 | 可能原因 | 排查 / 修复 |
|---|---|---|
| HTTP 422 `valid contact_email is required` | 旧版本未修 sanitize_text bug | `git log --oneline | grep v1.7.198` 确认有这个 commit |
| `retrieved_fewshot_id=null` | 黄金库没灌种子 | 跑 `python backend/seed_mail_gold_candidates.py` |
| `llm_status` 永远是 `fallback_template` | LLM 上游 zjsphs.2288.org 不通 | curl 直连试 `curl http://zjsphs.2288.org:11599/v1/chat-messages`; 或换 `.env` 里 `LLM1_API_URL/KEY/MODEL` 到能用的上游 |
| `llm_model_used=null` | 旧版本 | 确认是 v1.7.198+ |
| `safety_guardrail.gate_results` 缺字段 | 旧版本 | 确认 main.py 包含 `_build_mail_safety_gate_results` |
| 浏览器面板看不到 Live Demo 区 | 缓存了旧 frontend/index.html | `Ctrl+Shift+R` 强刷; 或 view-source 看有没有 `mail-quality-live-demo` |
| Network 面板看不到 fetch 请求 | 前端 JS 没绑上 | F12 Console 看有没有 JS 报错; 看 `runMailQualityLiveDraft` 是否定义 |
| 接口超时 25s 才返回 | LLM 上游 timeout (默认 25s) | 这是设计上限, fallback 路径会触发, 接口仍 200 |
| 草稿正文里出现具体价格数字 | LLM 没遵守占位符规则, 或 fallback 模板 bug | 看响应里 `llm_status`: success 就改 prompt; fallback 就检查 `_resolve_mail_commercial_terms` |

---

## 10. 离"真 AI 回复客户邮件"的完整闭环还差什么

下面这张表是完整产品愿景 vs 当前状态:

| 段 | 当前 | 还差 | 优先级 |
|---|---|---|---|
| 客户来信触发 | CRM 手动/定时调 API | IMAP 监听邮箱, 真收到就触发 | P1 |
| AI 草稿生成 | ✅ 真接入 | - | - |
| Few-Shot 引导风格 | ✅ 真接入 | - | - |
| 安全门校验 | ✅ 6 道全真接入 | - | - |
| 占位符强制替换价格 | ✅ 真接入 | 但 `_resolve_mail_commercial_terms` 还没接生产 `PricingRule` 数据库 | P2 |
| 前端审稿面板 | ✅ Live Demo 区真接入 | 反哺黄金库的 PATCH 接口未做 | P2 |
| 销售一键真发邮件 | ❌ 完全没做 | **Task 79 SMTP 通道** (高斯延迟 + IP 配额 + 退信熔断) | P0 |
| 客户回复触发 Sequence 中断 | ⚠️ API 在, 没真监听 | IMAP / WebHook 接客户邮箱 | P1 |
| CRM 联查真实数据 | ⚠️ 读 Python 常量 dict | 接 SQL Server / HTTP CRM | P1 |

**所以"AI 真回复客户邮件"作为可用产品 = 当前 Live Demo + Task 79 SMTP + IMAP 监听**。

最快路径: 把 Task 79 做完, 就能演示"销售点一下按钮邮件真发到客户邮箱"; 再加 IMAP 监听, 就能做到"全自动收到客户回复就停下追加序列"; 那时这套系统就能真正解放销售的重复劳动。

---

## 11. 一图流: 当前完整能跑的链路

```
[人工 / CRM / 测试 curl]
            ↓ POST /api/v1/mail/generate-draft (真路由)
   ┌────────────────────────────────────────────────────┐
   │ backend/main.py _build_mail_generate_draft_response │
   │  1) 输入校验 (修了 5 处 sanitize_text bug, v1.7.198) │
   │  2) get_mail_sequence_step → 拿 Sequence 元数据      │
   │  3) _mail_generate_draft_fewshot → 真查 DB Few-Shot │
   │  4) _resolve_mail_commercial_terms → 占位符注入      │
   │  5) _build_mail_draft_intent_profile → 真查 CRM Mock│
   │  6) _assemble_mail_draft_from_intent_profile         │
   │     ├─ _llm_generate_mail_intro_paragraphs (真调 LLM)│
   │     │   └─ IntentEngine.run_llm1_json_prompt (sync) │
   │     │       └─ HTTP → zjsphs.2288.org:11599 (Dify) │
   │     └─ fallback 老硬编码模板 (LLM 失败时)            │
   │  7) 6 道安全门 (收件域/SLA/价格/敏感词/占位符/欠款)   │
   │  8) 构造响应, real_sending_enabled=false             │
   └────────────────────────────────────────────────────┘
            ↓ JSON 响应
[前端 #mail-quality-live-demo 区]
   - 8 个字段卡片实时显示
   - 渲染 final_subject + final_body_html
   - 折叠原始 JSON 审计区
            ↓
[销售在浏览器看完, 决定]
   - passed: 复制 body → 邮箱客户端 → 手动发
   - yellow_card: 改一改商业条款, 再生成一次
   - red_card: 直接弃稿
            ↓
[未来 Task 79]
   - 销售点 "发送" 按钮 → POST /api/v1/mail/send/{mail_uid}
   - 后端 aiosmtplib 真发 (默认 MAIL_REAL_SENDING_ENABLED=false 时拒发)
   - 高斯随机 90-150s 延迟 + 单账号日 15 封配额 + 退信率 5% 熔断
```
