"""
经典案例库导入脚本：
1. 解析 sales_scenario_cases_v2.md
2. 每场景按"质量分（最高）"取前5个案例（不足则全部取）
3. 从数据库为每个案例抓核心对话之前的15条聊天消息作为背景
4. UPSERT 入 case_library_case 表（覆盖式：同 scenario_code+rank 视作同一槽位）
"""
import os, sys, io, re, json, uuid
from datetime import datetime, date

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

from database import engine, SessionLocal, CaseLibraryCase, CaseLibraryDialogueTurn, init_db
from sqlalchemy import text

MD_PATH = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
RECENT_CUTOFF = datetime(2024, 5, 20)
SALES_IDS = ('alicehe', 'davidXiaoMeiPeng', 'HanHan', 'joycesheng', 'WangHuiYing')
TARGET_DIALOGUE_TURNS = 5
MAX_PROJECT_GAP_DAYS = 45

SCENARIO_HEADER_RE = re.compile(r'^# (S\d{2})\s+(.+?)\s*$', re.M)
CASE_HEADER_RE = re.compile(r'^## 案例 (S\d{2})-(\d{2})(?:\s*🔍)?[:：]\s*(.*?)\s*$', re.M)

FIELD_PATTERNS = {
    'session_date':   re.compile(r'\| \*\*会话日期\*\* \| (\d{4}-\d{2}-\d{2}) \|'),
    'group_key':      re.compile(r'\| \*\*对话组ID.*?\| `([^`]+)` \|'),
    'batch_id':       re.compile(r'\| \*\*批次ID\*\* \| `([^`]+)` \|'),
    'row_range':      re.compile(r'\| \*\*行范围\*\* \| row (\d+) ~ (\d+) \|'),
    'quality_score':  re.compile(r'\| \*\*质量分（最高）\*\* \| ([\d.]+)/100 \|'),
}
SLICE_RE = re.compile(r'\| \*\*切片ID\(s\)\*\* \| (.+?) \|')
MSG_RE = re.compile(
    r'\*\*【(客户|销售|未知)】\*\* `(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})` _\(id=(\d+), row=(\d+)\)_\n([\s\S]+?)(?=\n\*\*【|\n\n## |\n\n---|\Z)'
)

TRIVIAL_REPLIES = {
    '好', '好的', '好哒', '好滴', '好嘞', '嗯', '嗯嗯', '恩', 'ok', 'OK', '收到', '知道了',
    '明白', '明白了', '可以', '行', '是的', '对', '谢谢', '感谢', '辛苦', '哈哈', '哈哈哈',
}

OUTDATED_SCENE_RE = re.compile(
    r'疫情|新冠|核酸|封控|封城|封小区|隔离|居家办公|居家隔离|远程办公|线上办公|复工|复产|浦东封|开关|关了|决赛圈'
)

SCENARIO_POSITIVE_KEYWORDS = {
    'S01': ('方案', '报价', '价格', '费用', '单价', '总价', '含税', '开票', '折扣', '预算', '申请', '报价单', '合同', '老板', '大老板'),
}

SCENARIO_NEGATIVE_KEYWORDS = {
    'S01': ('翻译好了吗', '正在QC', 'QC好了', '术语翻译', '很多都不对', '请帮我安排一下翻译'),
}


def is_meaningful_message(msg):
    content = (msg.get('content') or '').strip()
    compact = re.sub(r'\s+', '', content)
    if not compact:
        return False
    if compact in TRIVIAL_REPLIES:
        return False
    if len(compact) <= 2 and not re.search(r'[?？0-9报价价格合同订单发票款预算方案需求]', compact):
        return False
    return True


def is_outdated_scene(case):
    parts = [case.get('case_title') or '']
    parts.extend((m.get('content') or '') for m in (case.get('core_dialog') or []))
    return bool(OUTDATED_SCENE_RE.search('\n'.join(parts)))


def derive_title_from_messages(messages, fallback_name):
    first_customer = next((m for m in messages if m.get('role') == 'customer' and is_meaningful_message(m)), None)
    first_sales = next((m for m in messages if m.get('role') == 'sales' and is_meaningful_message(m)), None)
    src = first_customer or first_sales
    if not src:
        return f'{fallback_name}补充案例'
    text = re.sub(r'\s+', ' ', (src.get('content') or '').strip())
    return text[:28] + ('…' if len(text) > 28 else '')


def scenario_fit_score(scenario_code, title, messages):
    text_blob = (title or '') + '\n' + '\n'.join((m.get('content') or '') for m in messages)
    score = 0
    for kw in SCENARIO_POSITIVE_KEYWORDS.get(scenario_code, ()):
        if kw in text_blob:
            score += 2
    for kw in SCENARIO_NEGATIVE_KEYWORDS.get(scenario_code, ()):
        if kw in text_blob:
            score -= 3
    return score


def normalize_db_message(row):
    return {
        'role': row[2] or 'unknown',
        'msg_time': str(row[4])[:19] if row[4] else None,
        'msg_id': row[0],
        'row_index': row[1],
        'content': (row[3] or '').strip(),
    }


