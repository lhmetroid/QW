"""真实模式 smoke：拿1个案例 -> 调本地 sidebar_assist -> 读 reply_chain_snapshot。"""
import os, sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    with open(p) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

os.environ['PORT'] = '8071'
os.environ['BACKEND_HOST'] = '127.0.0.1'

import main as M
from database import SessionLocal, CaseLibraryCase

db = SessionLocal()
c = db.query(CaseLibraryCase).filter(CaseLibraryCase.scenario_code == 'S04', CaseLibraryCase.scenario_rank == 1).first()
print(f'选案例: {c.scenario_code}-{c.scenario_rank} {c.case_title}')
print(f'  core_dialog={len(c.core_dialog) if isinstance(c.core_dialog, list) else "?"} msgs')

payload = M._caselib_serialize_case(c)
print(f'  serialized core={len(payload["core_dialog"])} ctx={len(payload["context_messages"])}')

# 直接调底层 sidebar_assist 看完整响应
import requests as _rq
cid = payload['case_id'][:12]
external_userid = f"caselib_ext_{cid}"
sales_userid = f"caselib_sales_smoke_te"
participants = sorted([sales_userid, external_userid])
session_id = f"single_{'_'.join(participants)}"
# 先插消息（与 _caselib_run_real 一致）
from sqlalchemy import text as _t
from datetime import datetime as _dt, timedelta as _td
_db = SessionLocal()
_db.execute(_t("DELETE FROM message_logs WHERE user_id=:sid"), {"sid": session_id})
all_msgs = (payload.get("context_messages") or []) + (payload.get("core_dialog") or [])
base_ts = _dt.utcnow() - _td(days=30)
for i, m in enumerate(all_msgs):
    try:
        ts = _dt.fromisoformat((m.get("msg_time") or base_ts.isoformat())[:19])
    except Exception:
        ts = base_ts + _td(seconds=i)
    _db.execute(_t("""INSERT INTO message_logs (user_id, sender_type, content, timestamp, is_mock)
                       VALUES (:uid, :st, :c, :ts, FALSE)"""),
                {"uid": session_id, "st": m.get("role") or "customer", "c": m.get("content") or "", "ts": ts})
_db.commit()
print(f'  inserted {len(all_msgs)} msgs to session_id={session_id}')

t0 = time.time()
resp = _rq.post("http://127.0.0.1:8071/api/wecom/sidebar_assist",
                json={"external_userid": external_userid, "userid": sales_userid,
                      "force_refresh": True, "sync_archive_before_read": False,
                      "trigger_source": "web_manual"}, timeout=180)
t1 = time.time()
print(f'\nsidebar_assist HTTP {resp.status_code} 耗时 {t1-t0:.1f}s')
body = resp.json() if resp.status_code == 200 else {}
print('--- top-level keys ---')
print(list(body.keys())[:30])
print('--- sales_advice_v2 ---')
print(repr((body.get('sales_advice_v2') or body.get('sales_advice') or '')[:200]))
print('--- summary topic ---')
print((body.get('summary') or {}).get('topic'))
print('--- stage_status ---')
print(json.dumps(body.get('stage_status'), ensure_ascii=False)[:600] if body.get('stage_status') else 'none')
print('--- reply_style_results_v2 (first 1) ---')
styles = body.get('reply_style_results_v2') or body.get('reply_style_results') or []
if isinstance(styles, list) and styles:
    print(json.dumps(styles[0], ensure_ascii=False)[:300])
else:
    print('none')
out = M._caselib_run_real(payload, run_id='smoke_test_real')
print(f'\n_caselib_run_real 复跑:')
print(f'  quality_status={out.get("quality_status")}')
print(f'  quality_score={out.get("quality_score")}')
print(f'  snapshot_id={out.get("snapshot_id")}')
print(f'  step1 topic={(out.get("step1_summary") or {}).get("topic","")[:80]}')
print(f'  step1 core_demand={(out.get("step1_summary") or {}).get("core_demand","")[:80]}')
print(f'  step6 sales_advice={(out.get("step6_sales_advice") or "")[:200]}')
db.close()
