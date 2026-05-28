"""邮件黄金种子灌库脚本 (Phase 5 / Task 76)

把 docs/mail_gold_candidates/latest_mail_gold_candidates.json 里的 25 条
review-only 脱敏候选切片真实写入 email_fragment_asset 表，作为
POST /api/v1/mail/generate-draft 的 Few-Shot 检索数据源。

使用:
    cd backend && python seed_mail_gold_candidates.py
    # 或自定义路径:
    python seed_mail_gold_candidates.py --json /abs/path/to/seeds.json --dry-run

幂等:
    以 (source_type='mail_gold_seed', source_ref=<candidate_id>) 为唯一键，
    重复跑只 update 不 insert。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED_JSON = REPO_ROOT / "docs" / "mail_gold_candidates" / "latest_mail_gold_candidates.json"

sys.path.insert(0, str(REPO_ROOT / "backend"))

from database import EmailFragmentAsset, SessionLocal  # noqa: E402

SEED_SOURCE_TYPE = "mail_gold_seed"
SEED_LIBRARY_TYPE = "gold_seed"


def _to_decimal(value, default: str = "0.0") -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except Exception:
        return Decimal(default)


def _scenario_to_intent(scenario: str | None) -> str | None:
    return (scenario or "").strip().lower() or None


def upsert_seed(db, candidate: dict, idx: int) -> tuple[str, str]:
    """返回 (action, fragment_id_str)，action 取值 inserted / updated / skipped."""
    candidate_id = (candidate.get("candidate_id") or "").strip()
    if not candidate_id:
        return ("skipped", f"row#{idx}:missing_candidate_id")

    body_text = (candidate.get("body_text") or candidate.get("body_preview") or "").strip()
    if not body_text:
        return ("skipped", f"{candidate_id}:empty_body")

    subject = (candidate.get("subject") or candidate_id)[:255]
    scenario = (candidate.get("scenario") or "").strip()
    chinese_label = candidate.get("scenario_label") or scenario or "unknown"
    useful_score = _to_decimal(candidate.get("useful_score"), "0.6")

    existing = (
        db.query(EmailFragmentAsset)
        .filter(
            EmailFragmentAsset.source_type == SEED_SOURCE_TYPE,
            EmailFragmentAsset.source_ref == candidate_id,
        )
        .first()
    )

    if existing is None:
        item = EmailFragmentAsset(
            source_type=SEED_SOURCE_TYPE,
            source_ref=candidate_id,
            thread_id=candidate_id,
            title=subject,
            content=body_text,
        )
        db.add(item)
        db.flush()
        action = "inserted"
    else:
        item = existing
        item.title = subject
        item.content = body_text
        action = "updated"

    item.function_fragment = "example"
    item.scenario_label = scenario or chinese_label
    item.intent_label = _scenario_to_intent(scenario)
    item.language_style = "mixed_cn_en"
    item.library_type = SEED_LIBRARY_TYPE
    item.allowed_for_generation = True
    item.usable_for_reply = True
    item.publishable = True
    item.useful_score = useful_score
    item.topic_clarity_score = useful_score
    item.completeness_score = useful_score
    item.reusability_score = useful_score
    item.evidence_reliability_score = useful_score
    item.status = "ready"
    item.source_snapshot = {
        "seed_loader_version": "v1.7.198",
        "seed_source_file": str(DEFAULT_SEED_JSON.relative_to(REPO_ROOT)),
        "candidate_rank": candidate.get("rank"),
        "candidate_id": candidate_id,
        "sqlserver_source_ref": candidate.get("source_ref"),
        "scenario": scenario,
        "desensitized_status": candidate.get("desensitized_status"),
        "desensitized_fields": candidate.get("desensitized_fields") or [],
        "useful_score": float(useful_score),
        "score_source": candidate.get("score_source"),
    }
    item.quality_notes = {
        "loader": "seed_mail_gold_candidates.py",
        "review_only_seed": True,
    }
    return (action, str(item.fragment_id))


def main():
    parser = argparse.ArgumentParser(description="Seed email_fragment_asset with mail gold candidates")
    parser.add_argument("--json", default=str(DEFAULT_SEED_JSON), help="JSON file path")
    parser.add_argument("--dry-run", action="store_true", help="不提交事务，只打印将要做什么")
    args = parser.parse_args()

    seed_path = Path(args.json)
    if not seed_path.exists():
        print(f"[seed] ERROR: seed file not found: {seed_path}", file=sys.stderr)
        sys.exit(2)

    with seed_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    candidates = payload.get("candidates") or []
    print(f"[seed] 读到 {len(candidates)} 条候选，源文件: {seed_path}")

    db = SessionLocal()
    inserted = 0
    updated = 0
    skipped = 0
    try:
        for idx, candidate in enumerate(candidates, start=1):
            action, info = upsert_seed(db, candidate, idx)
            if action == "inserted":
                inserted += 1
                print(f"  [{idx:02d}] inserted  {info}  | {candidate.get('candidate_id')}")
            elif action == "updated":
                updated += 1
                print(f"  [{idx:02d}] updated   {info}  | {candidate.get('candidate_id')}")
            else:
                skipped += 1
                print(f"  [{idx:02d}] skipped   {info}")

        if args.dry_run:
            db.rollback()
            print(f"[seed] DRY-RUN 已回滚。inserted={inserted} updated={updated} skipped={skipped}")
        else:
            db.commit()
            print(f"[seed] COMMIT 完成。inserted={inserted} updated={updated} skipped={skipped}")

        total = (
            db.query(EmailFragmentAsset)
            .filter(EmailFragmentAsset.source_type == SEED_SOURCE_TYPE)
            .count()
        )
        print(f"[seed] 当前 email_fragment_asset 表中 source_type='{SEED_SOURCE_TYPE}' 共 {total} 行")
    finally:
        db.close()


if __name__ == "__main__":
    main()
