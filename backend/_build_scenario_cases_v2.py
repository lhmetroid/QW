"""
v2：以切片（slice_id）为单位选取典型案例，每个切片对应明确场景，加上下文窗口展示完整对话
- 10个场景，每场景10个典型切片案例
- 每案例展示：切片核心行 + 前后各10行上下文
- 每场景内尽量使用不同 group_key（不同客户）
- 输出：sales_scenario_cases_v2.md
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

SCENARIOS = [
    {
        'name': '方案确认与正式报价', 'code': 'S01',
        'desc': '客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。',
        'importance': '直接影响成交率，是销售漏斗最核心节点。',
    },
    {
        'name': '新客激活', 'code': 'S02',
        'desc': '首次与潜在客户建立联系，引起关注并推动首次合作意向。',
        'importance': '业务增量的核心来源，决定客户获取效率。',
    },
    {
        'name': '产品/服务细节对标', 'code': 'S03',
        'desc': '客户就服务能力、交付规格、质量标准等细节进行深度询问和比较。',
        'importance': '建立专业信任，将询价客户转化为意向客户的关键对话。',
    },
    {
        'name': '价格竞争/比价', 'code': 'S04',
        'desc': '客户明确提出与竞争对手比价，或要求降价，销售需在维护利润的同时守住客户。',
        'importance': '直接影响毛利率和客户留存，考验销售价值塑造能力。',
    },
    {
        'name': '紧急响应/确定性交付', 'code': 'S05',
        'desc': '客户有紧急交付需求，或在订单执行中追问进度、要求确认节点。',
        'importance': '影响客户满意度和续单，是服务能力的直接体现。',
    },
    {
        'name': '售后纠偏/客诉处理', 'code': 'S06',
        'desc': '交付后客户反映质量问题、账单纠纷、服务不满等，需及时响应处理。',
        'importance': '直接影响客户留存和口碑，处理不当导致丢单甚至负面传播。',
    },
    {
        'name': '预算收紧', 'code': 'S07',
        'desc': '客户以预算受限为由暂缓或压缩采购，销售需灵活应对守住合作。',
        'importance': '高频异议场景，决定销售能否守住存量客户。',
    },
    {
        'name': '业务深度介绍', 'code': 'S08',
        'desc': '向客户系统介绍公司服务范围、核心能力、成功案例及差异化优势。',
        'importance': '决定客户对公司的第一印象和产品认知深度。',
    },
    {
        'name': '节气/开工问候', 'code': 'S09',
        'desc': '节日、开工、重要时间节点发起的客情维护性问候，保持关系热度。',
        'importance': '低频但高价值，维系长期客户关系的基础动作。',
    },
    {
        'name': '案例分享', 'code': 'S10',
        'desc': '向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。',
        'importance': '软性促单工具，在客户犹豫阶段效果显著。',
    },
]

CASES_PER_SCENARIO = 10
CONTEXT_ROWS = 10  # 切片前后各展示多少行上下文

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
    # 换行转 markdown
    c = c.replace('\r\n', '\n').replace('\r', '\n')
    return c

with e.connect() as c:
    all_md_sections = []

    for sc in SCENARIOS:
        sc_name = sc['name']
        sc_code = sc['code']
        print(f'处理: {sc_name}')

        # 获取该场景下所有独立切片，按质量分排序
        # 优先 '入库_切片'，其次 '待人工确认'，兜底取全部有场景标注的
        # 过滤：排除核心内容全是【未知消息类型】的切片
        slices = c.execute(text("""
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
            ORDER BY slice_id,
                     CASE slice_process_result
                         WHEN '入库_切片' THEN 1
                         WHEN '待人工确认' THEN 2
                         ELSE 3 END ASC,
                     slice_quality_score DESC NULLS LAST
        """), {'sc': sc_name}).fetchall()

        # 选案例：每个group_key最多取2个切片，保证多样性
        group_count = defaultdict(int)
        selected = []
        # 先选高质量（入库_切片）
        priority_slices = [s for s in slices if s[6] == '入库_切片']
        other_slices = [s for s in slices if s[6] != '入库_切片']
        # 按质量分排序
        priority_slices.sort(key=lambda s: float(s[5] or 0), reverse=True)
        other_slices.sort(key=lambda s: float(s[5] or 0), reverse=True)

        for s in priority_slices + other_slices:
            if len(selected) >= CASES_PER_SCENARIO:
                break
            gk = s[1]
            if group_count[gk] >= 2:
                continue
            selected.append(s)
            group_count[gk] += 1

        if len(selected) < CASES_PER_SCENARIO:
            print(f'  警告：{sc_name} 只有 {len(selected)} 个切片案例（目标 {CASES_PER_SCENARIO}）')

        sc_lines = []
        sc_lines.append('\n---\n')
        sc_lines.append(f'# {sc_code} {sc_name}\n')
        sc_lines.append(f'**场景描述**：{sc["desc"]}  ')
        sc_lines.append(f'**商业重要性**：{sc["importance"]}  ')
        sc_lines.append(f'**数据来源**：wecom_raw_import 表 | 共 {len(slices)} 个切片可选，本文选取 {len(selected)} 个\n')

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

            # 判断对话模式：单轮还是多轮（切片内消息数）
            slice_span = row_end - row_start + 1
            # 获取上下文范围内的消息
            ctx_start = max(0, row_start - CONTEXT_ROWS)
            ctx_end = row_end + CONTEXT_ROWS

            msgs = c.execute(text("""
                SELECT id, row_index, role, content, msg_time, sender
                FROM wecom_raw_import
                WHERE group_key = :gk
                  AND row_index BETWEEN :rs AND :re
                  AND content IS NOT NULL AND content != ''
                ORDER BY row_index ASC, msg_time ASC
            """), {'gk': group_key, 'rs': ctx_start, 're': ctx_end}).fetchall()

            if not msgs:
                continue

            core_msgs = [m for m in msgs if row_start <= m[1] <= row_end]
            has_both_roles = (
                any(m[2] == 'customer' for m in core_msgs) and
                any(m[2] == 'sales' for m in core_msgs)
            )
            dialog_type = '多轮对话' if len(msgs) >= 4 else '单轮/短对话'
            if not has_both_roles:
                dialog_type += '（单方发言）'

            start_time = fmt_time(msgs[0][4])
            end_time = fmt_time(msgs[-1][4])
            total_msgs_shown = len(msgs)

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
            # LLM提取的摘要（如有）
            if slice_question or slice_answer:
                sc_lines.append('**AI提取摘要**（LLM自动抽取，用于快速理解核心内容）：\n')
                if slice_question:
                    sc_lines.append(f'- **客户问题/触发场景**：{slice_question.strip()}')
                if slice_answer:
                    sc_lines.append(f'- **销售回复要点**：{slice_answer.strip()}')
                sc_lines.append('')
            sc_lines.append(f'**完整对话记录**（切片核心 row {row_start}-{row_end}，含前后 {CONTEXT_ROWS} 行上下文，共展示 {total_msgs_shown} 条）：\n')

            for m in msgs:
                msg_id = m[0]
                row_idx = m[1]
                role = m[2]
                content = m[3]
                msg_time = fmt_time(m[4])

                is_core = row_start <= row_idx <= row_end
                prefix = '▶ ' if is_core else '  '  # 核心行用▶标记
                rl = role_label(role)
                content_clean = clean_content(content)
                content_lines = content_clean.split('\n')

                sc_lines.append(f'{prefix}**{rl}** `{msg_time}` _(id={msg_id}, row={row_idx}{"，核心" if is_core else "，上下文"})_')
                for cl in content_lines:
                    if cl.strip():
                        sc_lines.append(f'{prefix}{cl}')
                sc_lines.append('')

        all_md_sections.extend(sc_lines)

    # ── 组装文档 ──────────────────────────────────────────────────
    today = datetime.now().strftime('%Y-%m-%d')
    header = f"""# 销售场景典型案例集 v2

