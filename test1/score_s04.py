import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case16: 13bace8a 价格优惠请求及回复
    "13bace8a-cccf-4034-b5da-48452dfcf50e": {
        1: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 92, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 75, "dims": {"conciseness": 70, "low_barrier": 75, "non_repetition": 88, "safety": 65, "style_match": 82, "context_alignment": 65}, "score_method": "manual"},
        4: {"overall": 84, "dims": {"conciseness": 88, "low_barrier": 75, "non_repetition": 88, "safety": 90, "style_match": 85, "context_alignment": 72}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
    },
    # case17: a6e97c55 关于降价后质量下降的担忧
    "a6e97c55-efaf-4501-b509-55fb81422912": {
        1: {"overall": 92, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 93, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 84, "dims": {"conciseness": 90, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 85, "context_alignment": 75}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 92, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
    },
    # case18: 44bbbd80 关于特殊折扣价格的沟通
    "44bbbd80-305d-4a0b-bcc2-931db9661df4": {
        1: {"overall": 84, "dims": {"conciseness": 90, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 85, "context_alignment": 75}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 92, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        4: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 80}, "score_method": "manual"},
    },
    # case19: 6cf7341d 关于降价后质量下降的担忧
    "6cf7341d-ccaa-4ff2-ba4c-8f5675cd8517": {
        1: {"overall": 84, "dims": {"conciseness": 90, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 85, "context_alignment": 75}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 92, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        4: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 93, "low_barrier": 82, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
    },
    # case20: 38369346 关于特殊折扣价格的沟通
    "38369346-bccb-4613-abf0-b016b7d8f4db": {
        1: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 92, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 80}, "score_method": "manual"},
        5: {"overall": 84, "dims": {"conciseness": 90, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
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
