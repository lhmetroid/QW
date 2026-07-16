from __future__ import annotations

import ast
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "backend" / "main.py"
FRONTEND = ROOT / "frontend" / "mail-suite.html"
SOURCE = MAIN.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

FUNCTIONS = {
    "_autosend_cond_eval", "_autosend_rule_matches", "_autosend_resolve_partial_mode",
    "_autosend_pick_suite", "_autosend_schedule", "_autosend_parse_date_csv",
    "_autosend_holiday_set", "_cn_holiday_plan_sets", "_autosend_is_non_workday",
    "_autosend_next_workday",
}
NODES = []
for node in TREE.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS:
        NODES.append(node)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_CN_HOLIDAY_PLAN_BY_YEAR":
        NODES.append(node)

class _Logger:
    def warning(self, *_args, **_kwargs):
        pass

ns = {
    "Any": Any, "date": date, "datetime": datetime, "timedelta": timedelta,
    "re": re, "logger": _Logger(), "ALL_MAIL_SEQUENCE_STEPS": (1, 2, 3, 4),
    "_AUTOSEND_EXISTING_SUITE_OFFSET_DAYS": 7,
    "_get_scenario_label_cn": lambda scenario: scenario,
}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(MAIN), "exec"), ns)
ns["_autosend_scenario_step_count"] = lambda _scenario: 4
schedule = ns["_autosend_schedule"]
is_non_workday = ns["_autosend_is_non_workday"]

RULES = [{"scenario": "new_business_promotion", "conditions": [], "partial_sent_mode": "remaining"}]

def contacts(count: int):
    return [{
        "contact_id": f"KH-{i:04d}", "customer_id": f"KH-{i:04d}",
        "owner_staff_id": "0141", "company_name": f"C{i}", "contact_name": f"N{i}",
        "email": f"n{i}@example.com",
    } for i in range(count)]


def test_first_actual_anchor_and_intervals():
    result = schedule(contacts(1), RULES, [1, 10, 19, 25], 50, date(2026, 7, 16))
    rows = result["items"]
    assert [r["suite_step"] for r in rows] == [1, 2, 3, 4]
    days = [date.fromisoformat(r["plan_date"]) for r in rows]
    assert days[0] == date(2026, 7, 16), days
    for got, minimum in zip(days[1:], (9, 18, 24)):
        assert (got - days[0]).days >= minimum, days
    assert len(set(days)) == 4, days


def test_capacity_slots_and_no_same_day_suite():
    result = schedule(contacts(120), RULES, [1, 10, 19, 25], 50, date(2026, 7, 16))
    rows = result["items"]
    assert len(rows) == 480
    per_day = {}
    per_suite = {}
    occupied = set()
    for row in rows:
        key = (row["owner_staff_id"], row["plan_date"])
        per_day[key] = per_day.get(key, 0) + 1
        slot = key + (row["plan_time"],)
        assert slot not in occupied, slot
        occupied.add(slot)
        per_suite.setdefault(row["contact_id"], []).append(row)
    assert max(per_day.values()) <= 50, max(per_day.values())
    for key, count in per_day.items():
        times = sorted(r["plan_time"] for r in rows if (r["owner_staff_id"], r["plan_date"]) == key)
        minutes = [int(t[:2]) * 60 + int(t[3:5]) for t in times]
        assert all(b - a >= 10 for a, b in zip(minutes, minutes[1:])), (key, times)
    for suite_rows in per_suite.values():
        suite_rows.sort(key=lambda x: x["suite_step"])
        days = [date.fromisoformat(x["plan_date"]) for x in suite_rows]
        assert len(set(days)) == 4, days
        assert (days[1] - days[0]).days >= 9, days
        assert (days[2] - days[0]).days >= 18, days
        assert (days[3] - days[0]).days >= 24, days