def fetch_messages_between(conn, group_key, row_start, row_end):
    rows = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE group_key=:gk AND row_index BETWEEN :rs AND :re
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
        ORDER BY row_index
    """), {'gk': group_key, 'rs': row_start, 're': row_end}).fetchall()
    return [normalize_db_message(r) for r in rows]


def fetch_slice_messages(conn, slice_id):
    rows = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE slice_id=:sid
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
        ORDER BY row_index
    """), {'sid': slice_id}).fetchall()
    return [normalize_db_message(r) for r in rows]


def fetch_session_messages(conn, group_key):
    rows = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE group_key=:gk
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
        ORDER BY row_index
    """), {'gk': group_key}).fetchall()
    return [normalize_db_message(r) for r in rows]


def fetch_group_messages(conn, group_key):
    rows = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE group_key=:gk
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
        ORDER BY row_index
    """), {'gk': group_key}).fetchall()
    return [normalize_db_message(r) for r in rows]


def _parse_msg_dt(msg):
    raw = msg.get('msg_time')
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:19])
    except Exception:
        return None


def select_project_window(messages, anchor_rows, max_gap_days=MAX_PROJECT_GAP_DAYS, max_messages=120):
    if not messages or not anchor_rows:
        return []
    anchor_min = min(anchor_rows)
    anchor_max = max(anchor_rows)
    indices = [
        i for i, m in enumerate(messages)
        if m.get('row_index') is not None and anchor_min <= m['row_index'] <= anchor_max
    ]
    if not indices:
        indices = [min(range(len(messages)), key=lambda i: abs((messages[i].get('row_index') or 0) - anchor_min))]
    left = min(indices)
    right = max(indices)

    def too_far(a, b):
        da, db = _parse_msg_dt(messages[a]), _parse_msg_dt(messages[b])
        if not da or not db:
            return False
        return abs((db - da).days) > max_gap_days

    while left > 0 and (right - left + 1) < max_messages and not too_far(left - 1, left):
        left -= 1
    while right < len(messages) - 1 and (right - left + 1) < max_messages and not too_far(right, right + 1):
        right += 1
    return messages[left:right + 1]


def split_messages_into_turns(messages, scenario_code, target_turns=TARGET_DIALOGUE_TURNS):
    allow_sales_only = scenario_code in SALES_INITIATED_SCENARIOS
    customer_first = scenario_code in CUSTOMER_FIRST_SCENARIOS
    meaningful = [m for m in messages if is_meaningful_message(m)]
    if customer_first:
        first_customer = next((i for i, m in enumerate(meaningful) if m.get('role') == 'customer'), None)
        if first_customer is None:
            return []
        meaningful = meaningful[first_customer:]

    raw_turns = []
    current = []
    has_customer = False
    has_sales = False
    for msg in meaningful:
        role = msg.get('role')
        if role not in ('customer', 'sales'):
            continue
        if customer_first:
            if role == 'customer' and current and has_sales:
                raw_turns.append(current)
                current = []
                has_customer = False
                has_sales = False
        elif allow_sales_only:
            if role == 'sales' and current and (has_customer or has_sales):
                # 销售主动触达场景里，一条完整触达也可以独立成轮；客户回复后下一条销售再开新轮。
                if has_customer:
                    raw_turns.append(current)
                    current = []
                    has_customer = False
                    has_sales = False
        else:
            if role == 'customer' and current and has_sales:
                raw_turns.append(current)
                current = []
                has_customer = False
                has_sales = False
        current.append(msg)
        has_customer = has_customer or role == 'customer'
        has_sales = has_sales or role == 'sales'
    if current:
        raw_turns.append(current)

    normalized = []
    for msgs in raw_turns:
        roles = {m.get('role') for m in msgs}
        if 'sales' not in roles:
            continue
        if customer_first and 'customer' not in roles:
            continue
        if not allow_sales_only and 'customer' not in roles:
            continue
        rows = [m.get('row_index') for m in msgs if m.get('row_index') is not None]
        if not rows:
            continue
        normalized.append({
            'slice_id': next((m.get('slice_id') for m in msgs if m.get('slice_id')), None),
            'row_start': min(rows),
            'row_end': max(rows),
            'messages': msgs,
            'customer_text': '\n'.join(m['content'] for m in msgs if m.get('role') == 'customer'),
            'sales_text': '\n'.join(m['content'] for m in msgs if m.get('role') == 'sales'),
        })

    for idx, t in enumerate(normalized, start=1):
        t['turn_no'] = idx
    return normalized[:target_turns]


