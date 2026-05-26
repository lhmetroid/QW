# -*- coding: utf-8 -*-
import urllib.request, time, json, threading
RID='36c8125d-b282-4741-8bf1-a923b2e85033'
url=None
for line in open('.env',encoding='utf-8'):
    if line.startswith('DATABASE_URL='): url=line.split('=',1)[1].strip()
url=url.replace('postgresql+psycopg://','postgresql://')
import psycopg

def llm1_ok():
    try:
        urllib.request.urlopen('http://zjsphs.2288.org:11599/v1',timeout=6); return True
    except Exception as e:
        return 'timed out' not in str(e).lower() and 'refused' not in str(e).lower() and 'TimeoutError' not in type(e).__name__

def scored_count():
    with psycopg.connect(url) as conn:
        cur=conn.cursor()
        cur.execute("SELECT COUNT(*) FILTER (WHERE quality_score IS NOT NULL), COUNT(*) FROM case_iteration_result WHERE run_id=%s",(RID,))
        return cur.fetchone()

def fire_rescore():
    try:
        req=urllib.request.Request(f'http://127.0.0.1:8071/api/case_lib/iterations/{RID}/rescore',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
        urllib.request.urlopen(req,timeout=3000)
    except Exception as e:
        print('rescore POST returned/raised(server may continue):',type(e).__name__,flush=True)

# Phase A: wait endpoint stable (2 consecutive ok)
ok_streak=0
for i in range(45):  # ~3h at 240s
    if llm1_ok():
        ok_streak+=1; print(f'[probe {i}] LLM1 reachable streak={ok_streak}',flush=True)
        if ok_streak>=2: break
    else:
        ok_streak=0
        if i%5==0: print(f'[probe {i}] LLM1 still down',flush=True)
    time.sleep(240)
else:
    print('=== endpoint did not recover within 3h, giving up ===',flush=True); raise SystemExit(0)

print('=== LLM1 recovered, firing rescore ===',flush=True)
threading.Thread(target=fire_rescore,daemon=True).start()
# Phase C: poll commit
for _ in range(150):  # ~50min
    sc,tot=scored_count()
    if sc>=tot and tot>0:
        print(f'=== RESCORE COMMITTED scored={sc}/{tot} ===',flush=True); break
    time.sleep(20)
sc,tot=scored_count()
print(f'final scored={sc}/{tot}',flush=True)