def test_holiday_weekend_and_makeup_workday():
    holiday = schedule(contacts(1), RULES, [1, 10, 19, 25], 50, date(2026, 9, 25))["items"][0]
    assert holiday["plan_date"] == "2026-09-28", holiday
    makeup = schedule(contacts(1), RULES, [1, 10, 19, 25], 50, date(2026, 9, 20))["items"][0]
    assert makeup["plan_date"] == "2026-09-20", makeup
    assert is_non_workday(date(2026, 9, 25)) is True
    assert is_non_workday(date(2026, 9, 20)) is False


def test_reschedule_scope_and_time_only_crm_contract():
    assert "target.item_id IN :ids" in SOURCE
    assert "target.contact_id=i.contact_id AND target.scenario=i.scenario" in SOURCE
    assert "_autosend_reschedule_plan(db, staff, True, payload.item_ids)" in SOURCE
    assert "_autosend_reschedule_plan(db, staff, True, queued_ids)" in SOURCE
    helper = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_autosend_apply_crm_time_changes")
    helper_source = ast.get_source_segment(SOURCE, helper) or ""
    assert "UPDATE spQueueSend SET PlanSendTime=:dt" in helper_source
    forbidden = ("SET Subject", "SET EmailContent", "SET PureText", "EmlFtpPath=", "Receiver=")
    assert not any(x in helper_source for x in forbidden), helper_source
    assert "crm_pending_meta" in helper_source and "restore=True" not in helper_source


def test_whole_crm_pending_suite_is_rebuilt_from_saved_intervals():
    wanted = {
        "_autosend_parse_hhmm", "_autosend_fmt_hhmm", "_autosend_crm_pending_slots",
        "_autosend_reschedule_plan",
    }
    nodes = [n for n in TREE.body if
             (isinstance(n, ast.FunctionDef) and n.name in wanted) or
             (isinstance(n, ast.ClassDef) and n.name == "_AutosendSlotBook")]

    class Stmt:
        def __init__(self, value): self.value = value
        def bindparams(self, *_args, **_kwargs): return self
        def __str__(self): return self.value

    class Result:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows

    now = datetime.utcnow() + timedelta(hours=8)
    old_day = now.date() - timedelta(days=2)
    candidate_rows = [
        (f"item-{step}", "contact-1", "new_business_promotion", step, old_day, "09:00",
         "Company", "Contact", "sent", "1,10,19,25", "customer-1", "to@example.com", "run-1")
        for step in (1, 2, 3, 4)
    ]
    send_plans = [
        (f"plan-{step}", "customer-1", "new_business_promotion", step, "to@example.com",
         f"row-{step}", f"send-{step}", datetime.combine(old_day, datetime.min.time()), "WaitSend", None)
        for step in (1, 2, 3, 4)
    ]
    queue = [{"rowid": f"row-{step}", "send_id": f"send-{step}",
              "plan_dt": datetime.combine(old_day, datetime.min.time())}
             for step in (1, 2, 3, 4)]

    class DB:
        def execute(self, stmt, _params=None):
            sql = str(stmt)
            if "LEFT JOIN mail_autosend_run" in sql: return Result(candidate_rows)
            if "FROM mail_customer_suite_send_plan" in sql: return Result(send_plans)
            if "status IN ('sent','committing')" in sql: return Result([])
            if "SELECT item_id, plan_date, plan_time" in sql: return Result([])
            raise AssertionError(sql)

    local = {
        "Any": Any, "Session": object, "datetime": datetime, "timedelta": timedelta,
        "re": re, "text": Stmt, "bindparam": lambda *_a, **_k: None,
        "_AUTOSEND_MOVABLE_SQL_IN": "'planned','queued','drafting','drafted','commit_queued','commit_failed'",
        "_AUTOSEND_RESCHEDULE_LEAD_MINUTES": 10, "_AUTOSEND_RESCHEDULE_MAX_DAYS": 180,
        "_AUTOSEND_SLOT_GAP_MINUTES": 10, "_AUTOSEND_DAY_START_MINUTE": 540,
        "_AUTOSEND_DAY_END_MINUTE": 1110, "logger": _Logger(),
        "_autosend_receiver_key": lambda value: value,
        "_autosend_parse_interval_csv": lambda value: [int(x) for x in value.split(",")],
        "_autosend_get_or_create_config": lambda _db: object(),
        "_autosend_serialize_config": lambda _cfg: {"daily_cap": 50, "skip_non_workdays": True, "holiday_dates": []},
        "_autosend_crm_pending_snapshot": lambda _staff, _start: queue,
        "_autosend_crm_sent_snapshot": lambda _staff, _ids: {},
        "_autosend_next_workday": ns["_autosend_next_workday"],
        "_autosend_is_non_workday": ns["_autosend_is_non_workday"],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN), "exec"), local)
    slot_book = local["_AutosendSlotBook"]({}, 50, date(2026, 7, 16), 9 * 60, False, [])
    slot_day, slot_minute, _seq = slot_book.take(date(2026, 7, 17), 10 * 60 + 5)
    assert slot_day == date(2026, 7, 17)
    assert slot_minute == 10 * 60 + 10, slot_minute
    result = local["_autosend_reschedule_plan"](DB(), "0141", False, ["item-1"])
    assert result["crm_pending_movable"] == 4, result
    assert result["schedule_violations"] == 4, result
    assert result["changed"] == 4, result
    changes = sorted(result["changes"], key=lambda x: x["suite_step"])
    days = [date.fromisoformat(x["new_date"]) for x in changes]
    assert len(set(days)) == 4, days
    assert (days[1] - days[0]).days >= 9, days
    assert (days[2] - days[0]).days >= 18, days
    assert (days[3] - days[0]).days >= 24, days

