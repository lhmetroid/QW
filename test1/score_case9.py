import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseLibraryDialogueTurn

case_id = "e7936711-351c-4458-87c6-0b3dd9b2475d"

scores = {
    1: {"overall": 90, "dims": {"conciseness": 85, "low_barrier": 92, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 90}, "score_method": "manual"},
    2: {"overall": 91, "dims": {"conciseness": 88, "low_barrier": 90, "non_repetition": 92, "safety": 92, "style_match": 90, "context_alignment": 92}, "score_method": "manual"},
    3: {"overall": 93, "dims": {"conciseness": 95, "low_barrier": 92, "non_repetition": 95, "safety": 92, "style_match": 90, "context_alignment": 95}, "score_method": "manual"},
    4: {"overall": 88, "dims": {"conciseness": 90, "low_barrier": 82, "non_repetition": 90, "safety": 92, "style_match": 88, "context_alignment": 85}, "score_method": "manual"},
    5: {"overall": 84, "dims": {"conciseness": 75, "low_barrier": 80, "non_repetition": 88, "safety": 90, "style_match": 90, "context_alignment": 78}, "score_method": "manual"},
}

db = SessionLocal()
try:
    turns = db.query(CaseLibraryDialogueTurn).filter_by(case_id=case_id).order_by(CaseLibraryDialogueTurn.turn_no).all()
    print(f"Found {len(turns)} turns")
    for t in turns:
        s = scores[t.turn_no]
        t.actual_sales_score = float(s["overall"])
        t.actual_sales_scores = s
        t.score_status = "manual_scored"
        print(f"  T{t.turn_no}: {s['overall']}")
    db.commit()
    print("Done.")
finally:
    db.close()
