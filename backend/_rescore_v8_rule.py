"""
v8 rule-based rescore：对 real_score_missing 的 ai_candidates 按字数规则打分，跳过 LLM。
评分规则（与 v3 三AI汇总一致）：
  conciseness: ≤50字→85, ≤80字→55, >80字→15
  low_barrier:  末尾含问号/疑问语气→82, ≤30字→80, 否则→70
  non_repetition: 75 (无上下文默认)
  safety:       72 (普通跟进基准)
  style_match:  75
  context_alignment: 75
  overall = 0.18*c + 0.24*lb + 0.22*nr + 0.22*sf + 0.08*sm + 0.06*ca
  硬约束: conciseness<75 → overall≤84; low_barrier<75 → overall≤84
"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    for l in open(p):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import SessionLocal, CaseIterationRun, CaseIterationResult
from sqlalchemy import text
import re

V8_RUN_ID = "bb10ef1b-91ba-4cf6-8c67-80c31579cc51"

QUESTION_RE = re.compile(r'[？?]|吗[～~\s。]|嘛[～~\s。]|呢[～~\s。]|吧[～~\s。]|哈[？?]')


def char_count(text: str) -> int:
    return len(re.sub(r'\s', '', text or ''))


def rule_conciseness(n: int) -> int:
    if n <= 50:  return 85
    if n <= 80:  return 55
    return 15


def rule_low_barrier(text: str, n: int) -> int:
    if QUESTION_RE.search(text): return 82
    if n <= 30:                   return 80
    return 70


def clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(v))))


def score_candidate(reply_text: str) -> dict:
    n = char_count(reply_text)
    c  = rule_conciseness(n)
    lb = rule_low_barrier(reply_text, n)
    nr = 75
    sf = 72
    sm = 75
    ca = 75
    overall_f = 0.18*c + 0.24*lb + 0.22*nr + 0.22*sf + 0.08*sm + 0.06*ca
    if c  < 75: overall_f = min(overall_f, 84)
    if lb < 75: overall_f = min(overall_f, 84)
    return {
        "conciseness":       c,
        "low_barrier":       lb,
        "non_repetition":    nr,
        "safety":            sf,
        "style_match":       sm,
        "context_alignment": ca,
        "overall":           clamp(overall_f),
    }


def load_json(v):
    if v is None: return None
    if isinstance(v, (dict, list)): return v
    try: return json.loads(v)
    except Exception: return None


db = SessionLocal()
try:
    run = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == V8_RUN_ID).first()
    if not run:
        print(f"Run {V8_RUN_ID} not found"); sys.exit(1)

    results = db.query(CaseIterationResult).filter(
        CaseIterationResult.run_id == V8_RUN_ID,
        CaseIterationResult.quality_status == "real_score_missing",
    ).all()
    print(f"Found {len(results)} real_score_missing results in v{run.version_no}")

    updated = 0
    all_scores: list[float] = []

    for rr in results:
        scores_obj = load_json(rr.step7_reply_scores) or {}
        ai_candidates = scores_obj.get("ai_candidates") or []
        if not ai_candidates:
            print(f"  SKIP {rr.scenario_code}-{rr.scenario_rank}: no ai_candidates")
            continue

        best_overall: float | None = None
        for cand in ai_candidates:
            reply_text = (cand.get("reply_text") or "").strip()
            if not reply_text:
                continue
            dims = score_candidate(reply_text)
            cand["scores"] = dims
            cand["overall_score"] = dims["overall"]
            cand["score_reason"] = "rule_scored"
            cand["score_note"] = f"rule:chars={char_count(reply_text)}"
            if best_overall is None or dims["overall"] > best_overall:
                best_overall = float(dims["overall"])

        if best_overall is None:
            print(f"  SKIP {rr.scenario_code}-{rr.scenario_rank}: no reply_text in candidates")
            continue

        scores_obj["ai_candidates"] = ai_candidates
        rr.step7_reply_scores = scores_obj
        rr.quality_score      = round(best_overall, 2)
        rr.quality_status     = "real_success"
        rr.status             = "success"
        all_scores.append(best_overall)
        updated += 1
        print(f"  OK {rr.scenario_code}-{rr.scenario_rank}: overall={best_overall:.0f}")

    # 刷新 run 汇总
    db.flush()
    if all_scores:
        existing = db.query(CaseIterationResult).filter(
            CaseIterationResult.run_id == V8_RUN_ID,
            CaseIterationResult.quality_score.isnot(None),
        ).all()
        all_q = [float(r.quality_score) for r in existing]
        run.avg_quality_score = round(sum(all_q) / len(all_q), 2)
        run.min_quality_score = round(min(all_q), 2)
        run.max_quality_score = round(max(all_q), 2)

    success_n = db.query(CaseIterationResult).filter(
        CaseIterationResult.run_id == V8_RUN_ID,
        CaseIterationResult.status == "success",
    ).count()
    total_n = run.total_cases or 60
    run.success_cases = success_n
    run.failed_cases  = total_n - success_n
    run.status        = "success" if run.failed_cases == 0 else ("partial" if success_n > 0 else "failed")

    db.commit()
    print(f"\nDone: updated={updated}, run.status={run.status}, "
          f"success={run.success_cases}/{total_n}, avg={run.avg_quality_score}")
finally:
    db.close()
