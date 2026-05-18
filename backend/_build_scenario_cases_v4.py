"""
v4 改进：
1. 员工过滤同时匹配 from_id（英文）和 sender（含中文名），修复遗漏
2. 切片搜索不足10条时，用关键词补充搜索未处理对话（肖美鹏/韩瑾/盛晔）
3. 综合质量评分：轮次 + 双向性 + 消息丰富度 + 关键词密度
4. 王慧莹数据未导入，在报告中注明
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

# ── 员工白名单（英文ID + 中文发件人字段） ─────────────────────
SALES_IDS = ['alicehe', 'davidXiaoMeiPeng', 'HanHan', 'joycesheng']
SALES_SENDERS = [
    '销售:何珺', '销售:肖美鹏', '销售:韩瑾', '销售:盛晔',
    '销售:alicehe', '销售:davidXiaoMeiPeng', '销售:HanHan', '销售:joycesheng',
]

SALES_INITIATED = {'S02', 'S09', 'S11', 'S12'}
CASES_PER = 10
MAX_MSGS_DISPLAY = 80

# ── 各场景关键词（用于无切片标注的补充搜索） ───────────────────
KEYWORDS = {
    'S01': ['报价', '报价单', '正式报价', '方案确认', '合同', '签单', '确认订单', '下单', '价格确认', '报价出来'],
    'S02': ['第一次合作', '初次联系', '新合作', '首次合作', '刚接触', '需要了解', '朋友推荐', '初次了解'],
    'S03': ['交期', '质量标准', '规格', '能否做', '做过吗', '最小起订', '样品', '技术要求', '产品参数', '能做到'],
    'S04': ['比价', '别家', '其他家', '价格贵', '便宜些', '价格能不能', '降价', '比你们便宜', '砍价', '对比价格'],
    'S05': ['急单', '紧急', '什么时候到', '催货', '进度怎么样', '几天能好', '要得急', '尽快', '最快多久', '赶货'],
    'S06': ['质量问题', '有问题', '不对', '搞错了', '退款', '投诉', '索赔', '退货', '赔偿', '质量不好'],
    'S07': ['预算', '资金紧', '暂缓', '先等一等', '暂时不', '不做了', '缓一缓', '预算不够', '缩减预算'],
    'S08': ['你们主要做', '业务范围', '介绍一下', '有哪些业务', '你们能做什么', '公司主营', '业务介绍'],
    'S09': ['新年快乐', '春节', '中秋', '国庆', '元旦', '开工大吉', '节日快乐', '祝您', '假期快乐', '新春'],
    'S10': ['案例', '之前做过', '有没有做过', '效果如何', '成功案例', '客户案例', '参考案例', '做过类似'],
    'S11': ['好久不联系', '好久没联系', '最近怎么样', '之前合作', '再次合作', '老客户', '有新业务', '新服务推荐'],
    'S12': ['推荐', '介绍给', '同事需要', '其他部门', '朋友需要', '转介绍', '帮忙介绍', '帮我推荐'],
}

# ── 场景定义 ─────────────────────────────────────────────────
SCENARIOS = [
    {'code': 'S01', 'name_db': '方案确认与正式报价', 'display': '方案确认与正式报价',
     'desc': '客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。',
     'importance': '直接影响成交率，是销售漏斗最核心节点。'},
    {'code': 'S02', 'name_db': '新客激活', 'display': '新客激活',
     'desc': '首次与潜在客户建立联系，引起关注并推动首次合作意向。',
     'importance': '业务增量的核心来源，决定客户获取效率。'},
    {'code': 'S03', 'name_db': '产品/服务细节对标', 'display': '产品/服务细节对标',
     'desc': '客户就服务能力、交付规格、质量标准等细节进行深度询问和比较。',
     'importance': '建立专业信任，将询价客户转化为意向客户的关键对话。'},
    {'code': 'S04', 'name_db': '价格竞争/比价', 'display': '价格竞争/比价',
     'desc': '客户明确提出与竞争对手比价，或要求降价，销售需在维护利润的同时守住客户。',
     'importance': '直接影响毛利率和客户留存，考验销售价值塑造能力。'},
    {'code': 'S05', 'name_db': '紧急响应/确定性交付', 'display': '紧急响应/确定性交付',
     'desc': '客户有紧急交付需求，或在订单执行中追问进度、要求确认节点。',
     'importance': '影响客户满意度和续单，是服务能力的直接体现。'},
    {'code': 'S06', 'name_db': '售后纠偏/客诉处理', 'display': '售后纠偏/客诉处理',
     'desc': '交付后客户反映质量问题、账单纠纷、服务不满等，需及时响应处理。',
     'importance': '直接影响客户留存和口碑，处理不当导致丢单甚至负面传播。'},
    {'code': 'S07', 'name_db': '预算收紧', 'display': '预算收紧',
     'desc': '客户以预算受限为由暂缓或压缩采购，销售需灵活应对守住合作。',
     'importance': '高频异议场景，决定销售能否守住存量客户。'},
    {'code': 'S08', 'name_db': '业务深度介绍', 'display': '业务深度介绍',
     'desc': '向客户系统介绍公司服务范围、核心能力、成功案例及差异化优势。',
     'importance': '决定客户对公司的第一印象和产品认知深度。'},
    {'code': 'S09', 'name_db': '节气/开工问候', 'display': '节气/开工问候',
     'desc': '节日、开工、重要时间节点发起的客情维护性问候，保持关系热度。',
     'importance': '低频但高价值，维系长期客户关系的基础动作。'},
    {'code': 'S10', 'name_db': '案例分享', 'display': '案例分享',
     'desc': '向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。',
     'importance': '软性促单工具，在客户犹豫阶段效果显著。'},
    {'code': 'S11', 'name_db': '老客唤醒', 'display': '老客户激活 / 推新业务',
     'desc': '针对沉默或低频老客户，通过问候、案例、新服务介绍重新激活关系，顺势推广新业务线。',
     'importance': '老客复购成本极低、信任基础已建立，是高ROI销售动作；推新业务可快速扩大客单价。',
     'extra_filter': "AND slice_title NOT LIKE '%销售单向触达候选%'"},
    {'code': 'S12', 'name_db': '转介绍请求与存量裂变', 'display': '转介绍请求',
     'desc': '请求现有客户将服务推荐给同事、其他部门或行业伙伴，实现低成本裂变获客。',
     'importance': '转介绍客户转化率是冷开发3-5倍，是存量客户最高效的裂变手段。'},
]

# ─────────────────────────────────────────────────────────────
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

def to_date(v):
    if v is None: return None
    if isinstance(v, date): return v
    return datetime.fromisoformat(str(v)[:19]).date()

def composite_score_kw(msgs, kws):
    """为关键词搜索的会话计算综合质量分（0-100）"""
    cust  = [m for m in msgs if m[2] == 'customer']
    sales = [m for m in msgs if m[2] == 'sales']
    n     = len(msgs)
    turn_pts  = min(n * 5, 40)
    bidir_pts = 20 if cust and sales else 0
    cust_len  = sum(len(m[3] or '') for m in cust)
    len_pts   = min(cust_len // 50, 20)
    full_text = ' '.join(m[3] or '' for m in msgs)
    kw_hits   = sum(1 for kw in kws if kw in full_text)
    kw_pts    = min(kw_hits * 4, 20)
    return turn_pts + bidir_pts + len_pts + kw_pts

# ─────────────────────────────────────────────────────────────
def find_sessions_slice(conn, sc_name, sc_code, extra_filter=''):
    """
    切片标注搜索（已处理数据，主要是alicehe）
    修复：员工CTE同时匹配 from_id 和 sender
    """
    slices = conn.execute(text(f"""
        WITH emp_groups AS (
            SELECT DISTINCT group_key FROM wecom_raw_import
            WHERE from_id = ANY(:ids) OR sender = ANY(:senders)
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
          {extra_filter}
        ORDER BY slice_id, slice_quality_score DESC NULLS LAST
    """), {'sc': sc_name, 'ids': SALES_IDS, 'senders': SALES_SENDERS}).fetchall()

    if not slices:
        return []

    session_map = defaultdict(lambda: {
        'slices': [], 'row_ranges': [], 'msgs': [],
        'titles': [], 'questions': [], 'answers': [],
        'quality_scores': [], 'proc_results': [], 'batch_id': '',
    })

    for sl in slices:
        sid, gk  = sl[0], sl[1]
        rs, re   = sl[2], sl[3]
        title    = sl[4] or ''
        q_score  = float(sl[5]) if sl[5] else 0
        proc     = sl[6] or ''
        batch    = sl[7] or ''
        sq       = sl[8] or ''
        sa       = sl[9] or ''

        core_rows = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key = :gk AND row_index BETWEEN :rs AND :re
              AND content IS NOT NULL AND content != ''
            ORDER BY row_index
        """), {'gk': gk, 'rs': rs, 're': re}).fetchall()

        if not core_rows:
            continue
        first_time = core_rows[0][4]
        if first_time is None:
            continue
        sess_date = to_date(first_time)
        key = (gk, sess_date)

        s = session_map[key]
        s['slices'].append(sid)
        s['row_ranges'].append((rs, re))
        s['msgs'].extend(core_rows)
        s['titles'].append(title)
        s['questions'].append(sq)
        s['answers'].append(sa)
        s['quality_scores'].append(q_score)
        s['proc_results'].append(proc)
        s['batch_id'] = batch
        s['group_key'] = gk
        s['session_date'] = sess_date

    sessions = []
    for (gk, sd), s in session_map.items():
        seen = {}
        for m in s['msgs']:
            if m[1] not in seen:
                seen[m[1]] = m
        msgs = sorted(seen.values(), key=lambda m: m[1])
        if not msgs:
            continue

        has_customer = any(m[2] == 'customer' for m in msgs)
        has_sales    = any(m[2] == 'sales'    for m in msgs)
        first_role   = msgs[0][2]
        n_turns      = len(msgs)
        avg_q        = sum(s['quality_scores']) / len(s['quality_scores']) if s['quality_scores'] else 0

        score = n_turns * 2 + avg_q * 0.3 + len(s['slices']) * 5

        sessions.append({
            'group_key': gk, 'session_date': sd, 'msgs': msgs,
            'slice_ids': s['slices'], 'row_ranges': s['row_ranges'],
            'titles': s['titles'], 'questions': s['questions'], 'answers': s['answers'],
            'quality_scores': s['quality_scores'], 'proc_results': s['proc_results'],
            'batch_id': s['batch_id'],
            'has_customer': has_customer, 'has_sales': has_sales,
            'first_role': first_role, 'n_turns': n_turns, 'avg_q': avg_q,
            'score': score, 'source': 'slice',
        })
    return sessions


