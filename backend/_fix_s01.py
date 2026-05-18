"""
修复 S01：
1. 保留4个合格案例（S01-02/03/05/08），截短到≤16条
2. 用6个更短、更贴合"方案确认与正式报价"的新案例替换
3. 不影响其他场景（S02-S12保持不变）
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

# ── 当前保留的4个好案例 ────────────────────────────────────────
KEEP_SESSIONS = [
    ('wri_a28e29584d1a_d125', date(2022, 10, 21)),  # S01-02 展会合同
    ('wri_a28e29584d1a_d124', date(2022,  5, 11)),  # S01-03 NDA翻译报价
    ('wri_a28e29584d1a_d104', date(2023,  6, 26)),  # S01-05 笔记本报价
    ('wri_a28e29584d1a_d124', date(2022, 10,  5)),  # S01-08 翻译报价付款
]

# 需要排除的所有已用过（包括坏的）
ALL_USED = set(KEEP_SESSIONS) | {
    ('wri_a28e29584d1a_d125', date(2023,  4,  6)),  # S01-01 代开发票
    ('wri_a28e29584d1a_d95',  date(2021, 12,  7)),  # S01-04 账单纠纷
    ('wri_a28e29584d1a_d91',  date(2024, 12,  2)),  # S01-06 油卡
    ('wri_a28e29584d1a_d121', date(2022,  8,  1)),  # S01-07 紧急交付
    ('wri_a28e29584d1a_d95',  date(2022,  3, 21)),  # S01-09 转介绍
    ('wri_a28e29584d1a_d117', date(2024, 10, 15)),  # S01-10 礼品闲聊
}

MAX_DISPLAY = 16   # 最多显示16条消息

# 过滤无意义消息的规则
FILLER_RE = re.compile(
    r'^(\[.{1,15}\][\s\[.{1,15}\]]*'  # 纯表情
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
    if len(c) < 3: return True
    return bool(FILLER_RE.match(c))

def trim_msgs(msgs, max_n=MAX_DISPLAY):
    """保留最多 max_n 条，优先去掉纯打招呼/确认消息。"""
    if len(msgs) <= max_n:
        return msgs
    # 先标记哪些是可以删的（filler）
    keep_flags = [not is_filler(m[3]) for m in msgs]
    # 强制保留第一条和最后一条
    keep_flags[0] = True
    keep_flags[-1] = True
    # 按保留优先级筛选
    result = [m for m, k in zip(msgs, keep_flags) if k]
    # 如果还是太多，从中间删减 filler
    if len(result) > max_n:
        result = result[:max_n]
    return result

def fmt_time(t):
    return str(t)[:19] if t else ''

def role_label(role):
    if role == 'customer': return '【客户】'
    if role == 'sales':    return '【销售】'
    return '【未知】'

def clean(s, n=800):
    if not s: return ''
    s = s.strip()
    return (s[:n] + '…') if len(s) > n else s

# ── 从DB读取切片信息构建已有会话 ─────────────────────────────
def load_session_from_slices(conn, gk, sess_date):
    slices = conn.execute(text("""
        SELECT DISTINCT ON (slice_id)
               slice_id, slice_row_start, slice_row_end,
               slice_title, slice_quality_score, slice_process_result,
               import_batch_id, slice_question, slice_answer
        FROM wecom_raw_import
        WHERE group_key = :gk
          AND business_scenario_name = '方案确认与正式报价'
          AND slice_id IS NOT NULL AND slice_row_start IS NOT NULL
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'gk': gk}).fetchall()

    if not slices:
        # 尝试直接取该天的消息
        msgs = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key = :gk
              AND DATE(msg_time) = :sd
              AND content IS NOT NULL AND content != ''
            ORDER BY row_index
        """), {'gk': gk, 'sd': sess_date}).fetchall()
        if not msgs: return None
        return _make_session(gk, sess_date, msgs, [], '')

    # 确定行范围
    all_rs = min(sl[1] for sl in slices)
    all_re = max(sl[2] for sl in slices)
    # 取核心消息（只看当天的）
    msgs = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE group_key = :gk
          AND row_index BETWEEN :rs AND :re
          AND content IS NOT NULL AND content != ''
          AND DATE(msg_time) = :sd
        ORDER BY row_index
    """), {'gk': gk, 'rs': all_rs, 're': all_re, 'sd': sess_date}).fetchall()

    if not msgs: return None

    q_scores = [float(sl[4]) if sl[4] else 0 for sl in slices]
    best = q_scores.index(max(q_scores)) if q_scores else 0
    si = {
        'slice_ids': [sl[0] for sl in slices],
        'row_ranges': [(sl[1], sl[2]) for sl in slices],
        'titles': [sl[3] or '' for sl in slices],
        'quality_scores': q_scores,
        'proc_results': [sl[5] or '' for sl in slices],
        'batch_id': slices[0][6] or '',
        'questions': [sl[7] or '' for sl in slices],
        'answers': [sl[8] or '' for sl in slices],
    }
    return _make_session(gk, sess_date, msgs, si, slices[0][6] or '')

