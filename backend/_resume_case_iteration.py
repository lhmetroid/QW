import io
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))


def load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env(os.path.join(os.path.dirname(__file__), "..", ".env"))
os.environ["PORT"] = os.environ.get("CASELIB_BACKEND_PORT") or "8071"

from database import CaseIterationResult, CaseIterationRun, CaseLibraryCase, SessionLocal
from main import (
    _caselib_compose_ai_next_plan,
    _caselib_compose_improvement_analysis,
    _caselib_run_real,
    _caselib_serialize_case,
)


RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "716914b9-1cdb-43de-b007-bba5ca68112b"


def apply_output(rr: CaseIterationResult, out: dict) -> bool:
    rr.step1_summary = out.get("step1_summary")
    rr.step2_crm_info = out.get("step2_crm_info")
    rr.step3_thread_business_fact = out.get("step3_thread_business_fact")
    rr.step4_knowledge = out.get("step4_knowledge")
    rr.step5_llm1_compare = out.get("step5_llm1_compare")
    rr.step6_sales_advice = out.get("step6_sales_advice")
    rr.step6_compare_advice = out.get("step6_compare_advice")
    rr.step7_reply_styles = out.get("step7_reply_styles")
    rr.step7_reply_scores = out.get("step7_reply_scores")
    rr.snapshot_id = out.get("snapshot_id")
    rr.quality_score = out.get("quality_score")
    rr.kb1_eval_score = out.get("kb1_eval_score")
    rr.kb2_eval_score = out.get("kb2_eval_score")
    rr.quality_status = (out.get("quality_status") or "")[:50]
    rr.latency_ms = out.get("latency_ms")
    rr.stage_status = out.get("stage_status")
    rr.error_message = out.get("error_message") or None
    return out.get("quality_status") == "real_success"


def recompute_run_summary(db, run: CaseIterationRun) -> None:
    rows = (
        db.query(CaseIterationResult)
        .filter(CaseIterationResult.run_id == RUN_ID)
        .all()
    )
    scores = [
        float(r.quality_score)
        for r in rows
        if r.quality_status == "real_success" and r.quality_score is not None
    ]
    latencies = [
        int(r.latency_ms)
        for r in rows
        if r.quality_status == "real_success" and r.latency_ms is not None
    ]
    run.total_cases = len(rows)
    run.completed_cases = sum(1 for r in rows if r.status in {"success", "failed"})
    run.success_cases = sum(1 for r in rows if r.quality_status == "real_success")
    run.failed_cases = sum(1 for r in rows if r.status == "failed")
    if scores:
        run.avg_quality_score = round(sum(scores) / len(scores), 2)
        run.min_quality_score = round(min(scores), 2)
        run.max_quality_score = round(max(scores), 2)
    if latencies:
        run.avg_latency_ms = int(sum(latencies) / len(latencies))
    if run.completed_cases >= run.total_cases:
        run.status = "success" if run.failed_cases == 0 else ("partial" if run.success_cases > 0 else "failed")
        run.finished_at = datetime.utcnow()
        run.improvement_analysis = _caselib_compose_improvement_analysis(db, run, scores)
        run.ai_next_step_plan = _caselib_compose_ai_next_plan(run, db)


def main() -> int:
    db = SessionLocal()
    try:
        run = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == RUN_ID).first()
        if not run:
            print(f"run not found: {RUN_ID}")
            return 2
        run.status = "running"
        run.finished_at = None
        db.commit()

        cases = (
            db.query(CaseLibraryCase)
            .order_by(CaseLibraryCase.scenario_code, CaseLibraryCase.scenario_rank)
            .all()
        )
        for case in cases:
            rr = (
                db.query(CaseIterationResult)
                .filter(
                    CaseIterationResult.run_id == RUN_ID,
                    CaseIterationResult.case_id == case.case_id,
                )
                .first()
            )
            if rr and rr.quality_status == "real_success":
                continue
            if not rr:
                rr = CaseIterationResult(
                    run_id=RUN_ID,
                    case_id=case.case_id,
                    scenario_code=case.scenario_code,
                    scenario_rank=case.scenario_rank,
                    status="queued",
                )
                db.add(rr)
                db.commit()
                db.refresh(rr)

            label = f"{case.scenario_code}-{case.scenario_rank}"
            print(f"[{datetime.now().isoformat(timespec='seconds')}] resume {label}", flush=True)
            rr.status = "running"
            rr.started_at = datetime.utcnow()
            rr.finished_at = None
            rr.error_message = None
            db.commit()

            try:
                out = _caselib_run_real(_caselib_serialize_case(case), run_id=RUN_ID)
                ok = apply_output(rr, out)
                rr.status = "success" if ok else "failed"
                if not ok and not rr.error_message:
                    rr.error_message = rr.quality_status or "real mode failed"
                print(f"  -> {rr.status} {rr.quality_status} score={rr.quality_score}", flush=True)
            except Exception as exc:
                rr.status = "failed"
                rr.quality_status = "resume_error"
                rr.error_message = str(exc)[:500]
                print(f"  -> failed resume_error {exc}", flush=True)
            rr.finished_at = datetime.utcnow()
            recompute_run_summary(db, run)
            db.commit()

        recompute_run_summary(db, run)
        db.commit()
        print("resume complete", flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
