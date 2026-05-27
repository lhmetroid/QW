import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case26: 2a542f6d 询问上一笔费用支付情况
    "2a542f6d-cbf6-4f90-abb7-c981f97e7693": {
        1: {"overall": 89, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 84, "dims": {"conciseness": 82, "low_barrier": 78, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
    },
    # case27: 56868114 询问上一笔费用支付情况
    "56868114-2b4b-4ac2-9f5a-03882429b6a5": {
        1: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 84, "dims": {"conciseness": 82, "low_barrier": 78, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 80}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 92, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 78}, "score_method": "manual"},
    },
    # case28: 63ad540f 关于发票备注填写PO号的沟通
    "63ad540f-19cf-4e85-9230-74da480d4e6f": {
        1: {"overall": 88, "dims": {"conciseness": 87, "low_barrier": 88, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 89, "dims": {"conciseness": 87, "low_barrier": 90, "non_repetition": 88, "safety": 88, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 88, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 92, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 88, "dims": {"conciseness": 87, "low_barrier": 86, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
    },
    # case29: dbabd538 邮件未收到
    "dbabd538-1422-4990-b14f-a77bbd8f2af5": {
        1: {"overall": 88, "dims": {"conciseness": 87, "low_barrier": 86, "non_repetition": 88, "safety": 90, "style_match": 88, "context_alignment": 86}, "score_method": "manual"},
        2: {"overall": 91, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 85, "low_barrier": 83, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 82}, "score_method": "manual"},
        5: {"overall": 82, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 68}, "score_method": "manual"},
    },
    # case30: f19da4be 客户反馈技术有道翻译错误及销售请求可编辑版本
    "f19da4be-7c55-4107-a9f8-bea5977d4ae6": {
        1: {"overall": 84, "dims": {"conciseness": 85, "low_barrier": 75, "non_repetition": 88, "safety": 88, "style_match": 88, "context_alignment": 75}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 95, "low_barrier": 88, "non_repetition": 90, "safety": 90, "style_match": 90, "context_alignment": 88}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 89, "dims": {"conciseness": 94, "low_barrier": 85, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        5: {"overall": 91, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 90, "safety": 90, "style_match": 87, "context_alignment": 92}, "score_method": "manual"},
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
