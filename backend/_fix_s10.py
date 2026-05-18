"""
修复 S10 案例分享：
- 保留3个：S10-04会议室效果图参考、S10-05视频案例分享、S10-06AI演示录屏
- 替换7个：S10-01翻译修改（非S10）、S10-02首条表情缺上文、S10-03跨日+翻译定制、
           S10-07关键词154条发票纠纷、S10-08关键词133条印刷商谈判、
           S10-09关键词132条PPT+口译、S10-10关键词120条PPT翻译
"""
import os, sys, io, re
from datetime import datetime, date
from collections import defaultdict

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
from sqlalchemy import create_engine, text
url = os.environ.get('DATABASE_URL', '').replace('postgresql+psycopg://', 'postgresql+psycopg2://')
e = create_engine(url, connect_args={'connect_timeout': 30})

SALES_IDS = ('alicehe', 'davidXiaoMeiPeng', 'HanHan', 'joycesheng', 'WangHuiYing')
SC_NAME   = '案例分享'
SC_CODE   = 'S10'
MAX_DISPLAY = 16

KEEP_SESSIONS = [
    ('wri_a28e29584d1a_d125', date(2023,  9, 14)),  # S10-04 会议室图片印刷参考效果图
    ('wri_a28e29584d1a_d126', date(2024,  8, 21)),  # S10-05 视频案例分享讨论
    ('wri_a28e29584d1a_d145', date(2026,  1, 26)),  # S10-06 AI面试系统演示录屏
]

ALL_USED = set(KEEP_SESSIONS) | {
    ('wri_a28e29584d1a_d166', date(2022,  6, 30)),   # S10-01 视频翻译修改（非S10）
    ('wri_a28e29584d1a_d126', date(2024,  8, 29)),   # S10-02 首条表情缺乏上文
    ('wri_a28e29584d1a_d125', date(2023,  4, 24)),   # S10-03 跨日期+翻译定制询价
    ('wri_a28e29584d1a_d1771', date(2024,  5, 14)),  # S10-07 关键词匹配发票纠纷+口译
    ('wri_a28e29584d1a_d1065', date(2025, 10, 24)),  # S10-08 关键词匹配印刷供应商谈判
    ('wri_a28e29584d1a_d1771', date(2024,  5, 30)),  # S10-09 关键词匹配PPT分享+口译安排
    ('wri_a28e29584d1a_d1587', date(2024,  9,  9)),  # S10-10 关键词匹配PPT翻译更新
}

FILLER_RE = re.compile(
    r'^(\[.{1,15}\][\s\[.{1,15}\]]*'
    r'|好的?[~！。\!]*'
    r'|嗯嗯?[~！。\!]*'
    r'|收到[~！。\!]*'
    r'|稍等[~！。\!]*'
    r'|好滴[~！。\!]*'
    r'|知道了[~！。\!]*'
    r'|OK[~！。\!]*'
    r'|ok[~！。\!]*'
    r'|哦哦[~！。\!]*'
    r')$'
)

def is_filler(content):
    if not content: return True
    c = content.strip()
    return len(c) < 3 or bool(FILLER_RE.match(c))

def trim_msgs(msgs, max_n=MAX_DISPLAY):
    if len(msgs) <= max_n: return msgs
    keep = [not is_filler(m[3]) for m in msgs]
    keep[0] = True; keep[-1] = True
    result = [m for m, k in zip(msgs, keep) if k]
    return result[:max_n] if len(result) > max_n else result

def fmt_time(t): return str(t)[:19] if t else ''
def role_label(r):
    return '【客户】' if r=='customer' else ('【销售】' if r=='sales' else '【未知】')
def clean(s, n=800):
    if not s: return ''
    s = s.strip()
    return (s[:n]+'…') if len(s)>n else s

