"""
v5：扩展版
- 员工白名单增加 WangHuiYing（第二个sheet数据已导入）
- 质量分 ≥75 优先，不足时降级到全部切片
- 未标注数据关键词兜底搜索（限员工对话组）
- 不使用 message_logs（仅含测试数据）
"""
import os, sys, io
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
SALES_INITIATED = {'S02', 'S09', 'S11', 'S12'}
CASES_PER = 10

SCENARIOS = [
    {
        'code': 'S01', 'name_db': '方案确认与正式报价', 'display': '方案确认与正式报价',
        'desc': '客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。',
        'importance': '直接影响成交率，是销售漏斗最核心节点。',
        'keywords': ['报价', '方案确认', '合同', '单价', '价格确认', '正式报价', '报价单'],
    },
    {
        'code': 'S02', 'name_db': '新客激活', 'display': '新客激活',
        'desc': '首次与潜在客户建立联系，引起关注并推动首次合作意向。',
        'importance': '业务增量的核心来源，决定客户获取效率。',
        'keywords': ['初次合作', '第一次', '新合作', '拓展', '了解下', '有没有需求', '有合作机会'],
    },
    {
        'code': 'S03', 'name_db': '产品/服务细节对标', 'display': '产品/服务细节对标',
        'desc': '客户就服务能力、交付规格、质量标准等细节进行深度询问和比较。',
        'importance': '建立专业信任，将询价客户转化为意向客户的关键对话。',
        'keywords': ['规格', '工艺', '样品', '参数', '质量要求', '技术标准', '能做到', '能否达到'],
    },
    {
        'code': 'S04', 'name_db': '价格竞争/比价', 'display': '价格竞争/比价',
        'desc': '客户明确提出与竞争对手比价，或要求降价，销售需在维护利润的同时守住客户。',
        'importance': '直接影响毛利率和客户留存，考验销售价值塑造能力。',
        'keywords': ['比价', '降价', '便宜', '其他家', '同行价格', '价格太高', '能不能便宜', '最低价'],
    },
    {
        'code': 'S05', 'name_db': '紧急响应/确定性交付', 'display': '紧急响应/确定性交付',
        'desc': '客户有紧急交付需求，或在订单执行中追问进度、要求确认节点。',
        'importance': '影响客户满意度和续单，是服务能力的直接体现。',
        'keywords': ['紧急', '急单', '什么时候', '交期', '几号能', '进度怎么', '能否加急', '催'],
    },
    {
        'code': 'S06', 'name_db': '售后纠偏/客诉处理', 'display': '售后纠偏/客诉处理',
        'desc': '交付后客户反映质量问题、账单纠纷、服务不满等，需及时响应处理。',
        'importance': '直接影响客户留存和口碑，处理不当导致丢单甚至负面传播。',
        'keywords': ['质量问题', '投诉', '退款', '赔偿', '纠纷', '不满意', '有问题', '出了问题', '客诉'],
    },
    {
        'code': 'S07', 'name_db': '预算收紧', 'display': '预算收紧',
        'desc': '客户以预算受限为由暂缓或压缩采购，销售需灵活应对守住合作。',
        'importance': '高频异议场景，决定销售能否守住存量客户。',
        'keywords': ['预算', '资金紧张', '暂缓', '控制成本', '今年预算', '没有预算', '资金问题'],
    },
    {
        'code': 'S08', 'name_db': '业务深度介绍', 'display': '业务深度介绍',
        'desc': '向客户系统介绍公司服务范围、核心能力、成功案例及差异化优势。',
        'importance': '决定客户对公司的第一印象和产品认知深度。',
        'keywords': ['介绍一下', '了解一下', '服务范围', '业务范围', '主要做什么', '能做哪些', '核心优势'],
    },
    {
        'code': 'S09', 'name_db': '节气/开工问候', 'display': '节气/开工问候',
        'desc': '节日、开工、重要时间节点发起的客情维护性问候，保持关系热度。',
        'importance': '低频但高价值，维系长期客户关系的基础动作。',
        'keywords': ['新年', '春节', '节日快乐', '开工大吉', '新春', '中秋', '国庆', '元旦', '节日问候', '假期愉快'],
    },
    {
        'code': 'S10', 'name_db': '案例分享', 'display': '案例分享',
        'desc': '向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。',
        'importance': '软性促单工具，在客户犹豫阶段效果显著。',
        'keywords': ['案例', '客户案例', '经验分享', '成功案例', '参考一下', '分享给你', '视频'],
    },
    {
        'code': 'S11', 'name_db': '老客唤醒', 'display': '老客户激活 / 推新业务',
        'desc': '针对沉默或低频老客户，通过问候、案例、新服务介绍重新激活关系，顺势推广新业务线。',
        'importance': '老客复购成本极低、信任基础已建立，是高ROI销售动作；推新业务可快速扩大客单价。',
        'extra_filter': "AND slice_title NOT LIKE '%销售单向触达候选%'",
        'keywords': ['好久不见', '久违', '最近还好', '还在做', '有没有新需求', '推新', '新业务', '新产品', '老客户', '重新合作'],
    },
    {
        'code': 'S12', 'name_db': '转介绍请求与存量裂变', 'display': '转介绍请求',
        'desc': '请求现有客户将服务推荐给同事、其他部门或行业伙伴，实现低成本裂变获客。',
        'importance': '转介绍客户转化率是冷开发3-5倍，是存量客户最高效的裂变手段。',
        'keywords': ['转介绍', '推荐给', '介绍朋友', '介绍同事', '介绍一下我们', '帮忙推荐'],
    },
]

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