def scenario_test_prompt(scenario_code, turn_no, messages, sales_text):
    if scenario_code != 'S11':
        return None
    compact_sales = re.sub(r'\s+', ' ', sales_text or '').strip()
    if turn_no == 1:
        return '请帮我写一条微信消息，激活一位很久没有联系的老客户，语气自然亲切，不要太营销，并顺带了解近期是否有新的合作需求。'
    if re.search(r'辞职|换工作|不在了|新公司|哪家|合作机会', compact_sales):
        return '老客户回复说已经换工作了，请帮我继续发一条微信，既保持关系，也自然询问新公司后续是否有翻译、视频、印刷或礼品等合作机会。'
    if re.search(r'业务|视频|推广|介绍|案例|合作', compact_sales):
        return '老客户有了简短回复，请帮我继续发一条微信，围绕我们可提供的业务做自然跟进，避免硬推销，争取了解对方是否有近期需求。'
    return '请帮我继续跟进这位老客户，保持轻松自然的微信语气，承接对方上一句回复，并把话题推进到是否有新的合作机会。'


def make_synthetic_customer_message(turn, content):
    rows = [m.get('row_index') for m in (turn.get('messages') or []) if m.get('row_index') is not None]
    times = [m.get('msg_time') for m in (turn.get('messages') or []) if m.get('msg_time')]
    return {
        'role': 'customer',
        'msg_time': times[0] if times else None,
        'msg_id': None,
        'row_index': (min(rows) - 1) if rows else turn.get('row_start'),
        'content': content,
        'synthetic': True,
        'synthetic_reason': 'scenario_test_prompt',
    }


def normalize_turns_for_test_flow(scenario_code, turns):
    normalized = []
    for idx, turn in enumerate(turns, start=1):
        t = dict(turn)
        messages = list(t.get('messages') or [])
        sales_text = '\n'.join(m.get('content') or '' for m in messages if m.get('role') == 'sales' and is_meaningful_message(m))
        prompt = scenario_test_prompt(scenario_code, idx, messages, sales_text)
        if prompt:
            messages = [make_synthetic_customer_message(t, prompt)] + [m for m in messages if m.get('role') != 'customer' or not m.get('synthetic')]
            t['messages'] = messages
            t['customer_text'] = prompt
            t['sales_text'] = sales_text
            t['row_start'] = min([m.get('row_index') for m in messages if m.get('row_index') is not None] or [t.get('row_start')])
        t['turn_no'] = idx
        normalized.append(t)
    return normalized


def build_turns_around_anchor(conn, group_key, anchor_rows, scenario_code, target_turns=TARGET_DIALOGUE_TURNS):
    all_messages = fetch_group_messages(conn, group_key)
    window = select_project_window(all_messages, anchor_rows)
    all_turns = split_messages_into_turns(window, scenario_code, target_turns=999)
    if not all_turns:
        return []
    anchor_set = set(anchor_rows)
    hit_indices = [
        i for i, t in enumerate(all_turns)
        if any((m.get('row_index') in anchor_set) for m in (t.get('messages') or []))
    ]
    if hit_indices:
        anchor_idx = min(hit_indices)
    else:
        anchor_min = min(anchor_rows)
        anchor_idx = min(range(len(all_turns)), key=lambda i: abs((all_turns[i].get('row_start') or 0) - anchor_min))
    # Business training cases need the setup that led to the anchor, not only messages after it.
    # Prefer ending at/just after the anchor so prior project-relevant turns can become core turns.
    end = min(len(all_turns), anchor_idx + 1)
    start = max(0, end - target_turns)
    if end - start < target_turns:
        end = min(len(all_turns), start + target_turns)
    selected = [dict(t) for t in all_turns[start:end]]
    for idx, t in enumerate(selected, start=1):
        t['turn_no'] = idx
    return normalize_turns_for_test_flow(scenario_code, selected)


def fetch_slice_turns_for_core(conn, group_key, core_dialog, target_turns=5, allow_sales_only=False):
    core_rows = [m.get('row_index') for m in core_dialog or [] if m.get('row_index') is not None]
    if not core_rows:
        return []
    rows = conn.execute(text("""
        SELECT row_index, slice_id, slice_row_start, slice_row_end
        FROM wecom_raw_import
        WHERE group_key=:gk AND row_index = ANY(:rows)
          AND slice_id IS NOT NULL
          AND slice_row_start IS NOT NULL
          AND slice_row_end IS NOT NULL
        ORDER BY row_index
    """), {'gk': group_key, 'rows': core_rows}).fetchall()

    ranges = []
    seen = set()
    for row_index, sid, rs, re in rows:
        key = (sid, rs, re)
        if key in seen:
            continue
        seen.add(key)
        ranges.append((row_index, sid, int(rs), int(re)))
    ranges.sort(key=lambda x: x[0])

    turns = []
    for _row_index, sid, rs, re in ranges:
        messages = fetch_messages_between(conn, group_key, rs, re)
        meaningful = [m for m in messages if is_meaningful_message(m)]
        roles = {m.get('role') for m in meaningful}
        if 'customer' not in roles or 'sales' not in roles:
            if not (allow_sales_only and roles == {'sales'}):
                continue
            messages = meaningful
        turns.append({
            'slice_id': sid,
            'row_start': rs,
            'row_end': re,
            'messages': messages,
        })
        if len(turns) >= target_turns:
            break

    normalized = []
    for idx, t in enumerate(turns, start=1):
        customer_text = '\n'.join(m['content'] for m in t['messages'] if m.get('role') == 'customer' and is_meaningful_message(m))
        sales_text = '\n'.join(m['content'] for m in t['messages'] if m.get('role') == 'sales' and is_meaningful_message(m))
        normalized.append({
            **t,
            'turn_no': idx,
            'customer_text': customer_text,
            'sales_text': sales_text,
        })
    return normalized