def find_sessions_keyword(conn, sc_code, kws, exclude_gk_dates):
    """
    关键词补充搜索（未处理数据：肖美鹏/韩瑾/盛晔）
    返回与 find_sessions_slice 相同格式的会话列表
    """
    if not kws:
        return []

    kw_conds = ' OR '.join(f"w.content ILIKE :kw{i}" for i in range(len(kws)))
    params = {'ids': SALES_IDS, 'senders': SALES_SENDERS}
    for i, kw in enumerate(kws):
        params[f'kw{i}'] = f'%{kw}%'

    # 找关键词命中的 (group_key, 日期)，按命中次数排序
    hits = conn.execute(text(f"""
        WITH emp_gk AS (
            SELECT DISTINCT group_key FROM wecom_raw_import
            WHERE from_id = ANY(:ids) OR sender = ANY(:senders)
        )
        SELECT w.group_key, DATE(w.msg_time) AS session_date,
               COUNT(*) AS kw_cnt
        FROM emp_gk eg
        JOIN wecom_raw_import w ON w.group_key = eg.group_key
        WHERE ({kw_conds})
          AND w.content NOT LIKE '%未知消息类型%'
        GROUP BY w.group_key, DATE(w.msg_time)
        ORDER BY kw_cnt DESC
        LIMIT 300
    """), params).fetchall()

    sessions = []
    seen_keys = set(exclude_gk_dates)

    for row in hits:
        gk  = row[0]
        sd  = to_date(row[1])
        if sd is None:
            continue
        key = (gk, sd)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # 取该天该组的所有消息
        msgs = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key = :gk
              AND DATE(msg_time) = :sd
              AND content IS NOT NULL AND content != ''
              AND content NOT LIKE '%未知消息类型%'
            ORDER BY row_index, msg_time
        """), {'gk': gk, 'sd': sd}).fetchall()

        if len(msgs) < 2:
            continue

        has_customer = any(m[2] == 'customer' for m in msgs)
        has_sales    = any(m[2] == 'sales'    for m in msgs)
        first_role   = msgs[0][2]
        n_turns      = len(msgs)
        comp_score   = composite_score_kw(msgs, kws)

        rng = (msgs[0][1], msgs[-1][1])
        sessions.append({
            'group_key': gk, 'session_date': sd, 'msgs': list(msgs),
            'slice_ids': [], 'row_ranges': [rng],
            'titles': ['（关键词匹配）'], 'questions': [''], 'answers': [''],
            'quality_scores': [comp_score], 'proc_results': ['关键词搜索'],
            'batch_id': '',
            'has_customer': has_customer, 'has_sales': has_sales,
            'first_role': first_role, 'n_turns': n_turns, 'avg_q': comp_score,
            'score': comp_score, 'source': 'keyword',
        })

    return sessions


def select_sessions(sessions, sc_code, n=CASES_PER):
    sales_init = sc_code in SALES_INITIATED
    valid = []
    for s in sessions:
        if not s['has_sales']:
            continue
        if sales_init:
            pass  # 允许单方触达
        else:
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
        if len(selected) >= n:
            break
        if gk_count[s['group_key']] >= 2:
            continue
        selected.append(s)
        gk_count[s['group_key']] += 1
    return selected


def render_session(sc_code, idx, s):
    gk         = s['group_key']
    sd         = s['session_date']
    msgs       = s['msgs']
    titles     = s['titles']
    slice_ids  = s['slice_ids']
    row_ranges = s['row_ranges']
    questions  = s['questions']
    answers    = s['answers']
    q_scores   = s['quality_scores']
    procs      = s['proc_results']
    batch_id   = s['batch_id']
    n_turns    = s['n_turns']
    source     = s.get('source', 'slice')

    best_idx  = q_scores.index(max(q_scores)) if q_scores else 0
    title     = titles[best_idx] if titles else '（无标题）'
    best_q    = max(q_scores) if q_scores else None
    best_proc = procs[best_idx] if procs else ''
    start_time = fmt_time(msgs[0][4])
    end_time   = fmt_time(msgs[-1][4])

    all_rs = min(r[0] for r in row_ranges)
    all_re = max(r[1] for r in row_ranges)

    has_reply = s.get('has_customer') and s.get('has_sales')
    dtype = '双向对话' if has_reply else '销售单方触达'
    source_label = 'LLM切片标注' if source == 'slice' else '关键词匹配（未处理数据）'

    lines = []
    lines.append(f'\n## 案例 {sc_code}-{idx+1:02d}：{title}\n')
    lines.append('| 字段 | 值 |')
    lines.append('|------|-----|')
    lines.append(f'| **来源** | {source_label} |')
    lines.append(f'| **会话日期** | {sd} |')
    lines.append(f'| **对话组ID (group_key)** | `{gk}` |')
    if batch_id:
        lines.append(f'| **批次ID** | `{batch_id}` |')
    if slice_ids:
        lines.append(f'| **切片ID(s)** | {", ".join(f"`{sid}`" for sid in slice_ids)} |')
    lines.append(f'| **行范围** | row {all_rs} ~ {all_re} |')
    lines.append(f'| **对话类型** | {dtype}，共 {n_turns} 条 |')
    lines.append(f'| **时间范围** | {start_time} 至 {end_time} |')
    lines.append(f'| **知识处理结论** | {best_proc} |')
    if best_q is not None:
        score_label = '综合质量分' if source == 'keyword' else '质量分（最高）'
        lines.append(f'| **{score_label}** | {best_q:.0f}/100 |')
    lines.append(f'| **查询原始数据** | `SELECT * FROM wecom_raw_import WHERE group_key = \'{gk}\' AND row_index BETWEEN {all_rs} AND {all_re} ORDER BY row_index` |')
    lines.append('')

    if source == 'slice':
        best_q_str = (questions[best_idx] or '').strip() if questions else ''
        best_a_str = (answers[best_idx] or '').strip()   if answers  else ''
        if best_q_str or best_a_str:
            lines.append('**AI提取摘要**（最高质量切片）：\n')
            if best_q_str:
                lines.append(f'- **触发场景/客户问题**：{best_q_str}')
            if best_a_str:
                lines.append(f'- **销售回复要点**：{best_a_str}')
            lines.append('')

    display_msgs = msgs[:MAX_MSGS_DISPLAY]
    truncated = len(msgs) > MAX_MSGS_DISPLAY
    lines.append(f'**对话记录**（共 {n_turns} 条{"，展示前" + str(MAX_MSGS_DISPLAY) + "条" if truncated else ""}）：\n')

    for m in display_msgs:
        msg_id, row_idx, role, content, msg_time = m
        rl    = role_label(role)
        text_ = clean(content)
        lines.append(f'**{rl}** `{fmt_time(msg_time)}` _(id={msg_id}, row={row_idx})_')
        for cl in text_.split('\n'):
            if cl.strip():
                lines.append(cl)
        lines.append('')

    if truncated:
        lines.append(f'> ⚠️ 对话过长已截断，完整数据：`SELECT * FROM wecom_raw_import WHERE group_key = \'{gk}\' ORDER BY row_index`')
        lines.append('')

    return lines


# ── 主流程 ────────────────────────────────────────────────────
with e.connect() as conn:
    all_sections = []

    for sc in SCENARIOS:
        sc_code  = sc['code']
        name_db  = sc['name_db']
        display  = sc['display']
        extra    = sc.get('extra_filter', '')
        initiated = '销售主动发起' if sc_code in SALES_INITIATED else '客户发起为主'
        kws      = KEYWORDS.get(sc_code, [])

        print(f'\n处理 {sc_code} {display} [{initiated}]')

        # ① 切片搜索
        slice_sessions = find_sessions_slice(conn, name_db, sc_code, extra)
        slice_selected = select_sessions(slice_sessions, sc_code, CASES_PER)
        print(f'  切片: 候选{len(slice_sessions)}个 → 已选{len(slice_selected)}个')

        # ② 如不足10个，用关键词搜索补充
        kw_selected = []
        if len(slice_selected) < CASES_PER and kws:
            used_gk_dates = {(s['group_key'], s['session_date']) for s in slice_selected}
            kw_sessions = find_sessions_keyword(conn, sc_code, kws, used_gk_dates)
            need = CASES_PER - len(slice_selected)
            kw_selected = select_sessions(kw_sessions, sc_code, need)
            print(f'  关键词: 候选{len(kw_sessions)}个 → 补充{len(kw_selected)}个')

        selected = slice_selected + kw_selected
        total = len(selected)
        print(f'  最终: {total}个案例')

        if not selected:
            print(f'  ⚠ 无满足条件的案例，跳过')
            continue

        sec = []
        sec.append('\n---\n')
        sec.append(f'# {sc_code} {display}\n')
        sec.append(f'**场景描述**：{sc["desc"]}  ')
        sec.append(f'**商业重要性**：{sc["importance"]}  ')
        sec.append(f'**数据来源**：wecom_raw_import | 员工：alicehe / davidXiaoMeiPeng / HanHan / joycesheng | 共 {total} 个案例  ')
        sec.append(f'**发起方**：{initiated}\n')

        for idx, s in enumerate(selected):
            sec.extend(render_session(sc_code, idx, s))

        all_sections.extend(sec)

    today = datetime.now().strftime('%Y-%m-%d')
    header = f"""# 销售场景典型案例集