**版本**：v2.0
**生成日期**：{today}
**数据来源**：`wecom_raw_import` 表（企微历史会话原始数据，已系统预处理）
**用途**：销售AI训练语料、评价基准、销售话术对比

## 使用说明

### 数据真实性保证
- 所有对话内容**原文提取，未改写、未创作**
- 敏感信息（手机、邮箱、姓名）在原始导入阶段已按规则脱敏（替换为 `[客户电话]`、`[客户邮箱]` 等占位符）
- 我方公司名（事必达、嘉赛等）保留

### 案例溯源
每个案例包含：
- **slice_id**：切片ID，知识库最小单元，可精确定位
- **group_key**：对话组ID，对应一对一完整沟通线
- **batch_id**：导入批次ID
- **切片行范围**：CSV原始行号，可精确回溯
- **SQL查询示例**：直接复制执行，即可在数据库中找回原始数据

### 对话展示格式
- `▶` 前缀 = 切片核心内容（LLM已识别为该场景的关键对话段）
- 无前缀 = 上下文（切片前后各 {CONTEXT_ROWS} 行，用于理解对话背景）
- `【销售】` / `【客户】` = 发言角色

### 训练价值评估参考
| 知识处理结论 | 含义 | 训练价值 |
|------------|------|---------|
| 入库_切片 | AI判断有知识价值，已入库 | ★★★★★ 最高 |
| 待人工确认 | AI判断边界情况，需人工审核 | ★★★☆☆ 中等 |
| 不入库_简单确认 | 仅确认类，信息量有限 | ★★☆☆☆ 较低 |

## 场景目录

| 编号 | 场景名称 | 商业重要度 | 说明 |
|------|---------|-----------|------|
| S01 | 方案确认与正式报价 | ★★★★★ | 直接成交节点 |
| S02 | 新客激活 | ★★★★★ | 业务增量来源 |
| S03 | 产品/服务细节对标 | ★★★★☆ | 转化关键对话 |
| S04 | 价格竞争/比价 | ★★★★☆ | 毛利与留客 |
| S05 | 紧急响应/确定性交付 | ★★★★☆ | 服务能力体现 |
| S06 | 售后纠偏/客诉处理 | ★★★★☆ | 留存与口碑 |
| S07 | 预算收紧 | ★★★☆☆ | 异议应对 |
| S08 | 业务深度介绍 | ★★★☆☆ | 认知建立 |
| S09 | 节气/开工问候 | ★★★☆☆ | 客情维护 |
| S10 | 案例分享 | ★★★☆☆ | 软性促单 |

"""

    full_md = header + '\n'.join(all_md_sections)

    out_path = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases_v2.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(full_md)

    print(f'\n输出文件：{out_path}')
    print(f'总字符数：{len(full_md)}')