def test_logical_suite_step_dedup_does_not_depend_on_date_or_subject():
    helper = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_mail_suite_existing_pending_plan")
    helper_source = ast.get_source_segment(SOURCE, helper) or ""
    assert "customer_id=:c AND scenario=:sc" in helper_source
    assert "suite_step=:st" in helper_source
    assert "recipient_email_key" in helper_source
    assert "FROM spQueueSend" in helper_source and "FolderId,'')='OutBox'" in helper_source

    key_fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_enqueue_dedup_key")
    key_source = ast.get_source_segment(SOURCE, key_fn) or ""
    assert "customer_id" in key_source and "scenario" in key_source and "suite_step" in key_source
    assert "subject" not in key_source and "plan_dt" not in key_source

    send_fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "send_mail_customer_suite")
    send_source = ast.get_source_segment(SOURCE, send_fn) or ""
    logical_check = send_source.index("_mail_suite_existing_pending_plan")
    crm_insert = send_source.index("_insert_spqueue_send_row")
    assert logical_check < crm_insert
    assert "MAIL_SUITE_LOGICAL_DUP_SKIP" in send_source

def test_shared_status_contract_and_frontend_colors():
    expected = {
        "WaitSend": "crm_pending", "Sending": "crm_pending",
        "SendSuccess": "send_success", "SendFail": "send_failed", "deleted": "deleted",
    }
    status_fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_mail_delivery_display_status")
    status_ns = {"Any": Any}
    exec(compile(ast.Module(body=[status_fn], type_ignores=[]), str(MAIN), "exec"), status_ns)
    for raw, want in expected.items():
        assert status_ns["_mail_delivery_display_status"](raw, "enqueued") == want
    html = FRONTEND.read_text(encoding="utf-8")
    assert "function mailDisplayStateMeta" in html
    assert "crm_pending:   { label: '待发送',   cls: 'border-sky-400 bg-sky-50 text-sky-700' }" in html
    assert "send_success:  { label: '已发送',   cls: 'border-emerald-400 bg-emerald-50 text-emerald-700' }" in html


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS all={len(tests)}")


if __name__ == "__main__":
    main()