def _make_session(gk, sd, msgs, si, batch_id):
    seen = {}
    for m in msgs:
        if m[1] not in seen: seen[m[1]] = m
    msgs = sorted(seen.values(), key=lambda m: m[1])
    if not msgs: return None

    rr = si.get('row_ranges', []) if si else []
    if rr:
        all_rs = min(r[0] for r in rr)
        all_re = max(r[1] for r in rr)
    else:
        all_rs = min(m[1] for m in msgs)
        all_re = max(m[1] for m in msgs)

    return {
        'group_key': gk, 'session_date': sd, 'msgs': msgs,
        'slice_ids': si.get('slice_ids', []) if si else [],
        'row_ranges': rr if rr else [(all_rs, all_re)],
        'titles': si.get('titles', []) if si else [],
        'questions': si.get('questions', []) if si else [],
        'answers': si.get('answers', []) if si else [],
        'quality_scores': si.get('quality_scores', []) if si else [],
        'proc_results': si.get('proc_results', []) if si else [],
        'batch_id': si.get('batch_id', '') if si else batch_id,
        'has_customer': any(m[2] == 'customer' for m in msgs),
        'has_sales': any(m[2] == 'sales' for m in msgs),
        'first_role': msgs[0][2],
        'n_turns': len(msgs),
        'source': 'slice' if (si and si.get('slice_ids')) else 'keyword',
    }