def load_session(conn, gk, sd):
    slices = conn.execute(text(f"""
        SELECT DISTINCT ON (slice_id)
               slice_id, slice_row_start, slice_row_end,
               slice_title, slice_quality_score, slice_process_result,
               import_batch_id, slice_question, slice_answer
        FROM wecom_raw_import
        WHERE group_key=:gk AND business_scenario_name=:sc
          AND slice_id IS NOT NULL AND slice_row_start IS NOT NULL
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'gk': gk, 'sc': SC_NAME}).fetchall()

    if slices:
        all_rs = min(s[1] for s in slices)
        all_re = max(s[2] for s in slices)
        msgs = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key=:gk AND row_index BETWEEN :rs AND :re
              AND DATE(msg_time)=:sd AND content IS NOT NULL AND content!=''
            ORDER BY row_index
        """), {'gk': gk, 'rs': all_rs, 're': all_re, 'sd': sd}).fetchall()
    else:
        msgs = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key=:gk AND DATE(msg_time)=:sd
              AND content IS NOT NULL AND content!=''
            ORDER BY row_index
        """), {'gk': gk, 'sd': sd}).fetchall()

    if not msgs: return None
    seen = {}
    for m in msgs:
        if m[1] not in seen: seen[m[1]] = m
    msgs = sorted(seen.values(), key=lambda m: m[1])

    if slices:
        q_scores = [float(s[4]) if s[4] else 0 for s in slices]
        bi = q_scores.index(max(q_scores))
        rr = [(s[1], s[2]) for s in slices]
        si = {
            'slice_ids': [s[0] for s in slices],
            'row_ranges': rr,
            'titles': [s[3] or '' for s in slices],
            'quality_scores': q_scores,
            'proc_results': [s[5] or '' for s in slices],
            'batch_id': slices[0][6] or '',
            'questions': [s[7] or '' for s in slices],
            'answers': [s[8] or '' for s in slices],
        }
    else:
        all_rows = [m[1] for m in msgs]
        si = {'slice_ids':[], 'row_ranges':[(min(all_rows), max(all_rows))],
              'titles':[], 'quality_scores':[], 'proc_results':[],
              'batch_id':'', 'questions':[], 'answers':[]}

    return {'group_key': gk, 'session_date': sd, 'msgs': msgs,
            'has_customer': any(m[2]=='customer' for m in msgs),
            'has_sales': any(m[2]=='sales' for m in msgs),
            'first_role': msgs[0][2], 'n_turns': len(msgs),
            'source': 'slice' if si['slice_ids'] else 'keyword', **si}

def find_replacements(conn, exclude_keys, need=7):
    slices = conn.execute(text("""
        WITH emp_groups AS (
            SELECT DISTINCT group_key FROM wecom_raw_import WHERE from_id=ANY(:ids)
        )
        SELECT DISTINCT ON (slice_id)
               slice_id, group_key, slice_row_start, slice_row_end,
               slice_title, slice_quality_score, slice_process_result,
               import_batch_id, slice_question, slice_answer
        FROM wecom_raw_import
        WHERE business_scenario_name=:sc
          AND slice_id IS NOT NULL AND slice_row_start IS NOT NULL
          AND content NOT LIKE '%未知消息类型%'
          AND group_key IN (SELECT group_key FROM emp_groups)
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'sc': SC_NAME, 'ids': list(SALES_IDS)}).fetchall()

    session_map = defaultdict(lambda: {
        'slice_ids':[], 'row_ranges':[], 'msgs':[],
        'titles':[], 'questions':[], 'answers':[],
        'quality_scores':[], 'proc_results':[], 'batch_id':''
    })

    for sl in slices:
        sid, gk, rs, re_ = sl[0], sl[1], sl[2], sl[3]
        core = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key=:gk AND row_index BETWEEN :rs AND :re
              AND content IS NOT NULL AND content!=''
            ORDER BY row_index
        """), {'gk': gk, 'rs': rs, 're': re_}).fetchall()
        if not core or core[0][4] is None: continue
        ft = core[0][4]
        sd = ft.date() if hasattr(ft,'date') else datetime.fromisoformat(str(ft)[:19]).date()
        key = (gk, sd)
        if key in exclude_keys: continue
        s = session_map[key]
        s['slice_ids'].append(sid); s['row_ranges'].append((rs, re_))
        s['msgs'].extend(core); s['titles'].append(sl[4] or '')
        s['questions'].append(sl[8] or ''); s['answers'].append(sl[9] or '')
        s['quality_scores'].append(float(sl[5]) if sl[5] else 0)
        s['proc_results'].append(sl[6] or ''); s['batch_id'] = sl[7] or ''

    candidates = []
    for (gk, sd), s in session_map.items():
        seen = {}
        for m in s['msgs']:
            if m[1] not in seen: seen[m[1]] = m
        msgs = sorted(seen.values(), key=lambda m: m[1])
        trimmed = trim_msgs(msgs)
        n = len(trimmed)
        has_s = any(m[2]=='sales' for m in trimmed)
        has_c = any(m[2]=='customer' for m in trimmed)
        first_role = msgs[0][2]
        if not has_s or not has_c or n < 4: continue
        avg_q = sum(s['quality_scores'])/len(s['quality_scores']) if s['quality_scores'] else 0
        ideal = min(n, 10)
        penalty = max(0, n-16)*3
        customer_first_bonus = 3 if first_role == 'customer' else 0
        score = ideal*2 - penalty + avg_q*0.3 + customer_first_bonus
        candidates.append({
            'group_key': gk, 'session_date': sd,
            'msgs': trimmed,
            'slice_ids': s['slice_ids'], 'row_ranges': s['row_ranges'],
            'titles': s['titles'], 'questions': s['questions'],
            'answers': s['answers'], 'quality_scores': s['quality_scores'],
            'proc_results': s['proc_results'], 'batch_id': s['batch_id'],
            'has_customer': has_c, 'has_sales': has_s, 'first_role': first_role,
            'n_turns': n, 'avg_q': avg_q, 'score': score, 'source': 'slice',
        })

    candidates.sort(key=lambda s: s['score'], reverse=True)
    gk_cnt = defaultdict(int)
    selected = []
    for c in candidates:
        if len(selected) >= need: break
        if gk_cnt[c['group_key']] >= 2: continue
        selected.append(c); gk_cnt[c['group_key']] += 1
    return selected

def render_session(idx, s):
    gk=s['group_key']; sd=s['session_date']; msgs=s['msgs']
    slice_ids=s['slice_ids']; row_ranges=s['row_ranges']
    titles=s['titles']; questions=s['questions']; answers=s['answers']
    q_scores=s['quality_scores']; procs=s['proc_results']; batch_id=s['batch_id']
    n_turns=len(msgs); source=s.get('source','slice')

    if q_scores:
        bi=q_scores.index(max(q_scores))
        title=titles[bi] if titles else '（无标题）'
        best_q=max(q_scores); best_proc=procs[bi] if procs else ''
    else:
        title='（无标题）'; best_q=None; best_proc=''; bi=0

    start_time=fmt_time(msgs[0][4]); end_time=fmt_time(msgs[-1][4])
    all_rs=min(r[0] for r in row_ranges); all_re=max(r[1] for r in row_ranges)

    lines=[]
    src_tag=' 🔍' if source=='keyword' else ''
    lines.append(f'\n## 案例 {SC_CODE}-{idx+1:02d}{src_tag}：{title}\n')
    lines.append('| 字段 | 值 |'); lines.append('|------|-----|')
    lines.append(f'| **会话日期** | {sd} |')
    lines.append(f'| **对话组ID (group_key)** | `{gk}` |')
    lines.append(f'| **批次ID** | `{batch_id}` |')
    if slice_ids:
        lines.append(f'| **切片ID(s)** | {", ".join(f"`{sid}`" for sid in slice_ids[:5])}{"…" if len(slice_ids)>5 else ""} |')
    lines.append(f'| **行范围** | row {all_rs} ~ {all_re} |')
    dtype='双向对话' if (s['has_customer'] and s['has_sales']) else '销售单方触达'
    lines.append(f'| **对话类型** | {dtype}，共 {n_turns} 条 |')
    lines.append(f'| **时间范围** | {start_time} 至 {end_time} |')
    lines.append(f'| **知识处理结论** | {best_proc} |')
    if best_q is not None: lines.append(f'| **质量分（最高）** | {best_q:.0f}/100 |')
    lines.append(f'| **查询原始数据** | `SELECT * FROM wecom_raw_import WHERE group_key = \'{gk}\' AND row_index BETWEEN {all_rs} AND {all_re} ORDER BY row_index` |')
    lines.append('')
    if slice_ids and questions:
        bq=(questions[bi] or '').strip() if bi<len(questions) else ''
        ba=(answers[bi] or '').strip() if bi<len(answers) else ''
        if bq or ba:
            lines.append('**AI提取摘要**：\n')
            if bq: lines.append(f'- **触发场景/客户问题**：{bq}')
            if ba: lines.append(f'- **销售回复要点**：{ba}')
            lines.append('')
    lines.append(f'**对话记录**（共 {n_turns} 条）：\n')
    for m in msgs:
        mid,ri,role,content,mt=m
        lines.append(f'**{role_label(role)}** `{fmt_time(mt)}` _(id={mid}, row={ri})_')
        for cl in clean(content).split('\n'):
            if cl.strip(): lines.append(cl)
        lines.append('')
    return lines

with e.connect() as conn:
    keep_sessions = []
    for gk, sd in KEEP_SESSIONS:
        s = load_session(conn, gk, sd)
        if s:
            s['msgs'] = trim_msgs(s['msgs'])
            s['n_turns'] = len(s['msgs'])
            keep_sessions.append(s)
            print(f'保留: {gk} {sd} → {s["n_turns"]}条')
        else:
            print(f'⚠ 未找到: {gk} {sd}')

    replacements = find_replacements(conn, exclude_keys=ALL_USED, need=7)
    print(f'\n找到替换案例: {len(replacements)}个')
    for r in replacements:
        print(f'  {r["group_key"]} {r["session_date"]} → {r["n_turns"]}条 title={r["titles"][0] if r["titles"] else "?"}')

    all_sessions = keep_sessions + replacements

    md_path = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
    with open(md_path, encoding='utf-8') as f:
        content = f.read()

    s10_start = content.find('\n---\n\n# S10 ')
    s11_start = content.find('\n---\n\n# S11 ')
    if s10_start==-1 or s11_start==-1:
        print('❌ 找不到S10/S11标记'); sys.exit(1)

    new_lines = [
        '\n---\n',
        f'# {SC_CODE} {SC_NAME}\n',
        '**场景描述**：向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。  ',
        '**商业重要性**：软性促单工具，在客户犹豫阶段效果显著。  ',
        f'**数据来源**：wecom_raw_import | 数据库标签=`{SC_NAME}` | 员工：{"/".join(SALES_IDS)} | 选取 {len(all_sessions)} 个案例  ',
        '**发起方**：客户发起为主\n',
    ]
    for idx, s in enumerate(all_sessions):
        new_lines.extend(render_session(idx, s))

    new_content = content[:s10_start] + '\n'.join(new_lines) + content[s11_start:]
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'\n完成！S10已更新。保留{len(keep_sessions)}+替换{len(replacements)}={len(all_sessions)}个')
    print(f'文件总字符: {len(new_content):,}')
