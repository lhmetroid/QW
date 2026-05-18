"""
追加 S11（老客户激活/推新业务）和 S12（转介绍请求）到 sales_scenario_cases_v2.md
"""
import os, sys, io
from datetime import datetime
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

CONTEXT_ROWS = 10
CASES_PER_SCENARIO = 10

NEW_SCENARIOS = [
    {
        'name_db': '老客唤醒',         # 数据库中的 business_scenario_name
        'code': 'S11',
        'display_name': '老客户激活 / 推新业务',
        'desc': '针对沉默或低频老客户，通过问候、案例、新服务介绍重新激活关系，同时顺势推广新业务线。',
        'importance': '老客复购成本极低、信任基础已建立，是高ROI销售动作；推新业务可快速扩大客单价。',
    },
    {
        'name_db': '转介绍请求与存量裂变',
        'code': 'S12',
        'display_name': '转介绍请求',
        'desc': '请求现有客户将服务推荐给同事、其他部门或行业伙伴，实现低成本裂变获客。',
        'importance': '转介绍客户转化率是冷开发3-5倍，是存量客户最高效的裂变手段。',
    },
]

def fmt_time(t):
    if t is None: return ''
    return str(t)[:19]

def role_label(role):
    if role == 'customer': return '【客户】'
    if role == 'sales': return '【销售】'
    return '【未知】'

def clean_content(content, max_len=600):
    if not content: return ''
    c = content.strip()
    if len(c) > max_len:
        c = c[:max_len] + '…（截断）'
    c = c.replace('\r\n', '\n').replace('\r', '\n')
    return c

