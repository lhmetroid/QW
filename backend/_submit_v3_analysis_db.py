import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
from database import SessionLocal
from sqlalchemy import text

content = '''
## V3 测试分析与改进闭环

通过对 V3 轮次（全链路评测）的深挖排查，确认 V3 跑分机制存在以下核心漏洞，这些问题已在最新的 V4 轮次代码中被阻断：

### 1. 评分机制虚高（最高拿到92分但不具备可用性）
- **现象**：V3 轮次中，部分 AI 回复由于格式工整、话术没有硬伤，虽然篇幅长达百字以上，依然获得了 90+ 甚至 92 的高分，**导致“质量分”完全不能体现其作为微信销售话术的可用性。**
- **根本原因**：系统未严格执行 `overall` （总分）的计算公式。在 V3 中，评分引擎错误地接收了大模型自己随性打出的 `overall` 字段，而大模型天生不擅长字数限制，给出的分数普遍虚高。
- **已实施修复（在V4代码中）**：
  1. 剥夺了 LLM-1 直接给出总分的权限。
  2. 强制在后台采用公式：`overall = conciseness*0.18 + low_barrier*0.24 + non_repetition*0.22 + safety*0.22 + style_match*0.08 + context_alignment*0.06`
  3. 在 LLM-1 的 Prompt 中下达严苛指令：“超过50个字最高只给60分，超过80个字直接给0分”。经过这样的改造，类似 V3 中的冗长回复在 V4 之后会被立刻打不及格。

### 2. 销售原始回复评分为空值的原因
- **现象**：V3 面板中，很多实际销售的回复缺少评分，或者知识库得分为 `-`。
- **根本原因**：打分严重依赖外部模型 `zjsphs.2288.org:11599`，由于该接口极度不稳定（频繁触发 `read timeout=100`），导致打分链路被阻断，状态回退为 `llm1_failed`。
- **改善措施**：后续商业化落地必须为打分系统配置更轻量、更高可用的并发模型，并且引入失败重试与熔断机制。目前已尝试通过 `_rescore_sales_replies.py` 脚本补偿数据，但完全修复仍依赖接口稳定性。

### 3. V4 数据进度与结论
V3 的总结直接推导了 V4 迭代的开始。目前 V4 已通过真实模式 (`real`) 发起，但鉴于上述外部 LLM 接口的极度不稳定情况，V4 仍处于极其缓慢的运行状态。不过 V4 将产出极度挤出水分、绝对真实的严格质量分。
'''

db = SessionLocal()
try:
    db.execute(text('UPDATE case_iteration_run SET analysis_antigravity = :content WHERE version_no = 3'), {'content': content.strip()})
    db.commit()
    print('V3 updated successfully in DB.')
except Exception as e:
    print('Error:', e)
finally:
    db.close()
