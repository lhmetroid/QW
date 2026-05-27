import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case31: a35d1f9b 预算限制及分期付款讨论
    "a35d1f9b-5834-440e-ba2e-245793137134": {
        1: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 75, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 78}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 80, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 93}, "score_method": "manual"},
    },
    # case32: c8f4844f 关于5000元以内报价的确认
    "c8f4844f-140c-4922-93ff-e375d23e463c": {
        1: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 85, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 85, "dims": {"conciseness": 78, "low_barrier": 82, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 86, "dims": {"conciseness": 82, "low_barrier": 86, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
    },
    # case33: f5f9c307 预算收紧 (T1-T4 overlap a35d1f9b T2-T5, T5 overlap c8f4844f T1)
    "f5f9c307-3f84-4fd7-b131-ab6a5f84b506": {
        1: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 86, "dims": {"conciseness": 80, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 93}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
    },
    # case34: 6109284b 预算收紧讨论 (T1-T4 overlap 8b94560a T2-T5)
    "6109284b-4299-499f-bc78-a589a2f4c563": {
        1: {"overall": 87, "dims": {"conciseness": 95, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 93}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 86, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        5: {"overall": 84, "dims": {"conciseness": 92, "low_barrier": 72, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
    },
    # case35: 8b94560a 预算收紧讨论 (T2-T5 overlap 6109284b T1-T4)
    "8b94560a-dde0-42eb-a958-36915d7bfd8a": {
        1: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 95, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 93}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 86, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
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
