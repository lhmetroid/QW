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

from database import engine, SessionLocal, CaseLibraryCase, init_db
from sqlalchemy import text

MD_PATH = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')

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
        ORDER BY row_index DESC
        LIMIT :n
    """), {'gk': group_key, 'rs': row_start, 'n': n}).fetchall()
    rows = list(reversed(rows))  # 还原成时间顺序
    return [{
        'role': r[2] or 'unknown',
        'msg_time': str(r[4])[:19] if r[4] else None,
        'msg_id': r[0],
        'row_index': r[1],
        'content': (r[3] or '').strip(),
    } for r in rows]


def upsert_cases(conn, scenarios):
    """每场景取质量分前5；UPSERT 到 case_library_case。"""
    md_name = os.path.basename(MD_PATH)
    total_kept = 0
    for sc in scenarios:
        cases = sc['cases']
        # 按 quality_score 降序，缺失质量分置 0
        sorted_cases = sorted(cases, key=lambda c: c.get('quality_score', 0) or 0, reverse=True)
        top5 = sorted_cases[:5]
        for rank, c in enumerate(top5, start=1):
            gk = c.get('group_key')
            row_start = c.get('row_start')
            if not gk or not c.get('core_dialog'):
                print(f'  跳过(缺关键字段): {sc["scenario_code"]}-{c.get("case_idx","??")}')
                continue
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

            conn.execute(text("""
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
            """), payload)
            total_kept += 1
            print(f'  {sc["scenario_code"]}-{rank}: {c.get("md_section_anchor")} quality={c.get("quality_score")} ctx={len(ctx)}条')
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
