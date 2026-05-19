"""保存三AI综合汇总到analysis_summary字段"""
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

SUMMARY = """## v3 三AI综合分析汇总（Codex + Antigravity + Claude Code，2026-05-19）

### 最终目的提示
本次分析服务于**商业化AI智能回复**落地——最终目标是销售拿到AI生成话术，无需任何修改，直接在企微复制发给客户。因此评分标准应严格以"可直接使用"为锚点，而非"格式正确""无硬伤"。

---

### 三AI一致结论

**1. v3 AI质量分整体虚高，不可作为优化基准**

三个AI均确认：v3的评分存在系统性虚高，偏高幅度约5~10分，核因有三：
- v3代码直接使用了LLM-1(qwen14b)返回的overall字段，而非公式计算值
- conciseness维度：qwen14b将"≤50字应高分"误解为"50分封顶"，23/49个案例给了错误的60-70分
- safety维度：49个案例中45%给了100分，78%给了≥90分，普通跟进话语不应给满分

修正后v3实际有效均分约**79~82分**（原显示87.63），最高90+案例均存在inflated问题。

**2. 关于"92分是否真高质量"——否**

v3中90+的案例回复本身口语化尚可，但：
- 按公式重算：90分实际约83~87分
- 从"直接可用"标准看：部分回复仍有"略显冗长""未提供具体数字""需要销售补充信息"等问题
- 这些不符合"销售直接复制就用"的标准

**3. 11个real_score_missing案例**

S06-3、S06-5、S02-4、S05-2、S07-2、S07-3、S06-4、S03-2、S07-1、S03-3、S03-1——AI回复生成成功，只是LLM-1评分超时/失败，quality_score=NULL。这11个案例不参与均分统计，需单独补评分。

**4. 销售原始分**

actual_sales_replies字段60/60均已入库，评分合理（4字"去问下哦"→30分、28字幽默破冰→90分）。UI若显示空白，是前端读取key错误（应读actual_sales_replies而非sales_scores）。

---

### 下一步具体优化项（逐项）

**【P0 评分机制——必须在下一轮前验证/修复】**

1. **验证公式覆盖生效**：确认score_reply_candidates中overall由公式计算，而非LLM直接给分；对比v4跑出的stored_overall与公式是否一致。

2. **修复conciseness Prompt**：在LLM-1评分prompt中明确加入："conciseness字数规则：≤50字可给80-95分，严禁对50字以内的回复给低于75分；50-80字给40-70分；>80字给0-30分。"

3. **修复safety Prompt**：加入："普通跟进/确认/报价类回复safety基准分为70-75，只有明确规避了客户违约风险、法律风险或品牌风险的回复才可给90+，禁止随意给100分。"

4. **总分硬约束规则**（代码层）：若conciseness<75 → overall上限84；若low_barrier<75 → overall上限84；若score_reason包含"未直接回应/缺关键事实/缺具体行动" → overall上限82。

**【P1 稳定性与数据修复】**

5. **LLM-1增加重试**：评分调用增加至少2次retry，单次timeout缩短至30s，全部失败才标llm1_failed；降低当前18%失败率。

6. **补打11个real_score_missing案例**：写脚本直接对已有ai_candidates重新调用score_reply_candidates，更新step7_reply_scores和quality_score字段，不需要重跑全链路。

7. **修复前端sales_scores读取**：前端渲染"销售原始分"列时改为读actual_sales_replies[].overall_score，而非sales_scores（后者不存在该key）。

**【P2 生成质量——下一轮内容层优化】**

8. **SYSTEM_PROMPT_LLM2强化口语化**：加入强制要求"回复必须≤50字；禁止任何敬语套话（您好、请问、感谢关注等）；必须像真人微信聊天，不得像邮件正文"。

9. **知识库补充（S09/S10场景）**：S09新客激活、S10价格竞争类场景知识库命中率低，质量只有60-75分，需从真实销售聊天记录中补充10-20条轻量维护跟进话术样本。

10. **检索严格度调整**：对无结果命中的案例，分别诊断是"知识库缺数据"还是"检索太严漏掉有效内容"；对后者考虑降低相似度阈值或扩大召回数量。

**【P3 分析与评估标准化】**

11. **建立可用性分级标准**：90+=直接可用无需修改；85-89=轻微修改（补一个数字或确认）可用；75-84=需销售润色；<75=不可直接用。下轮迭代以此分级而非原始均分来衡量进展。

12. **每轮分析必须覆盖全链路**：step4知识检索（命中率/相关性）、step6生成内容（口语化/字数）、step7评分（公式验证/分项分布）均需逐案例抽检，不能只看最终均分。

13. **下一轮启动前先人工抽检10条**：从v3有效49个案例中随机取10条，对照"直接可用"标准人工打分，与AI分对比，验证新评分参数是否校准到位，再启动v5。
"""

with engine.connect() as conn:
    conn.execute(text(
        'UPDATE case_iteration_run SET analysis_summary = :s WHERE run_id = :rid'
    ), {'rid': run_id, 's': SUMMARY})
    conn.commit()
    row = conn.execute(text(
        'SELECT LEFT(analysis_summary, 60) FROM case_iteration_run WHERE run_id = :rid'
    ), {'rid': run_id}).fetchone()
    print('汇总写入完成，验证前60字：', row[0] if row else '未找到')