SALES_INITIATED_SCENARIOS = set()


def build_turns_from_slices(conn, slice_ids, target_turns=5, allow_sales_only=False):
    turns = []
    for sid in slice_ids:
        messages = fetch_slice_messages(conn, sid)
        meaningful = [m for m in messages if is_meaningful_message(m)]
        roles = {m.get('role') for m in meaningful}
        if 'customer' not in roles or 'sales' not in roles:
            if not (allow_sales_only and roles == {'sales'}):
                continue
            # 紫色销售主动触达切片：标准定义允许一行一个候选单元。
            messages = meaningful
            roles = {'sales'}
        if 'sales' not in roles:
            continue
        rows = [m.get('row_index') for m in messages if m.get('row_index') is not None]
        if not rows:
            continue
        turns.append({
            'slice_id': sid,
            'row_start': min(rows),
            'row_end': max(rows),
            'messages': messages,
        })
        if len(turns) >= target_turns:
            break
    normalized = []
    for idx, t in enumerate(turns, start=1):
        messages = t['messages']
        normalized.append({
            **t,
            'turn_no': idx,
            'customer_text': '\n'.join(m['content'] for m in messages if m.get('role') == 'customer' and is_meaningful_message(m)),
            'sales_text': '\n'.join(m['content'] for m in messages if m.get('role') == 'sales' and is_meaningful_message(m)),
        })
    return normalized


def enforce_customer_first_turns(turns):
    if not turns:
        return turns
    first = dict(turns[0])
    messages = list(first.get('messages') or [])
    first_customer_idx = next((i for i, m in enumerate(messages) if m.get('role') == 'customer'), None)
    if first_customer_idx is None:
        return turns
    if first_customer_idx > 0:
        messages = messages[first_customer_idx:]
        rows = [m.get('row_index') for m in messages if m.get('row_index') is not None]
        first['messages'] = messages
        if rows:
            first['row_start'] = min(rows)
            first['row_end'] = max(rows)
        first['customer_text'] = '\n'.join(m['content'] for m in messages if m.get('role') == 'customer' and is_meaningful_message(m))
        first['sales_text'] = '\n'.join(m['content'] for m in messages if m.get('role') == 'sales' and is_meaningful_message(m))
        turns = [first] + turns[1:]
    return turns


def parse_md():
    """返回 [{scenario_code, scenario_name, cases:[case_dict]}]"""
    with open(MD_PATH, encoding='utf-8') as f:
        content = f.read()

    scenarios = []
    # 找所有场景标题位置
    hdrs = list(SCENARIO_HEADER_RE.finditer(content))
    for i, h in enumerate(hdrs):
        code, name = h.group(1), h.group(2).strip()
        body_start = h.end()
        body_end = hdrs[i+1].start() if i+1 < len(hdrs) else len(content)
        body = content[body_start:body_end]
        cases = parse_cases(body, code)
        scenarios.append({'scenario_code': code, 'scenario_name': name, 'cases': cases})
    return scenarios


def parse_cases(body, scenario_code):
    """从场景正文解析所有案例。"""
    cases = []
    hdrs = list(CASE_HEADER_RE.finditer(body))
    for i, h in enumerate(hdrs):
        sc, idx, title = h.group(1), h.group(2), h.group(3).strip()
        if sc != scenario_code: continue
        cstart = h.end()
        cend = hdrs[i+1].start() if i+1 < len(hdrs) else len(body)
        case_body = body[cstart:cend]

        case = {
            'scenario_code': sc,
            'case_idx': int(idx),
            'case_title': title,
            'md_section_anchor': f'{sc}-{idx}',
        }
        for name, pat in FIELD_PATTERNS.items():
            m = pat.search(case_body)
            if m:
                if name == 'row_range':
                    case['row_start'] = int(m.group(1))
                    case['row_end']   = int(m.group(2))
                elif name == 'session_date':
                    case['session_date'] = m.group(1)
                elif name == 'quality_score':
                    case['quality_score'] = float(m.group(1))
                else:
                    case[name] = m.group(1)
        sm = SLICE_RE.search(case_body)
        if sm:
            sids = re.findall(r'`([^`]+)`', sm.group(1))
            case['slice_ids'] = sids

        # 解析对话消息
        msgs = []
        for mm in MSG_RE.finditer(case_body):
            role_zh, mt, mid, row, content_block = mm.group(1), mm.group(2), mm.group(3), mm.group(4), mm.group(5)
            content = content_block.strip()
            role = {'客户': 'customer', '销售': 'sales'}.get(role_zh, 'unknown')
            msgs.append({
                'role': role,
                'msg_time': mt,
                'msg_id': int(mid),
                'row_index': int(row),
                'content': content,
            })
        case['core_dialog'] = msgs
        # 标题缺失/占位时，从核心对话首条客户消息回退；无客户消息时取首条任意消息
        title_raw = (case.get('case_title') or '').strip()
        if not title_raw or '无标题' in title_raw or title_raw in ('-', '（无）'):
            first_customer = next((m for m in msgs if m.get('role') == 'customer' and m.get('content')), None)
            fallback = first_customer or (msgs[0] if msgs else None)
            if fallback:
                content = (fallback.get('content') or '').replace('\n', ' ').strip()
                case['case_title'] = content[:30] + ('…' if len(content) > 30 else '') if content else '（暂无对话）'
        cases.append(case)
    return cases


