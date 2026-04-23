from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from sqlalchemy import func, text

from crm_database import CRMSessionLocal
from database import IntentSummary, KnowledgeHitLog, MessageLog, SessionLocal


SESSION_RE = re.compile(r"^single_(?P<sales>.+?)_(?P<external>(?:wm|wo|wb)[A-Za-z0-9_-]+)$")


@dataclass
class RepairCandidate:
    old_session_id: str
    new_session_id: str
    sales_userid: str
    truncated_external_userid: str
    full_external_userid: str
    message_count: int


def parse_single_session_id(session_id: str) -> tuple[str, str] | None:
    match = SESSION_RE.match(session_id or "")
    if not match:
        return None
    return match.group("sales"), match.group("external")


def find_full_external_userid(crm_db, truncated_external_userid: str) -> list[str]:
    rows = crm_db.execute(
        text(
            """
            SELECT DISTINCT external_userid
            FROM usrCustomerContactWebChartList
            WHERE external_userid LIKE :prefix
            ORDER BY external_userid
            """
        ),
        {"prefix": f"{truncated_external_userid}%"},
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def build_manual_candidate(target: str, full_external_userid: str) -> RepairCandidate:
    app_db = SessionLocal()
    try:
        parsed = parse_single_session_id(target)
        if not parsed:
            raise RuntimeError(f"target is not a supported single session id: {target}")
        sales_userid, truncated_external_userid = parsed
        if not full_external_userid.startswith(truncated_external_userid):
            raise RuntimeError(
                f"full external_userid is not prefixed by truncated value: "
                f"{truncated_external_userid} -> {full_external_userid}"
            )
        message_count = (
            app_db.query(func.count(MessageLog.id))
            .filter(MessageLog.user_id == target)
            .scalar()
            or 0
        )
        return RepairCandidate(
            old_session_id=target,
            new_session_id=f"single_{sales_userid}_{full_external_userid}",
            sales_userid=sales_userid,
            truncated_external_userid=truncated_external_userid,
            full_external_userid=full_external_userid,
            message_count=int(message_count),
        )
    finally:
        app_db.close()


def collect_candidates(limit: int | None = None, target: str | None = None) -> list[RepairCandidate]:
    app_db = SessionLocal()
    crm_db = CRMSessionLocal()
    try:
        query = (
            app_db.query(MessageLog.user_id, func.count(MessageLog.id).label("message_count"))
            .filter(MessageLog.is_mock.is_(False))
            .filter(MessageLog.user_id.like("single_%"))
            .group_by(MessageLog.user_id)
            .having(func.length(MessageLog.user_id) == 50)
            .order_by(func.max(MessageLog.timestamp).desc())
        )
        if target:
            query = query.filter(MessageLog.user_id == target)
        if limit:
            query = query.limit(limit)

        candidates: list[RepairCandidate] = []
        for old_session_id, message_count in query.all():
            parsed = parse_single_session_id(old_session_id)
            if not parsed:
                continue
            sales_userid, truncated_external_userid = parsed
            matches = find_full_external_userid(crm_db, truncated_external_userid)
            if len(matches) != 1:
                print(
                    f"SKIP {old_session_id}: crm_prefix_matches={len(matches)} "
                    f"prefix={truncated_external_userid}"
                )
                continue
            full_external_userid = matches[0]
            if full_external_userid == truncated_external_userid:
                continue
            new_session_id = f"single_{sales_userid}_{full_external_userid}"
            candidates.append(
                RepairCandidate(
                    old_session_id=old_session_id,
                    new_session_id=new_session_id,
                    sales_userid=sales_userid,
                    truncated_external_userid=truncated_external_userid,
                    full_external_userid=full_external_userid,
                    message_count=int(message_count or 0),
                )
            )
        return candidates
    finally:
        crm_db.close()
        app_db.close()


def apply_candidate(candidate: RepairCandidate) -> dict:
    db = SessionLocal()
    try:
        new_message_count = (
            db.query(func.count(MessageLog.id))
            .filter(MessageLog.user_id == candidate.new_session_id)
            .scalar()
            or 0
        )
        if new_message_count:
            raise RuntimeError(
                f"target session already has {new_message_count} messages: {candidate.new_session_id}"
            )

        message_rows = (
            db.query(MessageLog)
            .filter(MessageLog.user_id == candidate.old_session_id)
            .update({MessageLog.user_id: candidate.new_session_id}, synchronize_session=False)
        )
        summary_rows = (
            db.query(IntentSummary)
            .filter(IntentSummary.user_id == candidate.old_session_id)
            .update({IntentSummary.user_id: candidate.new_session_id}, synchronize_session=False)
        )
        hit_log_rows = (
            db.query(KnowledgeHitLog)
            .filter(KnowledgeHitLog.session_id == candidate.old_session_id)
            .update({KnowledgeHitLog.session_id: candidate.new_session_id}, synchronize_session=False)
        )
        db.commit()
        return {
            "message_logs": message_rows,
            "intent_summaries": summary_rows,
            "knowledge_hit_logs": hit_log_rows,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair historical 50-char-truncated single session IDs by matching CRM external_userid prefixes."
    )
    parser.add_argument("--apply", action="store_true", help="apply updates; default is dry-run only")
    parser.add_argument("--limit", type=int, default=0, help="limit scanned len=50 sessions")
    parser.add_argument("--target", default="", help="repair one exact old session_id")
    parser.add_argument(
        "--full-external-userid",
        default="",
        help="known complete external_userid for --target; skips CRM prefix lookup",
    )
    args = parser.parse_args()

    if args.full_external_userid:
        if not args.target:
            raise SystemExit("--full-external-userid requires --target")
        candidates = [build_manual_candidate(args.target, args.full_external_userid)]
    else:
        candidates = collect_candidates(limit=args.limit or None, target=args.target or None)
    print(f"repair_candidates={len(candidates)} mode={'apply' if args.apply else 'dry-run'}")
    for item in candidates:
        print(
            f"{item.old_session_id} -> {item.new_session_id} "
            f"messages={item.message_count} external={item.full_external_userid}"
        )
        if args.apply:
            result = apply_candidate(item)
            print(f"  updated={result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
