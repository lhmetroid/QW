# -*- coding: utf-8 -*-
"""一次性脚本：为 60 个经典案例回填客户真实 external_userid 并测试 CRM 画像。

- 加列 case_library_case.external_userid（幂等）
- 按 group_key 从 wecom_raw_import(role='customer'.from_id) 找回真实 external_userid 并 UPDATE
- 全量调用 IntentEngine.get_crm_context 测试画像可用性，输出状态统计
"""
import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import text
from database import SessionLocal
from main import _caselib_real_external_userid
from intent_engine import IntentEngine


def main():
    db = SessionLocal()
    db.execute(text("ALTER TABLE case_library_case ADD COLUMN IF NOT EXISTS external_userid VARCHAR(120);"))
    db.commit()

    cases = db.execute(text(
        "SELECT case_id, scenario_code, scenario_rank, group_key FROM case_library_case "
        "ORDER BY scenario_code, scenario_rank"
    )).fetchall()
    print(f"案例总数: {len(cases)}")

    filled = 0
    missing_ext = []
    for case_id, sc, rank, gk in cases:
        ext = _caselib_real_external_userid(db, gk)
        if ext:
            db.execute(text("UPDATE case_library_case SET external_userid=:e WHERE case_id=:c"),
                       {"e": ext, "c": case_id})
            filled += 1
        else:
            missing_ext.append(f"{sc}-{rank}({gk})")
    db.commit()
    print(f"回填成功: {filled}/{len(cases)}；未找回: {len(missing_ext)}")
    if missing_ext:
        print("  未找回列表:", missing_ext)

    # 全量测试 CRM 画像
    status_count = {}
    success_samples = []
    problem = []
    rows = db.execute(text(
        "SELECT scenario_code, scenario_rank, external_userid FROM case_library_case "
        "ORDER BY scenario_code, scenario_rank"
    )).fetchall()
    for sc, rank, ext in rows:
        if not ext:
            status_count["no_external_userid"] = status_count.get("no_external_userid", 0) + 1
            problem.append(f"{sc}-{rank}: 无 external_userid")
            continue
        crm = IntentEngine.get_crm_context(ext)
        st = crm.get("crm_profile_status")
        status_count[st] = status_count.get(st, 0) + 1
        if st == "success" and len(success_samples) < 5:
            success_samples.append(f"{sc}-{rank}: {crm.get('crm_contact_name')} / {crm.get('company_name')}")
        if st not in ("success",):
            problem.append(f"{sc}-{rank}: status={st} err={crm.get('crm_profile_error')}")

    print("\n=== CRM 画像状态统计（60案例）===")
    for k, v in sorted(status_count.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("\n成功样本:")
    for s in success_samples:
        print("  ", s)
    if problem:
        print(f"\n非 success 明细（{len(problem)} 条）:")
        for p in problem:
            print("  ", p)
    db.close()


if __name__ == "__main__":
    main()
