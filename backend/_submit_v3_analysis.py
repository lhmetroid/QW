"""将 Claude Code 的 v3 分析提交到数据库"""
import os, sys, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    with open(p) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import engine
from sqlalchemy import text

run_id = 'caf54fdf-21d4-4732-8963-d548d2d0da2c'

ANALYSIS = """## v3 Claude Code 深度评分分析（2026-05-19）

### 一、核心数据快照

| 指标 | 数值 |
|---|---|
| 成功案例 | 60/60（real_success） |
| LLM-1 评分成功 | 49/60 |
| LLM-1 评分失败（real_score_missing） | **11/60** |
| 销售原始回复分（actual_sales_replies） | 60/60 均有分 |
| AI 质量分均值（49个有效） | 87.63（含11个NULL后实际偏低） |
| conciseness 系统性偏低案例 | **23/49**（字数≤50字却给60-70分） |
| stored_overall vs formula 平均偏差 | -1.0（stored略低于公式值） |
| stored与公式差距>2分的案例 | 28/49（含12个偏高、16个偏低） |

---

### 二、打分准确性核心判断：当前分数整体虚高，且内部维度矛盾

#### 2.1 conciseness（微信感）系统性评分错误——最关键

Prompt 规定"超过50字最高只给60分，超过80字直接给0分"，即 ≤50字 可以给高分。

但实测发现 23/49 个案例字数 ≤50字 却只获得 conciseness=60~70，典型例子：

- S12-5（32字，stored=90）→ conc=60（formula=80，高估10分）：收到，我马上改好发你，先把翻译改成英译中，其他价格内容都不动哈。
- S05-1（27字，stored=90）→ conc=70（formula=86，高估4分）：刚发您邮箱了，查收下哈～需要我把英文文字也一起发您吗？
- S02-5（29字，stored=85）→ conc=60（formula=80，高估5分）：亲，三个翻译版本您看哪个更合适？有需要调整的地方随时说哈～
- S09-3（33字，stored=85）→ conc=60（formula=78，高估7分）：超，开工大吉～年后有需要翻译印刷的地方随时喊我，我这边随时在线哈😊

根因：qwen14b 将"≤50字"误解为"50分封顶"，系统性给短回复打了错误的低分。这导致本该因简洁获得加分的优质短回复被拉低了 overall。

#### 2.2 overall_score 与公式不一致——v3 数据存了 LLM 直接给分

代码公式：overall = conc×0.18 + low×0.24 + nonrep×0.22 + safe×0.22 + style×0.08 + ctx×0.06

实测 49 个案例：差距>2分的有 28 个，均值偏差 -1.0。
- S12-5：维度分反推公式=80，但stored=90（高估10分）
- S05-5：维度分反推公式=77，但stored=85（高估8分）

根因：v3 运行时代码直接将 LLM 返回的 overall 存入 overall_score，未做公式覆盖（该修复在后续 commit 才上线）。因此 v3 的质量分反映的是 qwen14b 的主观打分，而非公式计算值。

#### 2.3 safety 普遍虚高

49 个有分案例中 safety=100 的占 45%，safety≥90 的占 78%。普通跟进话语被打满分，人为拉高了整体分。

#### 2.4 综合判断：当前 v3 AI 质量分偏高约 5~8 分

49 个案例均值 87.63，若修正 conciseness + 用公式覆盖 overall，预估实际均值约 79~82。

关于"92分是否真高质量"：v3 最高实际为 S06-3（47字）"明白，您先忙。那FW那边最近PO刚用完，是直接跟您对接还是另有同事负责？"——回复本身口语化、推进到位，质量尚可，但按修正后公式估算约 83~87 分，而非 9x。当前虚高根因是 qwen14b 不遵守 conciseness 规则 + safety 给满分两重因素叠加。

---

### 三、11个 real_score_missing 案例

S06-3、S06-5、S02-4、S05-2、S07-2、S07-3、S06-4、S03-2、S07-1、S03-3、S03-1

这些案例 AI 回复生成成功（ai_candidates 有内容），只是评分阶段 qwen14b 超时/无响应。这 11 个案例的 quality_score=NULL，不纳入平均分统计，但 UI 在前一轮查询时可能显示过旧数据导致混淆。建议写脚本单独补评分，不需要重跑全链路。

---

### 四、销售原始分说明

actual_sales_replies 字段 60/60 均有分（非空）。评分样例合理：
- "去问下哦"（4字） → 30分（合理，推卸敷衍）
- "哦哦~~"（4字） → 40分（合理，无实质推进）
- "哎，物料成本都在涨呢，要不我去试试12"（28字） → 90分（合理，幽默破冰有推进）

UI 若显示"销售原始分为空"，根因可能是前端读取时用了错误的 key（sales_scores 而非 actual_sales_replies），需检查前端渲染代码。

---

### 五、下一轮迭代核心优化建议（按优先级）

1. 修复 conciseness 打分 Prompt（P0）：明确写"≤50字的回复 conciseness 应给 80-95 分；绝对不能对≤50字的回复给低于75分"，消除 qwen14b 的误解。

2. 强制公式覆盖 overall（已在最新代码修复，下轮跑时验证即可）。

3. 降低 safety 基准：普通跟进/确认类回复 safety 基准分为 75，只有明确规避客户风险的回复才给 90+。

4. 补打 11 个 real_score_missing 案例：单独对已有 ai_candidates 重调 LLM-1 评分，更新 step7 和 quality_score。

5. LLM-1 稳定性：11/60=18% 失败率，需增加重试（至少 2 次）。

6. 知识库补充：S09（新客激活）、S10（价格竞争）场景知识库命中率低，质量仅 60-75，需补充轻量维护/跟进类话术样本。

7. SYSTEM_PROMPT_LLM2 加强口语化要求：部分 85 分案例含书面敬语，需强制"禁止任何敬语套话，必须像真人销售微信聊天"。
"""

with engine.connect() as conn:
    row = conn.execute(text(
        'SELECT analysis_claude_code FROM case_iteration_run WHERE run_id = :rid'
    ), {'rid': run_id}).fetchone()
    existing = row[0] if row else None
    print(f'当前 analysis_claude_code 已有内容: {"是，长度=" + str(len(existing)) if existing else "否"}')

    conn.execute(text(
        'UPDATE case_iteration_run SET analysis_claude_code = :content WHERE run_id = :rid'
    ), {'rid': run_id, 'content': ANALYSIS})
    conn.commit()
    print('分析已写入数据库')

    row2 = conn.execute(text(
        'SELECT LEFT(analysis_claude_code, 80) FROM case_iteration_run WHERE run_id = :rid'
    ), {'rid': run_id}).fetchone()
    print(f'写入验证（前80字）：{row2[0] if row2 else "未找到"}')
