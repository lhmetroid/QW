import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case41: cbbe0320 新年开工问候及业务回顾
    "cbbe0320-5462-445a-9ee1-5ddfce1697fe": {
        1: {"overall": 88, "dims": {"conciseness": 85, "low_barrier": 86, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 82, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
    },
    # case42: b3eb22b7 活动案例分享及问候
    "b3eb22b7-04dc-49fb-b5df-41a02a8ebff0": {
        1: {"overall": 86, "dims": {"conciseness": 82, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 85, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 80, "style_match": 85, "context_alignment": 78}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 82, "low_barrier": 88, "non_repetition": 88, "safety": 88, "style_match": 92, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 80, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 88, "safety": 80, "style_match": 82, "context_alignment": 68}, "score_method": "manual"},
    },
    # case43: 1b84e2d5 新年开工问候 (T1 overlaps case39/5f45f127 T4; T2 overlaps case39 T5 and 82c645a5 T1)
    "1b84e2d5-c3da-4a8e-b50f-20bffcd67413": {
        1: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
    },
    # case44: ecb62d11 确认邮件内容及翻译需求
    "ecb62d11-1f25-4827-b73f-d4a90a645652": {
        1: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 90, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 82, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
    },
    # case45: 82c645a5 开工问候 (T1-T4 overlap 1b84e2d5 T2-T5)
    "82c645a5-8bc7-4329-b982-90647ed35a7c": {
        1: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 93, "context_alignment": 92}, "score_method": "manual"},
    },
}

db = SessionLocal()
try:
    for case_id, scores in all_cases.items():
        turns = db.query(CaseLibraryDialogueTurn).filter_by(case_id=case_id).order_by(CaseLibraryDialogueTurn.turn_no).all()
        print(f"{case_id[:8]}: {len(turns)} turns")
        for t in turns:
            s = scores[t.turn_no]
            t.actual_sales_score = float(s["overall"])
            t.actual_sales_scores = s
            t.score_status = "manual_scored"
            print(f"  T{t.turn_no}: {s['overall']}")
    db.commit()
    print("All committed.")
finally:
    db.close()
