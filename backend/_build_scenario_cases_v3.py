"""
v3（最终版）
- 只展示该场景对应的消息，无上下文行
- 按会话日期聚合：同一客户同一天内所有场景切片合并 → 保证多轮
- 客户发起筛选：除销售主动场景外，首条消息必须是客户
- 员工过滤：只取 alicehe / davidXiaoMeiPeng / HanHan / joycesheng
- 输出：sales_scenario_cases_v2.md
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

# ── 员工白名单 ────────────────────────────────────────────────
SALES_IDS = ('alicehe', 'davidXiaoMeiPeng', 'HanHan', 'joycesheng')

# ── 销售主动发起的场景（不要求客户首条消息） ──────────────────
SALES_INITIATED = {'S02', 'S09', 'S11', 'S12'}

CASES_PER = 10

# ── 12个场景 ──────────────────────────────────────────────────
SCENARIOS = [
    {
        'code': 'S01', 'name_db': '方案确认与正式报价', 'display': '方案确认与正式报价',
        'desc': '客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。',
        'importance': '直接影响成交率，是销售漏斗最核心节点。',
    },
    {
        'code': 'S02', 'name_db': '新客激活', 'display': '新客激活',
        'desc': '首次与潜在客户建立联系，引起关注并推动首次合作意向。',
        'importance': '业务增量的核心来源，决定客户获取效率。',
    },
    {
        'code': 'S03', 'name_db': '产品/服务细节对标', 'display': '产品/服务细节对标',
        'desc': '客户就服务能力、交付规格、质量标准等细节进行深度询问和比较。',
        'importance': '建立专业信任，将询价客户转化为意向客户的关键对话。',
    },
    {
        'code': 'S04', 'name_db': '价格竞争/比价', 'display': '价格竞争/比价',
        'desc': '客户明确提出与竞争对手比价，或要求降价，销售需在维护利润的同时守住客户。',
        'importance': '直接影响毛利率和客户留存，考验销售价值塑造能力。',
    },
    {
        'code': 'S05', 'name_db': '紧急响应/确定性交付', 'display': '紧急响应/确定性交付',
        'desc': '客户有紧急交付需求，或在订单执行中追问进度、要求确认节点。',
        'importance': '影响客户满意度和续单，是服务能力的直接体现。',
    },
    {
        'code': 'S06', 'name_db': '售后纠偏/客诉处理', 'display': '售后纠偏/客诉处理',
        'desc': '交付后客户反映质量问题、账单纠纷、服务不满等，需及时响应处理。',
        'importance': '直接影响客户留存和口碑，处理不当导致丢单甚至负面传播。',
    },
    {
        'code': 'S07', 'name_db': '预算收紧', 'display': '预算收紧',
        'desc': '客户以预算受限为由暂缓或压缩采购，销售需灵活应对守住合作。',
        'importance': '高频异议场景，决定销售能否守住存量客户。',
    },
    {
        'code': 'S08', 'name_db': '业务深度介绍', 'display': '业务深度介绍',
        'desc': '向客户系统介绍公司服务范围、核心能力、成功案例及差异化优势。',
        'importance': '决定客户对公司的第一印象和产品认知深度。',
    },
    {
        'code': 'S09', 'name_db': '节气/开工问候', 'display': '节气/开工问候',
        'desc': '节日、开工、重要时间节点发起的客情维护性问候，保持关系热度。',
        'importance': '低频但高价值，维系长期客户关系的基础动作。',
    },
    {
        'code': 'S10', 'name_db': '案例分享', 'display': '案例分享',
        'desc': '向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。',
        'importance': '软性促单工具，在客户犹豫阶段效果显著。',
    },
    {
        'code': 'S11', 'name_db': '老客唤醒', 'display': '老客户激活 / 推新业务',
        'desc': '针对沉默或低频老客户，通过问候、案例、新服务介绍重新激活关系，顺势推广新业务线。',
        'importance': '老客复购成本极低、信任基础已建立，是高ROI销售动作；推新业务可快速扩大客单价。',
        'extra_filter': "AND slice_title NOT LIKE '%销售单向触达候选%'",
    },
    {
        'code': 'S12', 'name_db': '转介绍请求与存量裂变', 'display': '转介绍请求',
        'desc': '请求现有客户将服务推荐给同事、其他部门或行业伙伴，实现低成本裂变获客。',
        'importance': '转介绍客户转化率是冷开发3-5倍，是存量客户最高效的裂变手段。',
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

# ── 核心：按会话日期查案例 ──────────────────────────────────
def find_sessions(conn, sc_name, sc_code, extra_filter=''):
    """
    返回候选会话列表，每条 = {group_key, session_date, row_ids, msgs, score}
    策略：同一 group_key + 同一自然日内，所有属于该场景的切片行合并
    """
    # 1. 找该场景下（员工白名单）所有切片的 group_key + 行范围
    #    在 group_key 级过滤：只要对话组内有员工消息即视为该员工的对话
    slices = conn.execute(text(f"""
        WITH emp_groups AS (
            SELECT DISTINCT group_key
            FROM wecom_raw_import
            WHERE from_id = ANY(:ids)
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
    """), {'sc': sc_name, 'ids': list(SALES_IDS)}).fetchall()

    if not slices:
        return []

    # 2. 对每个切片，取其核心行的消息，获取时间
    #    按 (group_key, 日期) 聚合 → 同一客户同一天的所有切片合并
    session_map = defaultdict(lambda: {
        'slices': [], 'row_ranges': [], 'msgs': [],
        'titles': [], 'questions': [], 'answers': [],
        'quality_scores': [], 'proc_results': [], 'batch_id': ''
    })

    for sl in slices:
        sid, gk = sl[0], sl[1]
        rs, re  = sl[2], sl[3]
        title   = sl[4] or ''
        q_score = float(sl[5]) if sl[5] else 0
        proc    = sl[6] or ''
        batch   = sl[7] or ''
        sq      = sl[8] or ''
        sa      = sl[9] or ''

        # 取核心行消息（只要 msg_time 来定日期）
        core_rows = conn.execute(text("""
            SELECT id, row_index, role, content, msg_time
            FROM wecom_raw_import
            WHERE group_key = :gk AND row_index BETWEEN :rs AND :re
              AND content IS NOT NULL AND content != ''
            ORDER BY row_index
        """), {'gk': gk, 'rs': rs, 're': re}).fetchall()

        if not core_rows:
            continue

        # 取第一条核心消息的日期作为会话日期
        first_time = core_rows[0][4]
        if first_time is None:
            continue
        sess_date = first_time.date() if hasattr(first_time, 'date') else datetime.fromisoformat(str(first_time)[:19]).date()
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

    # 3. 对每个会话去重消息、排序、打分
    sessions = []
    for (gk, sd), s in session_map.items():
        # 去重（同一 row_index 可能被多个切片包含）
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
        n_slices     = len(s['slices'])

        # 打分：轮次多、质量高、切片多的优先
        score = n_turns * 2 + avg_q * 0.3 + n_slices * 5

        sessions.append({
            'group_key':    gk,
            'session_date': sd,
            'msgs':         msgs,
            'slice_ids':    s['slices'],
            'row_ranges':   s['row_ranges'],
            'titles':       s['titles'],
            'questions':    s['questions'],
            'answers':      s['answers'],
            'quality_scores': s['quality_scores'],
            'proc_results': s['proc_results'],
            'batch_id':     s['batch_id'],
            'has_customer': has_customer,
            'has_sales':    has_sales,
            'first_role':   first_role,
            'n_turns':      n_turns,
            'avg_q':        avg_q,
            'score':        score,
        })

    return sessions

def select_sessions(sessions, sc_code):
    """按规则筛选10个案例。"""
    sales_initiated = sc_code in SALES_INITIATED

    # 过滤
    valid = []
    for s in sessions:
        if not s['has_sales']:
            continue  # 至少有销售消息
        if sales_initiated:
            # 销售主动场景：优先有客户回复，但允许纯销售触达
            pass
        else:
            # 客户发起场景：必须有客户消息且首条是客户
            if not s['has_customer']:
                continue
            if s['first_role'] != 'customer':
                continue
        if s['n_turns'] < 1:
            continue
        valid.append(s)

    # 排序：分数高优先
    valid.sort(key=lambda s: s['score'], reverse=True)

    # 每个 group_key 最多用2次（不同日期算不同案例）
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
    gk       = s['group_key']
    sd       = s['session_date']
    msgs     = s['msgs']
    titles   = s['titles']
    slice_ids = s['slice_ids']
    row_ranges = s['row_ranges']
    questions  = s['questions']
    answers    = s['answers']
    q_scores   = s['quality_scores']
    procs      = s['proc_results']
    batch_id   = s['batch_id']
    n_turns    = s['n_turns']

    # 会话标题：取质量最高的切片标题
    best_idx = q_scores.index(max(q_scores)) if q_scores else 0
    title    = titles[best_idx] if titles else '（无标题）'
    best_q   = max(q_scores) if q_scores else None
    best_proc = procs[best_idx] if procs else ''
    start_time = fmt_time(msgs[0][4])
    end_time   = fmt_time(msgs[-1][4])

    # row range 合并显示
    all_rs = min(r[0] for r in row_ranges)
    all_re = max(r[1] for r in row_ranges)
    # 构建核心行集合（所有切片的行）
    core_rows_set = set()
    for rs, re in row_ranges:
        core_rows_set.update(range(rs, re + 1))

    lines = []
    lines.append(f'\n## 案例 {sc_code}-{idx+1:02d}：{title}\n')
    lines.append('| 字段 | 值 |')
    lines.append('|------|-----|')
    lines.append(f'| **会话日期** | {sd} |')
    lines.append(f'| **对话组ID (group_key)** | `{gk}` |')
    lines.append(f'| **批次ID** | `{batch_id}` |')
    lines.append(f'| **切片ID(s)** | {", ".join(f"`{sid}`" for sid in slice_ids)} |')
    lines.append(f'| **行范围** | row {all_rs} ~ {all_re} |')
    has_reply = s.get('has_customer', False) and s.get('has_sales', False)
    dtype = '双向对话' if has_reply else '销售单方触达'
    lines.append(f'| **对话类型** | {dtype}，共 {n_turns} 条 |')
    lines.append(f'| **时间范围** | {start_time} 至 {end_time} |')
    lines.append(f'| **知识处理结论** | {best_proc} |')
    if best_q is not None:
        lines.append(f'| **质量分（最高）** | {best_q:.0f}/100 |')
    lines.append(f'| **查询原始数据** | `SELECT * FROM wecom_raw_import WHERE group_key = \'{gk}\' AND row_index BETWEEN {all_rs} AND {all_re} ORDER BY row_index` |')
    lines.append('')

    # AI摘要（只取最佳切片的）
    best_q_str = (questions[best_idx] or '').strip() if questions else ''
    best_a_str = (answers[best_idx] or '').strip()   if answers  else ''
    if best_q_str or best_a_str:
        lines.append('**AI提取摘要**（最高质量切片）：\n')
        if best_q_str:
            lines.append(f'- **触发场景/客户问题**：{best_q_str}')
        if best_a_str:
            lines.append(f'- **销售回复要点**：{best_a_str}')
        lines.append('')

    lines.append(f'**对话记录**（共 {n_turns} 条）：\n')

    for m in msgs:
        msg_id, row_idx, role, content, msg_time = m
        rl   = role_label(role)
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

    for sc in SCENARIOS:
        sc_code  = sc['code']
        name_db  = sc['name_db']
        display  = sc['display']
        extra    = sc.get('extra_filter', '')
        initiated = '销售主动发起' if sc_code in SALES_INITIATED else '客户发起为主'
        print(f'处理 {sc_code} {display} [{initiated}]')

        sessions = find_sessions(conn, name_db, sc_code, extra)
        selected = select_sessions(sessions, sc_code)
        print(f'  候选会话: {len(sessions)}，已选: {len(selected)}')

        if not selected:
            print(f'  ⚠ 无满足条件的案例')
            continue

        sec = []
        sec.append('\n---\n')
        sec.append(f'# {sc_code} {display}\n')
        sec.append(f'**场景描述**：{sc["desc"]}  ')
        sec.append(f'**商业重要性**：{sc["importance"]}  ')
        db_tag = f'数据库场景标签=`{name_db}` | ' if name_db != display else ''
        sec.append(f'**数据来源**：wecom_raw_import | {db_tag}员工：alicehe/davidXiaoMeiPeng/HanHan/joycesheng | 候选会话 {len(sessions)} 个，本文选取 {len(selected)} 个  ')
        sec.append(f'**发起方**：{initiated}\n')

        for idx, s in enumerate(selected):
            sec.extend(render_session(sc_code, idx, s))

        all_sections.extend(sec)

    today = datetime.now().strftime('%Y-%m-%d')
    header = f"""# 销售场景典型案例集

**版本**：v3.0
**生成日期**：{today}
**数据来源**：`wecom_raw_import` 表，企微历史会话原始数据
**员工范围**：alicehe / davidXiaoMeiPeng / HanHan / joycesheng
**用途**：销售AI训练语料、评价基准、销售话术对比

## 使用说明

### 案例构成
- **会话级案例**：同一客户同一自然日内，所有属于该场景的切片消息合并，保证多轮完整性
- 每个案例只展示与该场景直接相关的对话消息，无无关上下文
- 客户发起场景（S01/S03-S08/S10）：首条消息为客户发送
- 销售主动场景（S02/S09/S11/S12）：销售主动触达

### 案例溯源
- **group_key**：对话组ID，对应一对一完整沟通线
- **切片ID(s)**：LLM识别的知识切片，可直接查库
- **SQL**：直接执行可找回原始数据

### 训练价值
| 知识处理结论 | 训练价值 |
|------------|---------|
| 入库_切片 | ★★★★★ |
| 待人工确认 | ★★★☆☆ |

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