# ── 搜索替换候选 ──────────────────────────────────────────────
def find_replacements(conn, exclude_keys, need=6):
    """找 S01 合格候选，优先 5-16 条，客户发起。"""
    slices = conn.execute(text("""
        WITH emp_groups AS (
            SELECT DISTINCT group_key FROM wecom_raw_import WHERE from_id = ANY(:ids)
        )
        SELECT DISTINCT ON (slice_id)
               slice_id, group_key, slice_row_start, slice_row_end,
               slice_title, slice_quality_score, slice_process_result,
               import_batch_id, slice_question, slice_answer
        FROM wecom_raw_import
        WHERE business_scenario_name = '方案确认与正式报价'
          AND slice_id IS NOT NULL AND slice_row_start IS NOT NULL
          AND content NOT LIKE '%未知消息类型%'
          AND group_key IN (SELECT group_key FROM emp_groups)
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'ids': list(SALES_IDS)}).fetchall()

    session_map = defaultdict(lambda: {
        'slice_ids':[], 'row_ranges':[], 'msgs':[],
        'titles':[], 'questions':[], 'answers':[],
        'quality_scores':[], 'proc_results':[], 'batch_id':''
    })

    for sl in slices:
        sid, gk, rs, re = sl[0], sl[1], sl[2], sl[3]
        core = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key=:gk AND row_index BETWEEN :rs AND :re
              AND content IS NOT NULL AND content != ''
            ORDER BY row_index
        """), {'gk': gk, 'rs': rs, 're': re}).fetchall()
        if not core or core[0][4] is None: continue
        ft = core[0][4]
        sd = ft.date() if hasattr(ft,'date') else datetime.fromisoformat(str(ft)[:19]).date()
        key = (gk, sd)
        if key in exclude_keys: continue
        s = session_map[key]
        s['slice_ids'].append(sid)
        s['row_ranges'].append((rs, re))
        s['msgs'].extend(core)
        s['titles'].append(sl[4] or '')
        s['questions'].append(sl[8] or '')
        s['answers'].append(sl[9] or '')
        s['quality_scores'].append(float(sl[5]) if sl[5] else 0)
        s['proc_results'].append(sl[6] or '')
        s['batch_id'] = sl[7] or ''
        s['group_key'] = gk
        s['session_date'] = sd

    candidates = []
    for (gk, sd), s in session_map.items():
        seen = {}
        for m in s['msgs']:
            if m[1] not in seen: seen[m[1]] = m
        msgs = sorted(seen.values(), key=lambda m: m[1])
        if not msgs: continue

        # 截短计算
        trimmed = trim_msgs(msgs)
        n = len(trimmed)
        has_cust = any(m[2]=='customer' for m in trimmed)
        has_sale = any(m[2]=='sales'    for m in trimmed)
        first_role = msgs[0][2]

        # 必须双向，客户发起，至少3条
        if not (has_cust and has_sale): continue
        if first_role != 'customer': continue
        if n < 3: continue

        avg_q = sum(s['quality_scores'])/len(s['quality_scores']) if s['quality_scores'] else 0
        # 打分：偏爱 5-12 条，质量分加分
        ideal = min(n, 12)
        penalty = max(0, n - 16) * 3
        score = ideal * 2 - penalty + avg_q * 0.3

        candidates.append({
            'group_key': gk, 'session_date': sd,
            'msgs': trimmed, 'orig_msgs': msgs,
            'slice_ids': s['slice_ids'],
            'row_ranges': s['row_ranges'],
            'titles': s['titles'],
            'questions': s['questions'],
            'answers': s['answers'],
            'quality_scores': s['quality_scores'],
            'proc_results': s['proc_results'],
            'batch_id': s['batch_id'],
            'has_customer': has_cust, 'has_sales': has_sale,
            'first_role': first_role,
            'n_turns': n,
            'avg_q': avg_q, 'score': score,
            'source': 'slice',
        })

    candidates.sort(key=lambda s: s['score'], reverse=True)

    # 每个 group_key 最多2个
    gk_cnt = defaultdict(int)
    selected = []
    for c in candidates:
        if len(selected) >= need: break
        if gk_cnt[c['group_key']] >= 2: continue
        selected.append(c)
        gk_cnt[c['group_key']] += 1

    return selected

def render_session(sc_code, idx, s):
    gk        = s['group_key']
    sd        = s['session_date']
    msgs      = s['msgs']
    slice_ids = s['slice_ids']
    row_ranges = s['row_ranges']
    titles    = s['titles']
    questions = s['questions']
    answers   = s['answers']
    q_scores  = s['quality_scores']
    procs     = s['proc_results']
    batch_id  = s['batch_id']
    n_turns   = len(msgs)
    source    = s.get('source', 'slice')

    if q_scores:
        best_idx = q_scores.index(max(q_scores))
        title    = titles[best_idx] if titles else '（无标题）'
        best_q   = max(q_scores)
        best_proc = procs[best_idx] if procs else ''
    else:
        title = '（无标题）'; best_q = None; best_proc = ''
        best_idx = 0

    start_time = fmt_time(msgs[0][4])
    end_time   = fmt_time(msgs[-1][4])
    all_rs = min(r[0] for r in row_ranges)
    all_re = max(r[1] for r in row_ranges)

    lines = []
    src_tag = ' 🔍' if source == 'keyword' else ''
    lines.append(f'\n## 案例 {sc_code}-{idx+1:02d}{src_tag}：{title}\n')
    lines.append('| 字段 | 值 |')
    lines.append('|------|-----|')
    lines.append(f'| **会话日期** | {sd} |')
    lines.append(f'| **对话组ID (group_key)** | `{gk}` |')
    lines.append(f'| **批次ID** | `{batch_id}` |')
    if slice_ids:
        lines.append(f'| **切片ID(s)** | {", ".join(f"`{sid}`" for sid in slice_ids[:5])}{"…" if len(slice_ids)>5 else ""} |')
    lines.append(f'| **行范围** | row {all_rs} ~ {all_re} |')
    dtype = '双向对话' if (s['has_customer'] and s.get('has_sales', True)) else '销售单方触达'
    lines.append(f'| **对话类型** | {dtype}，共 {n_turns} 条 |')
    lines.append(f'| **时间范围** | {start_time} 至 {end_time} |')
    lines.append(f'| **知识处理结论** | {best_proc} |')
    if best_q is not None:
        lines.append(f'| **质量分（最高）** | {best_q:.0f}/100 |')
    lines.append(f'| **查询原始数据** | `SELECT * FROM wecom_raw_import WHERE group_key = \'{gk}\' AND row_index BETWEEN {all_rs} AND {all_re} ORDER BY row_index` |')
    lines.append('')

    if slice_ids and questions:
        bq = (questions[best_idx] or '').strip() if best_idx < len(questions) else ''
        ba = (answers[best_idx] or '').strip()   if best_idx < len(answers)   else ''
        if bq or ba:
            lines.append('**AI提取摘要**：\n')
            if bq: lines.append(f'- **触发场景/客户问题**：{bq}')
            if ba: lines.append(f'- **销售回复要点**：{ba}')
            lines.append('')

    lines.append(f'**对话记录**（共 {n_turns} 条）：\n')
    for m in msgs:
        msg_id, row_idx, role, content, msg_time = m
        rl = role_label(role)
        text_ = clean(content)
        lines.append(f'**{rl}** `{fmt_time(msg_time)}` _(id={msg_id}, row={row_idx})_')
        for cl in text_.split('\n'):
            if cl.strip():
                lines.append(cl)
        lines.append('')
    return lines

