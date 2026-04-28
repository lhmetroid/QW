from __future__ import annotations

import json

from database import SessionLocal
from main import AnalysisCompletionRequest, _complete_analysis_items


def main() -> int:
    db = SessionLocal()
    try:
        payload = AnalysisCompletionRequest(
            source_type="email_excel",
            rebuild_candidate_governance=True,
            backfill_email_assets=True,
            backfill_thread_facts=True,
            bootstrap_positive_feedback_count=3,
            bootstrap_feedback_status="adopted",
            extract_excellent_replies=True,
            prepare_training_samples=True,
            export_training_samples=True,
            sample_types=["embedding_corpus", "reply_fragment_sft", "thread_reply_sft", "retrieval_pair"],
            min_quality_score=0.45,
            min_effect_score=0.45,
            limit_per_source=200,
            max_samples=500,
            operator="complete_all_analysis_items.py",
        )
        result = _complete_analysis_items(db, payload)
        db.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
