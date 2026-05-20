import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case21: 2d04774d 紧急响应邮件发送
    "2d04774d-60c3-4c4e-9174-05b4156845af": {
        1: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 87, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 92, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 87, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
    },
    # case22: 55afc6a2 确认未收到邮件
    "55afc6a2-61f9-41aa-bc9e-76a577bad82d": {
        1: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 92, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 87, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
    },
    # case23: 151cc149 确认未收到邮件
    "151cc149-1db5-4146-a513-e51f47c5d28e": {
        1: {"overall": 87, "dims": {"conciseness": 92, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 87, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 83, "dims": {"conciseness": 90, "low_barrier": 68, "non_repetition": 90, "safety": 90, "style_match": 85, "context_alignment": 70}, "score_method": "manual"},
    },
    # case24: 10e0c71e 紧急响应时间确认
    "10e0c71e-f463-4e61-9020-606bde3c2c41": {
        1: {"overall": 75, "dims": {"conciseness": 62, "low_barrier": 70, "non_repetition": 85, "safety": 88, "style_match": 68, "context_alignment": 62}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 93, "low_barrier": 82, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 82}, "score_method": "manual"},
        5: {"overall": 89, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 84}, "score_method": "manual"},
    },
    # case25: 876b625d 翻译审核请求与响应
    "876b625d-70f3-41da-85b7-f3ca294a659e": {
        1: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 93, "low_barrier": 82, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 82}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 84}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 85, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
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
