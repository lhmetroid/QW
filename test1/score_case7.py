import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

case_id = "81a9fa77-bdac-41c8-a21c-4c567d6e3427"

scores = {
    1: {
        "overall": 86,
        "dims": {"conciseness": 90, "low_barrier": 78, "non_repetition": 88,
                 "safety": 92, "style_match": 88, "context_alignment": 82},
        "score_method": "manual"
    },
    2: {
        "overall": 75,
        "dims": {"conciseness": 78, "low_barrier": 58, "non_repetition": 75,
                 "safety": 90, "style_match": 88, "context_alignment": 62},
        "score_method": "manual"
    },
    3: {
        "overall": 87,
        "dims": {"conciseness": 88, "low_barrier": 80, "non_repetition": 88,
                 "safety": 90, "style_match": 90, "context_alignment": 85},
        "score_method": "manual"
    },
    4: {
        "overall": 88,
        "dims": {"conciseness": 82, "low_barrier": 85, "non_repetition": 90,
                 "safety": 92, "style_match": 90, "context_alignment": 88},
        "score_method": "manual"
    },
    5: {
        "overall": 92,
        "dims": {"conciseness": 95, "low_barrier": 90, "non_repetition": 95,
                 "safety": 92, "style_match": 90, "context_alignment": 90},
        "score_method": "manual"
    },
}

db = SessionLocal()
try:
    turns = db.query(CaseLibraryDialogueTurn).filter_by(case_id=case_id).order_by(CaseLibraryDialogueTurn.turn_no).all()
    print(f"Found {len(turns)} turns for case {case_id}")
    for t in turns:
        s = scores.get(t.turn_no)
        if s:
            t.actual_sales_score = float(s["overall"])
            t.actual_sales_scores = s
            t.score_status = "scored"
            print(f"  Turn {t.turn_no}: overall={s['overall']}, dims={s['dims']}")
    db.commit()
    print("Committed successfully.")
finally:
    db.close()
