import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case51: 028d4ad5 长期未合作客户的业务介绍与需求探询 (3 turns)
    "028d4ad5-d04a-4ab2-8a2b-e5c3d5273ba9": {
        1: {"overall": 86, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 82, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 92, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 92, "style_match": 93, "context_alignment": 92}, "score_method": "manual"},
    },
    # case52: a13e3f47 客户已换工作后销售询问新公司并保持联系 (3 turns)
    "a13e3f47-a0c7-4768-a635-e9ecd0f5d4a9": {
        1: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
    },
    # case53: 12d7e1b4 询问长时间未合作原因
    "12d7e1b4-e499-4dc3-a2fb-a99428b5f94b": {
        1: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 86, "dims": {"conciseness": 90, "low_barrier": 80, "non_repetition": 85, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 82, "non_repetition": 88, "safety": 85, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
    },
    # case54: 1b18acc5 您好，何老师
    "1b18acc5-53d7-40f4-9a52-caab79fb6f35": {
        1: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 83, "low_barrier": 88, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 78, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 75}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 80, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 78}, "score_method": "manual"},
        5: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 90, "safety": 85, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
    },
    # case55: 58035fa5 跟之前差不多 (all turns overlap 3909d6a2/S08 T1-T5)
    "58035fa5-148a-4868-bae9-552a30920d9f": {
        1: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 92, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 70}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 75}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 88, "safety": 90, "style_match": 92, "context_alignment": 85}, "score_method": "manual"},
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
