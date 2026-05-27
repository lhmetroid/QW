import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case56: 49038630 客户回复确认，随后销售发送推广内容 (5 turns)
    "49038630-40b3-43bc-a66f-1680934511d8": {
        1: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 92, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 82, "low_barrier": 90, "non_repetition": 90, "safety": 88, "style_match": 85, "context_alignment": 92}, "score_method": "manual"},
    },
    # case57: 832681fa 感谢回复与未来合作期待 (5 turns)
    # T5: low_barrier=72 触发cap(<=84)，实际计算值81，符合cap
    "832681fa-b523-4785-8fd3-14668f92cfca": {
        1: {"overall": 87, "dims": {"conciseness": 80, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        2: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 80, "non_repetition": 90, "safety": 85, "style_match": 85, "context_alignment": 82}, "score_method": "manual"},
        4: {"overall": 87, "dims": {"conciseness": 82, "low_barrier": 86, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 81, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 90, "safety": 80, "style_match": 85, "context_alignment": 72}, "score_method": "manual"},
    },
    # case58: 43515d9e 转介绍请求与存量裂变 (5 turns)
    # T1-T4 overlaps 085a8fa5 T2-T5 / 72d93794 T1-T4 (rows 11058-11069)
    "43515d9e-2681-4fd0-9507-1bf411279c05": {
        1: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 85, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 82, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 86, "non_repetition": 90, "safety": 88, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
    },
    # case59: 72d93794 转介绍请求与存量裂变 (5 turns)
    # T1-T4 overlaps 43515d9e T1-T4 / 085a8fa5 T2-T5 (rows 11058-11069)
    # T5 row 11070-11071 (单条回复，干净暖收)
    "72d93794-0a65-43ff-8a9c-76d52d90e941": {
        1: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 85, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 82, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
    },
    # case60: 085a8fa5 转介绍请求与存量裂变 (5 turns)
    # T2-T5 overlaps 43515d9e T1-T4 / 72d93794 T1-T4 (rows 11058-11069)
    "085a8fa5-dca8-4753-9b6b-7e9b4794d185": {
        1: {"overall": 87, "dims": {"conciseness": 82, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 88, "low_barrier": 82, "non_repetition": 90, "safety": 85, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        5: {"overall": 86, "dims": {"conciseness": 82, "low_barrier": 85, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
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
