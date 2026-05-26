# -*- coding: utf-8 -*-
import urllib.request, json, time, os
for line in open('.env',encoding='utf-8'):
    line=line.strip()
    if line and '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); os.environ.setdefault(k,v)
url=os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')
import psycopg

def backend_up():
    try:
        c=urllib.request.urlopen('http://127.0.0.1:8071/api/case_lib/iterations',timeout=8).getcode()
        return c==200
    except Exception: return False

def embed_ok():
    try:
        body=json.dumps({'model':'qllama/bge-m3:latest','prompt':'连通测试'}).encode()
        req=urllib.request.Request('http://10.0.0.222:11434/api/embeddings',data=body,headers={'Content-Type':'application/json'})
        r=json.loads(urllib.request.urlopen(req,timeout=12).read())
        return bool(r.get('embedding') and len(r['embedding'])==1024)
    except Exception: return False

# Phase 1: wait backend up
for _ in range(40):
    if backend_up(): print('backend UP',flush=True); break
    time.sleep(5)
else:
    print('backend 未就绪,放弃',flush=True); raise SystemExit(0)

# Phase 2: wait embedding stable (2 consecutive ok), cap ~2.5h
streak=0
for i in range(40):
    if embed_ok():
        streak+=1; print(f'[probe {i}] embedding ok streak={streak}',flush=True)
        if streak>=2: break
    else:
        streak=0
        if i%5==0: print(f'[probe {i}] embedding still down',flush=True)
    time.sleep(240)
else:
    print('=== embedding 2.5h 未稳定恢复,未发起 v18 ===',flush=True); raise SystemExit(0)

# Phase 3: trigger v18
print('=== embedding 恢复, 触发 v18 ===',flush=True)
body=json.dumps({'mode':'real','triggered_by':'claude_code','change_summary':'v18: 测A类4动作模板切片(邮件未收到0.72/守价0.57/拉会/巴葡,KB doc 30262d2c)+validate编造兜底 对生成链路的影响'},ensure_ascii=False).encode('utf-8')
req=urllib.request.Request('http://127.0.0.1:8071/api/case_lib/iterations/start',data=body,headers={'Content-Type':'application/json'},method='POST')
resp=json.loads(urllib.request.urlopen(req,timeout=40).read())
run_id=resp.get('iteration',{}).get('run_id'); vno=resp.get('iteration',{}).get('version_no')
print(f'triggered run_id={run_id} version={vno} status={resp.get("status")}',flush=True)
if not run_id: raise SystemExit(0)

# Phase 4: poll until finished
for _ in range(260):
    with psycopg.connect(url) as conn:
        cur=conn.cursor()
        cur.execute('SELECT status,success_cases,failed_cases FROM case_iteration_run WHERE run_id=%s',(run_id,))
        st,sc,fc=cur.fetchone()
    if st in ('success','failed','partial'):
        print(f'=== v{vno} FINISHED status={st} success={sc} failed={fc} ===',flush=True); break
    time.sleep(12)