def fetch_background_messages(conn, group_key, row_start, n=15):
    """获取 row_start 之前的 n 条非空消息（同 group_key）。"""
    rows = conn.execute(text("""
        SELECT id, row_index, role, content, msg_time
        FROM wecom_raw_import
        WHERE group_key=:gk AND row_index < :rs
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
        ORDER BY row_index DESC
        LIMIT :lim
    """), {'gk': group_key, 'rs': row_start, 'lim': max(n * 4, 30)}).fetchall()
    filtered = []
    for r in rows:
        content = (r[3] or '').strip()
        if not content or OUTDATED_SCENE_RE.search(content):
            continue
        filtered.append(r)
        if len(filtered) >= n:
            break
    filtered = list(reversed(filtered))  # 还原成时间顺序
    return [{
        'role': r[2] or 'unknown',
        'msg_time': str(r[4])[:19] if r[4] else None,
        'msg_id': r[0],
        'row_index': r[1],
        'content': (r[3] or '').strip(),
    } for r in filtered]


def fetch_background_from_messages(all_msgs, row_start, n=15):
    prior = [
        m for m in all_msgs
        if m.get('row_index') is not None
        and row_start is not None
        and m['row_index'] < row_start
        and is_meaningful_message(m)
    ]
    return prior[-n:]


def upsert_dialogue_turns(conn, case_id, scenario_code, scenario_rank, group_key, turns):
    conn.execute(text("DELETE FROM case_library_dialogue_turn WHERE case_id = :cid"), {'cid': case_id})
    for t in turns:
        conn.execute(text("""
            INSERT INTO case_library_dialogue_turn
                (case_id, scenario_code, scenario_rank, turn_no, group_key,
                 row_start, row_end, customer_text, sales_text, messages, context_messages,
                 score_status, created_at, updated_at)
            VALUES
                (:case_id, :scenario_code, :scenario_rank, :turn_no, :group_key,
                 :row_start, :row_end, :customer_text, :sales_text, CAST(:messages AS JSON), CAST(:context_messages AS JSON),
                 'missing', NOW(), NOW())
        """), {
            'case_id': case_id,
            'scenario_code': scenario_code,
            'scenario_rank': scenario_rank,
            'turn_no': t['turn_no'],
            'group_key': group_key,
            'row_start': t['row_start'],
            'row_end': t['row_end'],
            'customer_text': t.get('customer_text') or '',
            'sales_text': t.get('sales_text') or '',
            'messages': json.dumps(t.get('messages') or [], ensure_ascii=False),
            'context_messages': json.dumps(t.get('context_messages') or [], ensure_ascii=False),
        })