with e.connect() as conn:
    new_sections = []

    for sc in NEW_SCENARIOS:
        sc_name_db = sc['name_db']
        sc_code = sc['code']
        sc_display = sc['display_name']
        print(f'处理: {sc_display}')

        slices = conn.execute(text("""
            SELECT DISTINCT ON (slice_id)
                   slice_id, group_key, slice_row_start, slice_row_end,
                   slice_title, slice_quality_score, slice_process_result,
                   business_stage, import_batch_id,
                   slice_question, slice_answer
            FROM wecom_raw_import
            WHERE business_scenario_name = :sc
              AND slice_id IS NOT NULL
              AND slice_row_start IS NOT NULL
              AND slice_row_end IS NOT NULL
              AND content NOT LIKE '%未知消息类型%'
              AND slice_title NOT LIKE '%销售单向触达候选%'
            ORDER BY slice_id,
                     CASE slice_process_result
                         WHEN '入库_切片' THEN 1
                         WHEN '待人工确认' THEN 2
                         ELSE 3 END ASC,
                     slice_quality_score DESC NULLS LAST
        """), {'sc': sc_name_db}).fetchall()

        group_count = defaultdict(int)
        selected = []
        priority = [s for s in slices if s[6] == '入库_切片']
        other = [s for s in slices if s[6] != '入库_切片']
        priority.sort(key=lambda s: float(s[5] or 0), reverse=True)
        other.sort(key=lambda s: float(s[5] or 0), reverse=True)

        for s in priority + other:
            if len(selected) >= CASES_PER_SCENARIO:
                break
            if group_count[s[1]] >= 2:
                continue
            selected.append(s)
            group_count[s[1]] += 1

        print(f'  可选切片: {len(slices)}，已选: {len(selected)}')

        sc_lines = []
        sc_lines.append('\n---\n')
        sc_lines.append(f'# {sc_code} {sc_display}\n')
        sc_lines.append(f'**场景描述**：{sc["desc"]}  ')
        sc_lines.append(f'**商业重要性**：{sc["importance"]}  ')
        sc_lines.append(f'**数据来源**：wecom_raw_import 表 | 数据库场景标签=`{sc_name_db}` | 共 {len(slices)} 个切片可选，本文选取 {len(selected)} 个\n')

        for idx, sl in enumerate(selected):
            slice_id = sl[0]
            group_key = sl[1]
            row_start = sl[2]
            row_end = sl[3]
            title = sl[4] or '（无标题）'
            q_score = float(sl[5]) if sl[5] else None
            proc_result = sl[6] or ''
            business_stage = sl[7] or ''
            batch_id = sl[8] or ''
            slice_question = sl[9] or ''
            slice_answer = sl[10] or ''

            ctx_start = max(0, row_start - CONTEXT_ROWS)
            ctx_end = row_end + CONTEXT_ROWS

            msgs = conn.execute(text("""
                SELECT id, row_index, role, content, msg_time
                FROM wecom_raw_import
                WHERE group_key = :gk
                  AND row_index BETWEEN :rs AND :re
                  AND content IS NOT NULL AND content != ''
                ORDER BY row_index ASC, msg_time ASC
            """), {'gk': group_key, 'rs': ctx_start, 're': ctx_end}).fetchall()

            if not msgs:
                continue

            core_msgs = [m for m in msgs if row_start <= m[1] <= row_end]
            has_both = any(m[2] == 'customer' for m in core_msgs) and any(m[2] == 'sales' for m in core_msgs)
            dialog_type = '多轮对话' if len(msgs) >= 4 else '单轮/短对话'
            if not has_both:
                dialog_type += '（单方发言）'

            start_time = fmt_time(msgs[0][4])
            end_time = fmt_time(msgs[-1][4])
            slice_span = row_end - row_start + 1

            sc_lines.append(f'\n## 案例 {sc_code}-{idx+1:02d}：{title}\n')
            sc_lines.append(f'| 字段 | 值 |')
            sc_lines.append(f'|------|-----|')
            sc_lines.append(f'| **切片ID (slice_id)** | `{slice_id}` |')
            sc_lines.append(f'| **对话组ID (group_key)** | `{group_key}` |')
            sc_lines.append(f'| **批次ID** | `{batch_id}` |')
            sc_lines.append(f'| **切片行范围** | row {row_start} ~ {row_end}（共 {slice_span} 行） |')
            sc_lines.append(f'| **对话类型** | {dialog_type} |')
            sc_lines.append(f'| **时间范围** | {start_time} 至 {end_time} |')
            sc_lines.append(f'| **商业阶段** | {business_stage} |')
            sc_lines.append(f'| **知识处理结论** | {proc_result} |')
            if q_score is not None:
                sc_lines.append(f'| **质量分** | {q_score:.0f}/100 |')
            sc_lines.append(f'| **查询原始数据** | `SELECT * FROM wecom_raw_import WHERE group_key = \'{group_key}\' AND row_index BETWEEN {row_start} AND {row_end} ORDER BY row_index` |')
            sc_lines.append('')

            if slice_question or slice_answer:
                sc_lines.append('**AI提取摘要**：\n')
                if slice_question:
                    sc_lines.append(f'- **触发场景/客户问题**：{slice_question.strip()}')
                if slice_answer:
                    sc_lines.append(f'- **销售回复要点**：{slice_answer.strip()}')
                sc_lines.append('')

            sc_lines.append(f'**完整对话记录**（切片核心 row {row_start}-{row_end}，含前后 {CONTEXT_ROWS} 行上下文，共 {len(msgs)} 条）：\n')

            for m in msgs:
                msg_id, row_idx, role, content, msg_time = m[0], m[1], m[2], m[3], m[4]
                is_core = row_start <= row_idx <= row_end
                prefix = '▶ ' if is_core else '  '
                rl = role_label(role)
                content_clean = clean_content(content)
                sc_lines.append(f'{prefix}**{rl}** `{fmt_time(msg_time)}` _(id={msg_id}, row={row_idx}{"，核心" if is_core else "，上下文"})_')
                for cl in content_clean.split('\n'):
                    if cl.strip():
                        sc_lines.append(f'{prefix}{cl}')
                sc_lines.append('')

        new_sections.extend(sc_lines)

    # ── 读取现有文件，更新目录，追加内容 ──
    md_path = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
    with open(md_path, encoding='utf-8') as f:
        existing = f.read()

    # 更新目录表格：在 S10 行后追加 S11、S12
    s11_row = '| S11 | 老客户激活 / 推新业务 | ★★★★★ | 老客复购+推新业务 |'
    s12_row = '| S12 | 转介绍请求 | ★★★★★ | 存量裂变 |'
    old_s10_row = '| S10 | 案例分享 | ★★★☆☆ | 软性促单 |'
    new_table_end = old_s10_row + '\n' + s11_row + '\n' + s12_row

    if s11_row not in existing:
        existing = existing.replace(old_s10_row, new_table_end)

    # 更新版本和日期
    today = datetime.now().strftime('%Y-%m-%d')
    existing = existing.replace('**版本**：v2.0', '**版本**：v2.1')
    existing = existing.replace(
        '**用途**：销售AI训练语料、评价基准、销售话术对比',
        f'**生成日期**：{today}  \n**用途**：销售AI训练语料、评价基准、销售话术对比'
    )

    # 追加新场景到文件末尾
    full_content = existing.rstrip() + '\n' + '\n'.join(new_sections)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f'\n完成！文件已更新：{md_path}')
    print(f'新增字符数：{len(full_content) - len(existing)}')
    print(f'总字符数：{len(full_content)}')
