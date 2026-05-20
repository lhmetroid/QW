import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

all_cases = {
    # case11: 25e39a91 AI辅助线上面试及初步筛选流程
    "25e39a91-0b9e-4c1a-9eac-9301d7f773b4": {
        1: {"overall": 84, "dims": {"conciseness": 92, "low_barrier": 72, "non_repetition": 90, "safety": 92, "style_match": 90, "context_alignment": 70}, "score_method": "manual"},
        2: {"overall": 86, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 80, "safety": 92, "style_match": 85, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 93, "dims": {"conciseness": 93, "low_barrier": 95, "non_repetition": 93, "safety": 92, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        4: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 92, "safety": 92, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 88, "non_repetition": 80, "safety": 90, "style_match": 85, "context_alignment": 90}, "score_method": "manual"},
    },
    # case12: 8aebfe1d 关于二面系统功能的咨询
    "8aebfe1d-c311-4508-a3e1-3f5ea7ea0fc1": {
        1: {"overall": 86, "dims": {"conciseness": 80, "low_barrier": 88, "non_repetition": 80, "safety": 92, "style_match": 85, "context_alignment": 90}, "score_method": "manual"},
        2: {"overall": 93, "dims": {"conciseness": 93, "low_barrier": 95, "non_repetition": 93, "safety": 92, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 92, "safety": 92, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 88, "non_repetition": 80, "safety": 90, "style_match": 85, "context_alignment": 90}, "score_method": "manual"},
        5: {"overall": 92, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 93, "safety": 92, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
    },
    # case13: 8664a2d1 关于数据导入的用途和未来开发计划
    "8664a2d1-9bbe-45f2-84d4-24f9e912f3ca": {
        1: {"overall": 93, "dims": {"conciseness": 93, "low_barrier": 95, "non_repetition": 93, "safety": 92, "style_match": 88, "context_alignment": 95}, "score_method": "manual"},
        2: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 92, "safety": 92, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
        3: {"overall": 85, "dims": {"conciseness": 82, "low_barrier": 88, "non_repetition": 80, "safety": 90, "style_match": 85, "context_alignment": 90}, "score_method": "manual"},
        4: {"overall": 92, "dims": {"conciseness": 93, "low_barrier": 92, "non_repetition": 93, "safety": 92, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
    },
    # case14: 2c87f146 关于巴葡和普葡的选择
    "2c87f146-d8f6-45ef-bb9c-111e2cc5deca": {
        1: {"overall": 90, "dims": {"conciseness": 87, "low_barrier": 90, "non_repetition": 90, "safety": 92, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        2: {"overall": 92, "dims": {"conciseness": 92, "low_barrier": 92, "non_repetition": 92, "safety": 92, "style_match": 88, "context_alignment": 92}, "score_method": "manual"},
        3: {"overall": 90, "dims": {"conciseness": 90, "low_barrier": 88, "non_repetition": 90, "safety": 92, "style_match": 88, "context_alignment": 88}, "score_method": "manual"},
        4: {"overall": 88, "dims": {"conciseness": 88, "low_barrier": 85, "non_repetition": 88, "safety": 92, "style_match": 90, "context_alignment": 85}, "score_method": "manual"},
        5: {"overall": 75, "dims": {"conciseness": 70, "low_barrier": 75, "non_repetition": 88, "safety": 65, "style_match": 82, "context_alignment": 65}, "score_method": "manual"},
    },
    # case15: fc60379c 客户指定文件提交日期及后续沟通
    "fc60379c-090a-4915-8853-335188ffc0a5": {
        1: {"overall": 79, "dims": {"conciseness": 90, "low_barrier": 58, "non_repetition": 90, "safety": 85, "style_match": 80, "context_alignment": 62}, "score_method": "manual"},
        2: {"overall": 74, "dims": {"conciseness": 90, "low_barrier": 55, "non_repetition": 72, "safety": 85, "style_match": 80, "context_alignment": 58}, "score_method": "manual"},
        3: {"overall": 78, "dims": {"conciseness": 85, "low_barrier": 72, "non_repetition": 72, "safety": 85, "style_match": 82, "context_alignment": 80}, "score_method": "manual"},
        4: {"overall": 86, "dims": {"conciseness": 92, "low_barrier": 80, "non_repetition": 85, "safety": 88, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
        5: {"overall": 90, "dims": {"conciseness": 93, "low_barrier": 90, "non_repetition": 90, "safety": 90, "style_match": 88, "context_alignment": 90}, "score_method": "manual"},
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