def ensure_rejected_table(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS case_library_case_rejected (
            rejected_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            original_case_id UUID,
            scenario_code VARCHAR(10) NOT NULL,
            scenario_rank INTEGER,
            case_title VARCHAR(255),
            group_key VARCHAR(120),
            session_date TIMESTAMP,
            row_start INTEGER,
            row_end INTEGER,
            md_section_anchor VARCHAR(80),
            reject_reason TEXT,
            payload JSON,
            rejected_at TIMESTAMP DEFAULT now()
        )
    """))


def soft_reject_existing_slots(conn, selected_by_slot):
    for scenario_code, rank, replacement in selected_by_slot:
        old = conn.execute(text("""
            SELECT case_id, scenario_code, scenario_rank, case_title, group_key,
                   session_date, row_start, row_end, md_section_anchor, core_dialog,
                   context_messages, slice_ids, quality_score_md
            FROM case_library_case
            WHERE scenario_code=:sc AND scenario_rank=:rank
        """), {'sc': scenario_code, 'rank': rank}).fetchone()
        if not old:
            continue
        old_anchor = old[8]
        new_anchor = replacement.get('md_section_anchor')
        if old_anchor == new_anchor:
            continue
        payload = {
            'core_dialog': old[9],
            'context_messages': old[10],
            'slice_ids': old[11],
            'quality_score_md': float(old[12]) if old[12] is not None else None,
        }
        conn.execute(text("""
            INSERT INTO case_library_case_rejected
                (original_case_id, scenario_code, scenario_rank, case_title, group_key,
                 session_date, row_start, row_end, md_section_anchor, reject_reason, payload, rejected_at)
            VALUES
                (:case_id, :scenario_code, :scenario_rank, :case_title, :group_key,
                 :session_date, :row_start, :row_end, :md_section_anchor, :reject_reason,
                 CAST(:payload AS JSON), NOW())
        """), {
            'case_id': old[0],
            'scenario_code': old[1],
            'scenario_rank': old[2],
            'case_title': old[3],
            'group_key': old[4],
            'session_date': old[5],
            'row_start': old[6],
            'row_end': old[7],
            'md_section_anchor': old[8],
            'reject_reason': f"replaced_by_{new_anchor}",
            'payload': json.dumps(payload, ensure_ascii=False),
        })


SCENARIO_DB_NAME = {
    'S01': '方案确认与正式报价',
    'S02': '新客激活',
    'S03': '产品/服务细节对标',
    'S04': '价格竞争/比价',
    'S05': '紧急响应/确定性交付',
    'S06': '售后纠偏/客诉处理',
    'S07': '预算收紧',
    'S08': '业务深度介绍',
    'S09': '节气/开工问候',
    'S10': '案例分享',
    'S11': '老客唤醒',
    'S12': '转介绍请求与存量裂变',
}

CUSTOMER_FIRST_SCENARIOS = {
    'S01', 'S02', 'S03', 'S04', 'S05', 'S06',
    'S07', 'S08', 'S09', 'S10', 'S11', 'S12',
}


def validate_case_candidate(conn, case):
    gk = case.get('group_key')
    core = case.get('core_dialog') or []
    if not gk or not core:
        return False, '缺 group_key 或核心对话'
    first_meaningful = next((m for m in core if is_meaningful_message(m)), core[0])
    sc = case.get('scenario_code')
    if sc in CUSTOMER_FIRST_SCENARIOS and first_meaningful.get('role') != 'customer':
        return False, '客户发起场景首条不是客户'

    core_rows = [m.get('row_index') for m in core if m.get('row_index') is not None]
    if not core_rows:
        return False, '核心对话无 row_index'
    expected = SCENARIO_DB_NAME.get(sc)
    if expected:
        hit = conn.execute(text("""
            SELECT COUNT(*)
            FROM wecom_raw_import
            WHERE group_key=:gk AND row_index = ANY(:rows)
              AND business_scenario_name=:expected
        """), {'gk': gk, 'rows': core_rows, 'expected': expected}).scalar()
        if int(hit or 0) <= 0:
            return False, f'核心行未命中场景 {expected}'
    return True, 'ok'

def load_raw_candidates(conn, scenario_code, scenario_name, limit=120):
    expected = SCENARIO_DB_NAME.get(scenario_code, scenario_name)
    rows = conn.execute(text("""
        SELECT id, row_index, group_key, import_batch_id, msg_time,
               slice_id, slice_title, slice_quality_score, content
        FROM wecom_raw_import
        WHERE business_scenario_name=:scene
          AND (from_id = ANY(:ids) OR to_id = ANY(:ids))
          AND msg_time >= :cutoff
          AND content IS NOT NULL AND content!=''
          AND content NOT LIKE '%未知消息类型%'
          AND COALESCE(slice_process_result, process_result, '') NOT IN ('不入库_强个案','不入库_无答','不入库_无效')
        ORDER BY msg_time DESC, row_index DESC
        LIMIT :lim
    """), {
        'scene': expected,
        'ids': list(SALES_IDS),
        'cutoff': RECENT_CUTOFF,
        'lim': limit * 4,
    }).fetchall()
    candidates = []
    seen_spans = set()
    for idx, r in enumerate(rows, start=1):
        _id, row_index, gk, batch_id, msg_time, sid, title, quality_score, content = r
        if not gk or row_index is None or not msg_time:
            continue
        turns = build_turns_around_anchor(conn, gk, [int(row_index)], scenario_code, TARGET_DIALOGUE_TURNS)
        if scenario_code in CUSTOMER_FIRST_SCENARIOS:
            turns = enforce_customer_first_turns(turns)
        if not turns:
            continue
        final_core = [m for t in turns for m in (t.get('messages') or [])]
        messages = final_core
        if not messages:
            continue
        span_key = (gk, turns[0]['row_start'], turns[-1]['row_end'])
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)
        title = title or derive_title_from_messages(messages, scenario_name)
        if is_outdated_scene({'case_title': title, 'core_dialog': messages}):
            continue
        first_meaningful = next((m for m in final_core if is_meaningful_message(m)), final_core[0] if final_core else {})
        if scenario_code in CUSTOMER_FIRST_SCENARIOS and first_meaningful.get('role') != 'customer':
            continue
        all_rows = [m.get('row_index') for m in final_core if m.get('row_index') is not None]
        sd = msg_time.date() if hasattr(msg_time, 'date') else datetime.fromisoformat(str(msg_time)[:19]).date()
        slice_ids = sorted(set(m.get('slice_id') for m in final_core if m.get('slice_id')))
        if sid and sid not in slice_ids:
            slice_ids.append(sid)
        candidates.append({
            'scenario_code': scenario_code,
            'case_idx': 1000 + idx,
            'case_title': title or f'{scenario_name}补充案例',
            'md_section_anchor': f'{scenario_code}-RAW-{idx:03d}',
            'session_date': sd.isoformat(),
            'group_key': gk,
            'batch_id': batch_id,
            'slice_ids': slice_ids,
            'row_start': min(all_rows) if all_rows else int(row_index),
            'row_end': max(all_rows) if all_rows else int(row_index),
            'quality_score': float(quality_score) if quality_score is not None else None,
            'scenario_fit_score': scenario_fit_score(scenario_code, title, final_core),
            'core_dialog': final_core,
            'prepared_turns': turns,
            'prepared_core_dialog': final_core,
            'validation_ok': True,
            'validation_reason': 'raw_recent',
            'source_priority': 0,
            'source_type': 'raw_recent',
        })
        if len(candidates) >= limit:
            break
    return candidates


def prepare_case_candidate(conn, case, target_turns=5):
    gk = case.get('group_key')
    core = case.get('core_dialog') or []
    core_rows = [m.get('row_index') for m in core if m.get('row_index') is not None]
    turns = build_turns_around_anchor(
        conn, gk, core_rows, case.get('scenario_code'), target_turns
    ) if gk and core_rows else []
    if case.get('scenario_code') in CUSTOMER_FIRST_SCENARIOS:
        turns = enforce_customer_first_turns(turns)
    final_core = [m for t in turns for m in (t.get('messages') or [])] or core
    first = next((m for m in final_core if is_meaningful_message(m)), final_core[0] if final_core else {})
    reason = []
    if is_outdated_scene(case):
        reason.append('疫情相关过期场景')
    sc = case.get('scenario_code')
    if sc in CUSTOMER_FIRST_SCENARIOS and first.get('role') != 'customer':
        reason.append('客户发起场景首条不是客户')
    if not turns:
        reason.append('无红绿问答切片')
    expected = SCENARIO_DB_NAME.get(sc)
    rows = [m.get('row_index') for m in final_core if m.get('row_index') is not None]
    scene_names = []
    if gk and rows:
        scene_names = [
            r[0] for r in conn.execute(text("""
                SELECT business_scenario_name
                FROM wecom_raw_import
                WHERE group_key=:gk AND row_index = ANY(:rows)
                GROUP BY business_scenario_name
                ORDER BY COUNT(*) DESC
            """), {'gk': gk, 'rows': rows}).fetchall()
        ]
    if expected and expected not in scene_names:
        reason.append(f'核心行未命中场景 {expected}')

    prepared = dict(case)
    prepared['prepared_turns'] = turns
    prepared['prepared_core_dialog'] = final_core
    prepared['scenario_fit_score'] = scenario_fit_score(sc, prepared.get('case_title'), final_core)
    prepared['validation_ok'] = not reason
    prepared['validation_reason'] = '；'.join(reason) if reason else 'ok'
    prepared['source_priority'] = 1
    prepared['source_type'] = 'md'
    return prepared


def upsert_cases(conn, scenarios):
    """每场景取质量分前5；UPSERT 到 case_library_case。"""
    ensure_rejected_table(conn)
    md_name = os.path.basename(MD_PATH)
    total_kept = 0
    for sc in scenarios:
        cases = [prepare_case_candidate(conn, {**c, 'scenario_code': sc['scenario_code']}) for c in sc['cases']]
        raw_cases = load_raw_candidates(conn, sc['scenario_code'], sc['scenario_name'])
        seen = set()
        combined = []
        for c in raw_cases + cases:
            key = (c.get('group_key'), tuple(m.get('row_index') for m in (c.get('prepared_core_dialog') or c.get('core_dialog') or []) if m.get('row_index') is not None))
            if key in seen:
                continue
            seen.add(key)
            combined.append(c)
        sorted_cases = sorted(
            combined,
            key=lambda c: (
                0 if c.get('validation_ok') else 1,
                c.get('source_priority', 9),
                0 if len(c.get('prepared_turns') or []) >= 3 else 1,
                -len(c.get('prepared_turns') or []),
                -(c.get('scenario_fit_score', 0) or 0),
                -(c.get('quality_score', 0) or 0),
                c.get('session_date') or '',
                c.get('case_idx', 999),
            ),
            reverse=False,
        )
        # Within the same validation/source tier, newer raw data should win.
        sorted_cases.sort(key=lambda c: (
            0 if c.get('validation_ok') else 1,
            c.get('source_priority', 9),
            0 if len(c.get('prepared_turns') or []) >= 3 else 1,
            -len(c.get('prepared_turns') or []),
            -(c.get('scenario_fit_score', 0) or 0),
            0 if (c.get('session_date') or '') >= RECENT_CUTOFF.date().isoformat() else 1,
            -(c.get('quality_score', 0) or 0),
            -(int((c.get('session_date') or '0000-00-00').replace('-', '')[:8]) if re.match(r'^\d{4}-\d{2}-\d{2}', c.get('session_date') or '') else 0),
            c.get('case_idx', 999),
        ))
        top5 = sorted_cases[:5]
        soft_reject_existing_slots(conn, [(sc['scenario_code'], rank, c) for rank, c in enumerate(top5, start=1)])
        invalid_kept = [c for c in top5 if not c.get('validation_ok')]
        if invalid_kept:
            print(f'  ⚠ {sc["scenario_code"]} 可用候选不足5个，保留不合格候选: ' + ', '.join(f'{c.get("md_section_anchor")}({c.get("validation_reason")})' for c in invalid_kept))
        for rank, c in enumerate(top5, start=1):
            gk = c.get('group_key')
            row_start = c.get('row_start')
            if not gk or not c.get('core_dialog'):
                print(f'  跳过(缺关键字段): {sc["scenario_code"]}-{c.get("case_idx","??")}')
                continue
            turns = c.get('prepared_turns') or []
            if turns:
                selected_rows = [m['row_index'] for t in turns for m in t['messages'] if m.get('row_index') is not None]
                c['core_dialog'] = [m for t in turns for m in t['messages']]
                c['row_start'] = min(selected_rows)
                c['row_end'] = max(selected_rows)
                row_start = c['row_start']
                for t in turns:
                    t['context_messages'] = fetch_background_messages(conn, gk, t['row_start'], 15)
            else:
                c['core_dialog'] = c.get('prepared_core_dialog') or c.get('core_dialog') or []
                rows = [m.get('row_index') for m in c.get('core_dialog') or [] if m.get('row_index') is not None]
                if rows:
                    c['row_start'] = min(rows)
                    c['row_end'] = max(rows)
                    row_start = c['row_start']
            ctx = fetch_background_messages(conn, gk, row_start, 15) if row_start else []

            sd_str = c.get('session_date')
            try:
                sd = datetime.strptime(sd_str, '%Y-%m-%d') if sd_str else datetime.utcnow()
            except Exception:
                sd = datetime.utcnow()

            payload = {
                'scenario_code': sc['scenario_code'],
                'scenario_name': sc['scenario_name'],
                'scenario_rank': rank,
                'case_title': c.get('case_title') or '',
                'group_key': gk,
                'session_date': sd,
                'batch_id': c.get('batch_id'),
                'slice_ids': json.dumps(c.get('slice_ids', []), ensure_ascii=False),
                'row_start': c.get('row_start'),
                'row_end': c.get('row_end'),
                'quality_score_md': c.get('quality_score'),
                'core_dialog': json.dumps(c['core_dialog'], ensure_ascii=False),
                'context_messages': json.dumps(ctx, ensure_ascii=False),
                'md_source_path': md_name,
                'md_section_anchor': c.get('md_section_anchor'),
            }

            row = conn.execute(text("""
                INSERT INTO case_library_case
                    (case_id, scenario_code, scenario_name, scenario_rank, case_title,
                     group_key, session_date, batch_id, slice_ids, row_start, row_end,
                     quality_score_md, core_dialog, context_messages,
                     md_source_path, md_section_anchor, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :scenario_code, :scenario_name, :scenario_rank, :case_title,
                     :group_key, :session_date, :batch_id, CAST(:slice_ids AS JSON), :row_start, :row_end,
                     :quality_score_md, CAST(:core_dialog AS JSON), CAST(:context_messages AS JSON),
                     :md_source_path, :md_section_anchor, NOW(), NOW())
                ON CONFLICT (scenario_code, scenario_rank) DO UPDATE SET
                    scenario_name=EXCLUDED.scenario_name,
                    case_title=EXCLUDED.case_title,
                    group_key=EXCLUDED.group_key,
                    session_date=EXCLUDED.session_date,
                    batch_id=EXCLUDED.batch_id,
                    slice_ids=EXCLUDED.slice_ids,
                    row_start=EXCLUDED.row_start,
                    row_end=EXCLUDED.row_end,
                    quality_score_md=EXCLUDED.quality_score_md,
                    core_dialog=EXCLUDED.core_dialog,
                    context_messages=EXCLUDED.context_messages,
                    md_source_path=EXCLUDED.md_source_path,
                    md_section_anchor=EXCLUDED.md_section_anchor,
                    updated_at=NOW()
                RETURNING case_id
            """), payload).fetchone()
            case_id = row[0] if row else None
            if case_id:
                upsert_dialogue_turns(
                    conn, case_id, sc['scenario_code'], rank, gk, turns
                )
            total_kept += 1
            print(f'  {sc["scenario_code"]}-{rank}: {c.get("md_section_anchor")} quality={c.get("quality_score")} turns={len(turns)} ctx={len(ctx)}条')
    conn.commit()
    return total_kept


if __name__ == '__main__':
    print('初始化数据库表(创建缺失的新表)...')
    init_db()
    print('解析 sales_scenario_cases_v2.md...')
    scenarios = parse_md()
    for sc in scenarios:
        print(f'  {sc["scenario_code"]} {sc["scenario_name"]}: {len(sc["cases"])}个案例')
    print(f'\n开始导入 case_library_case（每场景前5）...')
    with engine.connect() as conn:
        n = upsert_cases(conn, scenarios)
    print(f'\n完成！共导入/更新 {n} 个案例')