def build_session_from_map(gk, sd, msg_list, slice_info=None):
    seen = {}
    for m in msg_list:
        if m[1] not in seen:
            seen[m[1]] = m
    msgs = sorted(seen.values(), key=lambda m: m[1])
    if not msgs:
        return None

    has_customer = any(m[2] == 'customer' for m in msgs)
    has_sales    = any(m[2] == 'sales'    for m in msgs)
    first_role   = msgs[0][2]
    n_turns      = len(msgs)

    if slice_info:
        qs = slice_info.get('quality_scores', [])
        avg_q    = sum(qs) / len(qs) if qs else 0
        n_slices = len(slice_info.get('slice_ids', []))
    else:
        avg_q = 0; n_slices = 0

    score = n_turns * 2 + avg_q * 0.3 + n_slices * 5

    si = slice_info or {}
    all_rows = [m[1] for m in msgs]
    rr = si.get('row_ranges', [])
    if rr:
        all_rs = min(r[0] for r in rr)
        all_re = max(r[1] for r in rr)
    else:
        all_rs = min(all_rows)
        all_re = max(all_rows)

    return {
        'group_key': gk, 'session_date': sd,
        'msgs': msgs,
        'slice_ids':    si.get('slice_ids', []),
        'row_ranges':   rr if rr else [(all_rs, all_re)],
        'titles':       si.get('titles', []),
        'questions':    si.get('questions', []),
        'answers':      si.get('answers', []),
        'quality_scores': si.get('quality_scores', []),
        'proc_results': si.get('proc_results', []),
        'batch_id':     si.get('batch_id', ''),
        'has_customer': has_customer, 'has_sales': has_sales,
        'first_role':   first_role, 'n_turns': n_turns,
        'avg_q': avg_q, 'score': score,
        'source': 'slice' if si.get('slice_ids') else 'keyword',
    }


def find_sessions_from_slices(conn, sc_name, extra_filter='', min_q=0):
    q_filter = f'AND slice_quality_score >= {min_q}' if min_q > 0 else ''
    slices = conn.execute(text(f"""
        WITH emp_groups AS (
            SELECT DISTINCT group_key FROM wecom_raw_import WHERE from_id = ANY(:ids)
        )
        SELECT DISTINCT ON (slice_id)
               slice_id, group_key, slice_row_start, slice_row_end,
               slice_title, slice_quality_score, slice_process_result,
               import_batch_id, slice_question, slice_answer
        FROM wecom_raw_import
        WHERE business_scenario_name = :sc
          AND slice_id IS NOT NULL
          AND slice_row_start IS NOT NULL
          AND content NOT LIKE '%未知消息类型%'
          AND group_key IN (SELECT group_key FROM emp_groups)
          {q_filter}
          {extra_filter}
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'sc': sc_name, 'ids': list(SALES_IDS)}).fetchall()

    if not slices:
        return []

    session_map = defaultdict(lambda: {
        'slice_ids': [], 'row_ranges': [], 'msgs': [],
        'titles': [], 'questions': [], 'answers': [],
        'quality_scores': [], 'proc_results': [], 'batch_id': ''
    })

    for sl in slices:
        sid, gk, rs, re = sl[0], sl[1], sl[2], sl[3]
        q_score = float(sl[5]) if sl[5] else 0
        core_rows = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key = :gk AND row_index BETWEEN :rs AND :re
              AND content IS NOT NULL AND content != ''
            ORDER BY row_index
        """), {'gk': gk, 'rs': rs, 're': re}).fetchall()
        if not core_rows or core_rows[0][4] is None:
            continue
        ft = core_rows[0][4]
        sd = ft.date() if hasattr(ft, 'date') else datetime.fromisoformat(str(ft)[:19]).date()
        key = (gk, sd)
        s = session_map[key]
        s['slice_ids'].append(sid)
        s['row_ranges'].append((rs, re))
        s['msgs'].extend(core_rows)
        s['titles'].append(sl[4] or '')
        s['questions'].append(sl[8] or '')
        s['answers'].append(sl[9] or '')
        s['quality_scores'].append(q_score)
        s['proc_results'].append(sl[6] or '')
        s['batch_id'] = sl[7] or ''
        s['group_key'] = gk
        s['session_date'] = sd

    sessions = []
    for (gk, sd), s in session_map.items():
        sess = build_session_from_map(gk, sd, s['msgs'], s)
        if sess:
            sessions.append(sess)
    return sessions


