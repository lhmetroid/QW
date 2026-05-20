import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case46: f06f4af5 德企大连办公室开业活动案例分享
    "f06f4af5-e9aa-4e80-8516-9ca6e94b6bf8": {
        1: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        3: {"overall": 87, "dims": {"conciseness": 85, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 84, "dims": {"conciseness": 88, "low_barrier": 78, "non_repetition": 90, "safety": 82, "style_match": 85, "context_alignment": 80}, "score_method": "manual"},
        5: {"overall": 83, "dims": {"conciseness": 78, "low_barrier": 82, "non_repetition": 85, "safety": 85, "style_match": 85, "context_alignment": 85}, "score_method": "manual"},
    },
    # case47: fab3112c 请求并提供操作录屏演示 (all turns overlap 1ca406b6/S08)
    "fab3112c-b1cc-4031-9e54-4bd1c9d2d705": {
        1: {"overall": 83, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 68}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 87, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 85, "context_alignment": 92}, "score_method": "manual"},
    },
    # case48: 03d56a43 关于易派客展会和橡塑展的合作
    # T1=case38 T3, T2=case38 T4, T3=case38 T5, T5=case41 T1
    "03d56a43-6733-4b3c-9869-36cc59904e79": {
        1: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 78, "non_repetition": 90, "safety": 88, "style_match": 90, "context_alignment": 70}, "score_method": "manual"},
        2: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 80, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 75}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 88, "safety": 90, "style_match": 92, "context_alignment": 85}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 86, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 85, "low_barrier": 86, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
    },
    # case49: 779c06c3 播客形式培训案例介绍
    "779c06c3-3d61-49a8-b58c-96e887041c3f": {
        1: {"overall": 87, "dims": {"conciseness": 85, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 88, "safety": 88, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        5: {"overall": 83, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 82, "safety": 80, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
    },
    # case50: 9ef46548 成功案例分享
    "9ef46548-6c47-448d-b430-b87ad75dd9ee": {
        1: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 82, "dims": {"conciseness": 72, "low_barrier": 82, "non_repetition": 88, "safety": 85, "style_match": 85, "context_alignment": 78}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 85, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        4: {"overall": 92, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 90, "safety": 92, "style_match": 93, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 89, "dims": {"conciseness": 95, "low_barrier": 85, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
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
