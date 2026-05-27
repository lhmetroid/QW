import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case36: 1ca406b6 面试过程的演示需求 (AI招聘软件)
    "1ca406b6-975c-4648-8fd5-4f6d0601b551": {
        1: {"overall": 83, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 68}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 87, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 85, "context_alignment": 92}, "score_method": "manual"},
    },
    # case37: 8ad0ed53 询问PPT翻译进度
    "8ad0ed53-a8ce-46e4-aa09-36e94ea67408": {
        1: {"overall": 89, "dims": {"conciseness": 85, "low_barrier": 90, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 93}, "score_method": "manual"},
        3: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        4: {"overall": 81, "dims": {"conciseness": 78, "low_barrier": 80, "non_repetition": 85, "safety": 80, "style_match": 85, "context_alignment": 75}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
    },
    # case38: 3909d6a2 问候及业务介绍
    "3909d6a2-23ad-4528-b389-1f36a8e618e2": {
        1: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 92, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 70}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 75}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 88, "safety": 90, "style_match": 92, "context_alignment": 85}, "score_method": "manual"},
    },
    # case39: 5f45f127 交付文件和术语表请求及回应
    "5f45f127-32ba-440a-9351-07dedce5512a": {
        1: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 95, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
    },
    # case40: 78ef6a41 确认文件翻译人员
    "78ef6a41-361e-43da-9f0f-daca69ebc94a": {
        1: {"overall": 91, "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 95, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 88, "dims": {"conciseness": 85, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
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