**版本**：v4.0
**生成日期**：{today}
**数据来源**：`wecom_raw_import` 表，企微历史会话原始数据
**员工范围**：alicehe（何珺）/ davidXiaoMeiPeng（肖美鹏）/ HanHan（韩瑾）/ joycesheng（盛晔）
**用途**：销售AI训练语料、评价基准、销售话术对比

> **⚠️ 数据说明**：WangHuiYing（王慧莹）的企微历史数据尚未导入知识库，
> 本文档未包含其对话案例。如需纳入，请先导入其历史CSV文件后重新生成。

## 使用说明

### 案例构成
- **LLM切片标注案例**：经AI识别标注的高质量切片，同一客户同一自然日合并为一个会话
- **关键词匹配案例**：对未处理员工数据（主要是肖美鹏/韩瑾/盛晔）按场景关键词搜索，综合质量评分
- 客户发起场景（S01/S03-S08/S10）：首条消息为客户发送
- 销售主动场景（S02/S09/S11/S12）：销售主动触达，允许单方触达

### 案例溯源
- **group_key**：对话组ID，对应一对一完整沟通线
- **切片ID(s)**：LLM识别的知识切片（关键词案例无此字段）
- **SQL**：直接执行可找回原始数据

### 质量分说明
| 分类 | 评分方式 |
|------|---------|
| LLM切片案例 | LLM原始质量分（0-100） |
| 关键词案例 | 综合评分：轮次(40)+双向(20)+消息丰富度(20)+关键词密度(20) |

### 训练价值
| 知识处理结论 | 训练价值 |
|------------|---------|
| 入库_切片 | ★★★★★ |
| 待人工确认 | ★★★☆☆ |
| 关键词搜索 | ★★★☆☆ 需人工复核 |

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
    print(f'\n完成：{out}')
    print(f'总字符：{len(full):,}  总行数：{len(full.splitlines()):,}')
