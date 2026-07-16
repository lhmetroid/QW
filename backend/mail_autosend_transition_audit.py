from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import bindparam, text

from crm_database import CRMSessionLocal
from database import SessionLocal


def chunks(values, size=200):
    values = list(values)
    for pos in range(0, len(values), size):
        yield values[pos:pos + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    check = json.loads(Path(args.check).read_text(encoding="utf-8"))
    plan_ids = [row.get("plan_id") for row in check.get("three_way_mismatches") or [] if row.get("plan_id")]
    pg = SessionLocal()
    crm = CRMSessionLocal()
    try:
        plans = pg.execute(
            text("SELECT plan_id,inputer_staff_id,COALESCE(crm_send_id,''),COALESCE(crm_send_status,''),"
                 "crm_fact_send_time,COALESCE(spqueue_rowid,'') FROM mail_customer_suite_send_plan "
                 "WHERE plan_id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": plan_ids},
        ).fetchall()
        sent = {}
        by_staff = defaultdict(list)
        for plan in plans:
            if plan[2]:
                by_staff[str(plan[1] or "")].append(str(plan[2]))
        for staff, send_ids in by_staff.items():
            if not staff.isalnum() or len(staff) > 8:
                continue
            for batch in chunks(set(send_ids)):
                params = {f"s{i}": value for i, value in enumerate(batch)}
                marks = ",".join(f":s{i}" for i in range(len(batch)))
                rows = crm.execute(text(
                    f"SELECT SendId,ISNULL(Status,''),FactSendTime,DeleteTime FROM [spSendInfo{staff}] "
                    f"WHERE SendId IN ({marks}) AND MessageType='Email'"
                ), params).fetchall()
                for row in rows:
                    sent[(staff, str(row[0]))] = row
        out = []
        counts = defaultdict(int)
        for plan in plans:
            truth = sent.get((str(plan[1] or ""), str(plan[2] or "")))
            if truth and str(truth[1] or "").lower() == "sendsuccess" and truth[3] is None:
                classification = "send_success"
            elif str(plan[3] or "").lower() == "deleted":
                classification = "deleted"
            else:
                classification = "unexpected_missing"
            counts[classification] += 1
            out.append({"plan_id": str(plan[0]), "staff": str(plan[1] or ""),
                        "send_id_present": bool(plan[2]), "cached_status": str(plan[3] or ""),
                        "classification": classification,
                        "crm_history_status": str(truth[1] or "") if truth else "",
                        "crm_history_present": bool(truth),
                        "crm_history_deleted": bool(truth and truth[3] is not None),
                        "fact_send_time": truth[2].isoformat() if truth and truth[2] else None})
        result = {"generated_at": datetime.now().isoformat(), "read_only": True,
                  "counts": dict(counts), "items": out}
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result["counts"], ensure_ascii=False))
        if counts.get("unexpected_missing"):
            raise SystemExit(1)
    finally:
        crm.close()
        pg.close()


if __name__ == "__main__":
    main()
