import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

def D(c, lb, nr, sf, sm, ca, ov):
    return {"overall": ov, "dims": {"conciseness": c, "low_barrier": lb, "non_repetition": nr,
            "safety": sf, "style_match": sm, "context_alignment": ca}, "score_method": "manual"}

all_cases = {
    # ===== S01 =====
    # 248b864f 印刷手册价格确认及文档类型确认
    # T3-T5 overlap 81a9fa77(S02) T1-T3 (rows 6738-6761)
    "248b864f-32a1-43d7-b659-9a6d70b4567f": {
        1: D(90, 85, 90, 90, 90, 82, 88),
        2: D(82, 88, 90, 90, 90, 90, 88),
        3: D(88, 90, 90, 88, 90, 90, 89),
        4: D(82, 88, 85, 88, 90, 88, 86),
        5: D(85, 88, 88, 90, 90, 90, 88),
    },
    # 89a2a8e2 900本笔记本规格单价和油卡报价建议
    # T1-T4 overlap bd4f0f48/f62107a7 (rows 1995-2011)
    "89a2a8e2-e972-4f89-9971-19992e4c14c7": {
        1: D(80, 85, 88, 88, 90, 88, 86),
        2: D(93, 90, 92, 92, 88, 92, 91),
        3: D(90, 90, 90, 90, 90, 92, 90),
        4: D(90, 82, 90, 85, 88, 88, 87),
        5: D(78, 85, 85, 88, 88, 88, 85),
    },
    # bd4f0f48 报价含税和6%开票确认
    # T3-T5 overlap f62107a7/89a2a8e2 (rows 1993-2003)
    "bd4f0f48-7ccf-473b-bf9e-3847a8d6ea9d": {
        1: D(90, 88, 90, 90, 88, 90, 89),
        2: D(92, 82, 90, 88, 88, 88, 88),
        3: D(92, 85, 90, 90, 90, 85, 89),
        4: D(80, 85, 88, 88, 90, 88, 86),
        5: D(93, 90, 92, 92, 88, 92, 91),
    },
    # 5c442242 场地布置费用归属说明 (全部独有)
    "5c442242-3ea0-4ffa-a3df-31ef616d985d": {
        1: D(90, 88, 88, 90, 90, 88, 89),
        2: D(85, 85, 88, 88, 90, 85, 87),
        3: D(92, 88, 90, 92, 88, 85, 90),
        4: D(90, 80, 88, 90, 88, 78, 86),
        5: D(90, 88, 88, 90, 88, 88, 89),
    },
    # f62107a7 不开票但总价不降的付款口径确认
    # T1-T5 全部 overlap bd4f0f48/89a2a8e2 (rows 1993-2011)
    "f62107a7-9e7e-4ea3-91be-e4b6c78aa31c": {
        1: D(92, 85, 90, 90, 90, 85, 89),
        2: D(80, 85, 88, 88, 90, 88, 86),
        3: D(93, 90, 92, 92, 88, 92, 91),
        4: D(90, 90, 90, 90, 90, 92, 90),
        5: D(90, 82, 90, 85, 88, 88, 87),
    },
    # ===== S02 =====
    # 6cb382d7 新联系人身份确认后的业务介绍和通话邀约 (全部独有)
    "6cb382d7-c1c8-47aa-9591-ada52b7326c9": {
        1: D(80, 85, 90, 88, 88, 88, 86),
        2: D(85, 88, 90, 90, 90, 88, 89),
        3: D(93, 88, 90, 92, 90, 88, 90),
        4: D(93, 90, 90, 90, 92, 90, 91),
        5: D(88, 88, 90, 90, 92, 85, 89),
    },
    # 81a9fa77 关于工厂找的服务
    # T1-T3 overlap 248b864f(S01) T3-T5 (rows 6738-6761)
    "81a9fa77-bdac-41c8-a21c-4c567d6e3427": {
        1: D(88, 90, 90, 88, 90, 90, 89),
        2: D(82, 88, 85, 88, 90, 88, 86),
        3: D(85, 88, 88, 90, 90, 90, 88),
        4: D(88, 86, 90, 85, 90, 88, 87),
        5: D(92, 85, 90, 85, 90, 88, 88),
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
