# -*- coding: utf-8 -*-
"""发起 V9 验证批跑：仅前 2 个案例（10 轮），单版本 + 跳过评分（到 step6 截止）。

通过本地 8071 真实链路逐轮运行，结果写入 case_iteration_run / case_iteration_result，
可在「经典案例迭代优化 → 迭代详情」查看，供人工验证。
"""
import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from database import SessionLocal, CaseIterationRun
from main import (
    _caselib_resolve_git_info,
    _caselib_next_version_no,
    _caselib_run_iteration_background,
    CASELIB_EVAL_SINGLE_VERSION,
    CASELIB_EVAL_SKIP_SCORING,
)

MAX_CASES = 2


def main():
    db = SessionLocal()
    gi = _caselib_resolve_git_info()
    version_no = _caselib_next_version_no(db)
    run = CaseIterationRun(
        version_no=version_no,
        git_commit_sha=gi["sha"], git_short_sha=gi["short_sha"],
        git_branch=gi["branch"], git_dirty=gi["dirty"],
        changed_paths=[],
        change_summary=f"V9 验证批跑：前{MAX_CASES}案例(10轮) 单版本+跳过评分(到step6截止)",
        pipeline_config={
            "mode": "real",
            "max_cases": MAX_CASES,
            "eval_single_version": CASELIB_EVAL_SINGLE_VERSION,
            "eval_skip_scoring": CASELIB_EVAL_SKIP_SCORING,
        },
        status="queued",
        triggered_by="verify_first2",
        triggered_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = str(run.run_id)
    print(f"已创建 v{version_no} run_id={run_id}，开始跑前 {MAX_CASES} 个案例...")
    db.close()

    # 同步执行（内部逐轮 POST 到本地 8071 真实链路）
    _caselib_run_iteration_background(run_id, "real", MAX_CASES)

    # 汇报结果
    db = SessionLocal()
    from database import CaseIterationResult
    r = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == run_id).first()
    print(f"\n=== v{r.version_no} 完成：status={r.status} 总轮次={r.total_cases} 成功={r.success_cases} 失败={r.failed_cases} ===")
    rows = db.query(CaseIterationResult).filter(
        CaseIterationResult.run_id == run_id
    ).order_by(CaseIterationResult.scenario_code, CaseIterationResult.scenario_rank, CaseIterationResult.turn_no).all()
    for x in rows:
        crm = (x.step2_crm_info or {}) if isinstance(x.step2_crm_info, dict) else {}
        styles = x.step7_reply_styles or []
        n_cand = len(styles) if isinstance(styles, list) else 0
        advice = (x.step6_sales_advice or "").replace("\n", " ")[:40]
        print(f"  {x.scenario_code}-{x.scenario_rank} t{x.turn_no} | {x.quality_status} | 候选数={n_cand} | CRM={crm.get('crm_profile_status')}/{crm.get('crm_contact_name')} | step6: {advice}")
    db.close()
    print(f"\nrun_id={run_id} 可在 UI 迭代详情查看。")


if __name__ == "__main__":
    main()
