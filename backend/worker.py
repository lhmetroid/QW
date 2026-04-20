from __future__ import annotations

from datetime import datetime
from threading import Thread
from typing import Any, Callable

from database import JobTask, SessionLocal


def _update_job(job_id: str, **fields: Any) -> None:
    db = SessionLocal()
    try:
        job = db.query(JobTask).filter(JobTask.job_id == job_id).first()
        if not job:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        db.commit()
    finally:
        db.close()


def start_job(job_id: str, handler: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    def runner() -> None:
        _update_job(
            job_id,
            status="running",
            progress=5,
            started_at=datetime.utcnow(),
            finished_at=None,
            error_message=None,
        )

        def report(progress: int | None = None, summary: str | None = None, result_patch: dict | None = None) -> None:
            fields: dict[str, Any] = {}
            if progress is not None:
                fields["progress"] = max(0, min(int(progress), 100))
            if summary is not None:
                fields["summary"] = summary
            if result_patch is not None:
                db = SessionLocal()
                try:
                    job = db.query(JobTask).filter(JobTask.job_id == job_id).first()
                    if not job:
                        return
                    merged = dict(job.result or {})
                    merged.update(result_patch)
                    job.result = merged
                    for key, value in fields.items():
                        setattr(job, key, value)
                    db.commit()
                finally:
                    db.close()
                return
            if fields:
                _update_job(job_id, **fields)

        try:
            result = handler(report, *args, **kwargs)
            _update_job(
                job_id,
                status="success",
                progress=100,
                summary="completed",
                result=result,
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            _update_job(
                job_id,
                status="failed",
                progress=100,
                summary="failed",
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )

    Thread(target=runner, daemon=True).start()