# ── 主流程 ────────────────────────────────────────────────────
with e.connect() as conn:
    # 1. 加载4个保留案例（从DB取切片信息+截短）
    keep_sessions = []
    for gk, sd in KEEP_SESSIONS:
        s = load_session_from_slices(conn, gk, sd)
        if s:
            s['msgs'] = trim_msgs(s['msgs'])
            s['n_turns'] = len(s['msgs'])
            keep_sessions.append(s)
            print(f'保留: {gk} {sd} → {s["n_turns"]}条')
        else:
            print(f'⚠ 未找到保留案例: {gk} {sd}')

    # 2. 找6个替换案例
    replacements = find_replacements(conn, exclude_keys=ALL_USED, need=6)
    print(f'\n找到替换案例: {len(replacements)}个')
    for r in replacements:
        print(f'  {r["group_key"]} {r["session_date"]} → {r["n_turns"]}条 score={r["score"]:.1f} title={r["titles"][0] if r["titles"] else "?"}')

    # 3. 合并：保留4 + 替换6，排序（先保留再替换）
    all_s01 = keep_sessions + replacements
    if len(all_s01) < 10:
        print(f'⚠ 只有 {len(all_s01)} 个案例')

    # 4. 读取现有 md，替换 S01 段落
    md_path = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
    with open(md_path, encoding='utf-8') as f:
        content = f.read()

    # 找到 S01 段落的起止位置
    s01_start = content.find('\n---\n\n# S01 ')
    s02_start = content.find('\n---\n\n# S02 ')

    if s01_start == -1 or s02_start == -1:
        print('❌ 找不到S01或S02段落标记')
        sys.exit(1)

    # 生成新的 S01 段落
    today = datetime.now().strftime('%Y-%m-%d')
    new_s01_lines = [
        '\n---\n',
        '# S01 方案确认与正式报价\n',
        '**场景描述**：客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。  ',
        '**商业重要性**：直接影响成交率，是销售漏斗最核心节点。  ',
        f'**数据来源**：wecom_raw_import | 数据库标签=`方案确认与正式报价` | 员工：{"/".join(SALES_IDS)} | 选取 {len(all_s01)} 个案例  ',
        '**发起方**：客户发起为主\n',
    ]
    for idx, s in enumerate(all_s01):
        new_s01_lines.extend(render_session('S01', idx, s))

    new_s01_text = '\n'.join(new_s01_lines)

    # 替换
    before_s01 = content[:s01_start]
    after_s02  = content[s02_start:]
    new_content = before_s01 + new_s01_text + after_s02

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'\n完成！S01段落已更新。')
    print(f'  保留案例: {len(keep_sessions)} 个')
    print(f'  替换案例: {len(replacements)} 个')
    print(f'  总计: {len(all_s01)} 个')
    print(f'  文件: {md_path}')
    print(f'  文件总字符: {len(new_content):,}')