def find_sessions_by_keyword(conn, keywords, exclude_keys, limit_groups=300):
    if not keywords:
        return []
    pattern = '|'.join(keywords)
    kw_rows = conn.execute(text("""
        WITH emp_groups AS (
            SELECT DISTINCT group_key FROM wecom_raw_import WHERE from_id = ANY(:ids)
        )
        SELECT DISTINCT group_key
        FROM wecom_raw_import
        WHERE group_key IN (SELECT group_key FROM emp_groups)
          AND content ~* :pat
          AND content NOT LIKE '%未知消息类型%'
          AND slice_id IS NULL
        LIMIT :lim
    """), {'ids': list(SALES_IDS), 'pat': pattern, 'lim': limit_groups}).fetchall()

    if not kw_rows:
        return []

    gk_list = [r[0] for r in kw_rows]
    all_msgs = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time, group_key, import_batch_id
        FROM wecom_raw_import
        WHERE group_key = ANY(:gks)
          AND content IS NOT NULL AND content != ''
        ORDER BY group_key, row_index
    """), {'gks': gk_list}).fetchall()

    session_map = defaultdict(list)
    batch_map   = {}
    for row in all_msgs:
        msg_id, row_idx, role, content, msg_time, gk, batch = row
        if msg_time is None:
            continue
        sd = msg_time.date() if hasattr(msg_time, 'date') else datetime.fromisoformat(str(msg_time)[:19]).date()
        key = (gk, sd)
        if key in exclude_keys:
            continue
        session_map[key].append((msg_id, row_idx, role, content, msg_time))
        batch_map[gk] = batch

    sessions = []
    for (gk, sd), msgs in session_map.items():
        si = {'batch_id': batch_map.get(gk, '')}
        sess = build_session_from_map(gk, sd, msgs, si)
        if sess:
            sessions.append(sess)
    return sessions


def select_sessions(sessions, sc_code, already_keys=None):
    already_keys = already_keys or set()
    sales_initiated = sc_code in SALES_INITIATED
    valid = []
    for s in sessions:
        if (s['group_key'], s['session_date']) in already_keys:
            continue
        if not s['has_sales']:
            continue
        if not sales_initiated:
            if not s['has_customer']:
                continue
            if s['first_role'] != 'customer':
                continue
        if s['n_turns'] < 1:
            continue
        valid.append(s)
    valid.sort(key=lambda s: s['score'], reverse=True)
    gk_count = defaultdict(int)
    selected = []
    for s in valid:
        if len(selected) >= CASES_PER:
            break
        if gk_count[s['group_key']] >= 2:
            continue
        selected.append(s)
        gk_count[s['group_key']] += 1
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
    n_turns   = s['n_turns']
    source    = s.get('source', 'slice')

    if q_scores:
        best_idx  = q_scores.index(max(q_scores))
        title     = titles[best_idx] if titles else '（无标题）'
        best_q    = max(q_scores)
        best_proc = procs[best_idx] if procs else ''
    else:
        title = '（关键词匹配）'; best_q = None; best_proc = '未处理（关键词检索）'
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
        lines.append(f'| **切片ID(s)** | {", ".join(f"`{sid}`" for sid in slice_ids)} |')
    lines.append(f'| **行范围** | row {all_rs} ~ {all_re} |')
    dtype = '双向对话' if (s['has_customer'] and s['has_sales']) else '销售单方触达'
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
    all_sections = []
    scenario_stats = []

    for sc in SCENARIOS:
        sc_code  = sc['code']
        name_db  = sc['name_db']
        display  = sc['display']
        extra    = sc.get('extra_filter', '')
        keywords = sc.get('keywords', [])
        initiated = '销售主动发起' if sc_code in SALES_INITIATED else '客户发起为主'
        print(f'\n处理 {sc_code} {display} [{initiated}]')

        selected = []
        used_keys = set()

        # Phase 1a：质量分 ≥75 的切片
        sess_75 = find_sessions_from_slices(conn, name_db, extra, min_q=75)
        sel_75  = select_sessions(sess_75, sc_code)
        selected.extend(sel_75)
        used_keys = {(s['group_key'], s['session_date']) for s in selected}
        print(f'  [P1a ≥75] sessions={len(sess_75)} → 选{len(sel_75)}')

        # Phase 1b：不限质量补足
        if len(selected) < CASES_PER:
            sess_all = find_sessions_from_slices(conn, name_db, extra, min_q=0)
            sel_all  = select_sessions(sess_all, sc_code, already_keys=used_keys)[:CASES_PER - len(selected)]
            selected.extend(sel_all)
            used_keys = {(s['group_key'], s['session_date']) for s in selected}
            print(f'  [P1b 不限] sessions={len(sess_all)} → 补{len(sel_all)}')

        # Phase 2：关键词兜底
        if len(selected) < CASES_PER and keywords:
            sess_kw = find_sessions_by_keyword(conn, keywords, exclude_keys=used_keys)
            sel_kw  = select_sessions(sess_kw, sc_code, already_keys=used_keys)[:CASES_PER - len(selected)]
            selected.extend(sel_kw)
            used_keys = {(s['group_key'], s['session_date']) for s in selected}
            print(f'  [P2 关键词] sessions={len(sess_kw)} → 补{len(sel_kw)}')

        total = len(selected)
        print(f'  → 最终: {total}/{CASES_PER}')
        scenario_stats.append((sc_code, display, total))

        if not selected:
            continue

        sec = ['\n---\n', f'# {sc_code} {display}\n',
               f'**场景描述**：{sc["desc"]}  ',
               f'**商业重要性**：{sc["importance"]}  ',
               f'**数据来源**：wecom_raw_import | 数据库标签=`{name_db}` | 员工：{"/".join(SALES_IDS)} | 选取 {total} 个案例  ',
               f'**发起方**：{initiated}\n']

        for idx, s in enumerate(selected):
            sec.extend(render_session(sc_code, idx, s))

        all_sections.extend(sec)

    today = datetime.now().strftime('%Y-%m-%d')
    header = f"""# 销售场景典型案例集

