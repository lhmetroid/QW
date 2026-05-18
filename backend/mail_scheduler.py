"""
APScheduler-based mail sync scheduler.
Stores schedule config in mail_sync_schedule table.
Each enabled account has one IntervalTrigger job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC", job_defaults={"misfire_grace_time": 300})
    return _scheduler


def ensure_schedule_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS mail_sync_schedule (
            id SERIAL PRIMARY KEY,
            account_id INTEGER UNIQUE NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            job_type VARCHAR(32) NOT NULL DEFAULT 'incremental_sync',
            lookback_days INTEGER NOT NULL DEFAULT 7,
            last_run_at TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    db.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_sync_job(account_id: int, job_type: str, lookback_days: int) -> None:
    """Called by APScheduler in a background thread."""
    from database import SessionLocal
    from mail_sync import (run_imap_sync, run_gmail_sync, run_outlook_sync,
                           _account_to_sync_dict)

    db: Session = SessionLocal()
    try:
        account_row = db.execute(
            text("SELECT * FROM mail_account WHERE id = :id"),
            {"id": account_id}
        ).fetchone()
        if not account_row:
            logger.warning("[scheduler] account %s not found, skipping", account_id)
            return

        # Mark last_run_at before sync so UI reflects "running"
        db.execute(
            text("UPDATE mail_sync_schedule SET last_run_at = NOW(), updated_at = NOW() WHERE account_id = :id"),
            {"id": account_id}
        )
        db.commit()

        account = _account_to_sync_dict(account_row)
        provider = account.get("provider_type", "imap")
        logger.info("[scheduler] running sync account=%s provider=%s", account_id, provider)

        if provider == "gmail":
            run_gmail_sync(db, account_row, job_type)
        elif provider == "outlook":
            run_outlook_sync(db, account_row, job_type)
        else:
            run_imap_sync(db, account_row, job_type, lookback_days)

        logger.info("[scheduler] sync done account=%s", account_id)
    except Exception as exc:
        logger.error("[scheduler] sync account=%s failed: %s", account_id, exc)
    finally:
        db.close()


def _job_id(account_id: int) -> str:
    return f"mail_sync_{account_id}"


def add_account_schedule(account_id: int, interval_minutes: int,
                         job_type: str = "incremental_sync", lookback_days: int = 7) -> None:
    """Register or replace an interval sync job for account_id."""
    scheduler = get_scheduler()
    jid = _job_id(account_id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    scheduler.add_job(
        _run_sync_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=jid,
        args=[account_id, job_type, lookback_days],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("[scheduler] scheduled account=%s every %d min", account_id, interval_minutes)


def remove_account_schedule(account_id: int) -> None:
    scheduler = get_scheduler()
    jid = _job_id(account_id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
        logger.info("[scheduler] removed schedule account=%s", account_id)


def get_next_run(account_id: int) -> Optional[str]:
    scheduler = get_scheduler()
    job = scheduler.get_job(_job_id(account_id))
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def load_schedules_from_db(db: Session) -> None:
    """On startup: re-register all enabled schedules."""
    try:
        rows = db.execute(text(
            "SELECT account_id, interval_minutes, job_type, lookback_days "
            "FROM mail_sync_schedule WHERE enabled = TRUE"
        )).fetchall()
        for row in rows:
            add_account_schedule(row[0], row[1], row[2] or "incremental_sync", row[3] or 7)
        logger.info("[scheduler] loaded %d schedules from DB", len(rows))
    except Exception as exc:
        logger.warning("[scheduler] load_schedules_from_db failed: %s", exc)


def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("[scheduler] started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")