**版本**：v5.0
**生成日期**：{today}
**数据来源**：`wecom_raw_import`（企微历史会话）
**员工范围**：{' / '.join(SALES_IDS)}
**用途**：销售AI训练语料、评价基准、销售话术对比

## 案例来源说明

| 来源 | 标记 | 知识处理结论 | 训练价值 |
|------|------|------------|---------|
| LLM切片标注（质量≥75） | 无标记 | 入库_切片 | ★★★★★ |
| LLM切片标注（全部） | 无标记 | 待人工确认 | ★★★☆☆ |
| 关键词兜底检索 | 🔍 | 未处理 | ★★☆☆☆（建议人工确认） |

## 使用说明

- **会话级案例**：同一客户同一自然日内所有相关消息合并（保证多轮完整性）
- 客户发起场景（S01/S03-S08/S10）：首条消息为客户发送
- 销售主动场景（S02/S09/S11/S12）：销售主动触达
- 每个案例含 `group_key` + SQL，可精确回溯原始数据

## 场景目录

| 编号 | 场景 | 重要度 | 发起方 |
|------|------|-------|-------|
| S01 | 方案确认与正式报价 | ★★★★★ | 客户 |
| S02 | 新客激活 | ★★★★★ | 销售 |
| S03 | 产品/服务细节对标 | ★★★★☆ | 客户 |
| S04 | 价格竞争/比价 | ★★★★☆ | 客户 |
| S05 | 紧急响应/确定性交付 | ★★★★☆ | 客户 |
| S06 | 售后纠偏/客诉处理 | ★★★★☆ | 客户 |
| S07 | 预算收紧 | ★★★☆☆ | 客户 |
| S08 | 业务深度介绍 | ★★★☆☆ | 客户 |
| S09 | 节气/开工问候 | ★★★☆☆ | 销售 |
| S10 | 案例分享 | ★★★☆☆ | 客户 |
| S11 | 老客户激活 / 推新业务 | ★★★★★ | 销售 |
| S12 | 转介绍请求 | ★★★★★ | 销售 |

"""
    full = header + '\n'.join(all_sections)
    out  = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(full)

    print(f'\n\n=== 完成 ===')
    print(f'输出：{out}')
    print(f'总字符：{len(full):,}  总行数：{len(full.splitlines()):,}')
    print('\n各场景案例数：')
    total_cases = 0
    for code, name, cnt in scenario_stats:
        bar = '★' * cnt + '☆' * (CASES_PER - cnt)
        print(f'  {code} {name}: {cnt}/{CASES_PER} {bar}')
        total_cases += cnt
    print(f'\n  合计：{total_cases} 个案例（目标 {len(SCENARIOS) * CASES_PER}）')
