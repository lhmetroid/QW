"""
生成销售场景典型案例集 markdown 文件
- 10个场景大类，每类10个典型对话
- 保留原始 group_key、消息时间，不改写内容
- 输出文件：sales_scenario_cases.md
"""
import os, sys, io, json, re
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

# ──────────────────────────────────────────────────────────────
# 10 个场景定义（按商业重要度排序）
# ──────────────────────────────────────────────────────────────
SCENARIOS = [
    {
        'name': '方案确认与正式报价',
        'code': 'S01',
        'desc': '客户已有初步意向，双方就具体方案、报价进行确认，是成交前最关键的环节。',
        'importance': '直接影响成交率，是销售漏斗最核心节点。',
    },
    {
        'name': '新客激活',
        'code': 'S02',
        'desc': '首次与潜在客户建立联系，引起关注并推动首次合作意向。',
        'importance': '业务增量的核心来源，决定客户获取效率。',
    },
    {
        'name': '产品/服务细节对标',
        'code': 'S03',
        'desc': '客户就服务能力、交付规格、质量标准等细节进行深度询问和比较。',
        'importance': '建立专业信任，将询价客户转化为意向客户的关键对话。',
    },
    {
        'name': '价格竞争/比价',
        'code': 'S04',
        'desc': '客户明确提出与竞争对手比价，或要求降价，销售需在维护利润的同时守住客户。',
        'importance': '直接影响毛利率和客户留存，考验销售价值塑造能力。',
    },
    {
        'name': '紧急响应/确定性交付',
        'code': 'S05',
        'desc': '客户有紧急交付需求，或在订单执行中追问进度、要求确认节点。',
        'importance': '影响客户满意度和续单，是服务能力的直接体现。',
    },
    {
        'name': '售后纠偏/客诉处理',
        'code': 'S06',
        'desc': '交付后客户反映质量问题、账单纠纷、服务不满等，需及时响应处理。',
        'importance': '直接影响客户留存和口碑，处理不当导致丢单甚至负面传播。',
    },
    {
        'name': '预算收紧',
        'code': 'S07',
        'desc': '客户以预算受限为由暂缓或压缩采购，销售需灵活应对守住合作。',
        'importance': '高频异议场景，决定销售能否守住存量客户。',
    },
    {
        'name': '业务深度介绍',
        'code': 'S08',
        'desc': '向客户系统介绍公司服务范围、核心能力、成功案例及差异化优势。',
        'importance': '决定客户对公司的第一印象和产品认知深度。',
    },
    {
        'name': '节气/开工问候',
        'code': 'S09',
        'desc': '节日、开工、重要时间节点发起的客情维护性问候，保持关系热度。',
        'importance': '低频但高价值，维系长期客户关系的基础动作。',
    },
    {
        'name': '案例分享',
        'code': 'S10',
        'desc': '向客户分享行业成功案例、服务视频或同类客户经验，以案例促进信任。',
        'importance': '软性促单工具，在客户犹豫阶段效果显著。',
    },
]

CASES_PER_SCENARIO = 10
# 偏好多轮对话（≥4条），但也允许精简对话
MIN_MSGS = 2
PREFER_MSGS = 4  # 优先选消息数≥4的组
MAX_MSGS_DISPLAY = 60  # 超长对话截取前60条

def fmt_time(t):
    if t is None:
        return ''
    if isinstance(t, str):
        return t[:19]
    return str(t)[:19]

def role_label(role):
    if role == 'customer':
        return '【客户】'
    elif role == 'sales':
        return '【销售】'
    return '【未知】'

def truncate(content, max_len=500):
    if content and len(content) > max_len:
        return content[:max_len] + '…（内容截断）'
    return content or ''

with e.connect() as c:

    all_md_sections = []

    for sc_idx, sc in enumerate(SCENARIOS):
        sc_name = sc['name']
        sc_code = sc['code']
        print(f'处理场景: {sc_name}')

        # Step1: 获取该场景下所有 group_key，按消息数从多到少排序
        groups = c.execute(text("""
            SELECT group_key,
                   COUNT(*) as msg_cnt,
                   MIN(msg_time) as start_time,
                   MAX(msg_time) as end_time,
                   MIN(slice_title) as title,
                   MIN(business_scenario_code) as sc_code,
                   MIN(quality_score) as q_score,
                   MIN(process_result) as proc_result,
                   MIN(import_batch_id) as batch_id
            FROM wecom_raw_import
            WHERE business_scenario_name = :sc
              AND content IS NOT NULL AND content != ''
            GROUP BY group_key
            HAVING COUNT(*) >= :min_msgs
            ORDER BY COUNT(*) DESC
        """), {'sc': sc_name, 'min_msgs': MIN_MSGS}).fetchall()

        if not groups:
            print(f'  {sc_name}: 无满足条件的数据')
            continue

        # Step2: 选案例策略
        # 优先选消息数 ≥ PREFER_MSGS 的，再选短对话补足
        preferred = [g for g in groups if g[1] >= PREFER_MSGS]
        short_ones = [g for g in groups if g[1] < PREFER_MSGS]

        # 从 preferred 中取最有代表性的（消息数适中：4-30条优先）
        def priority_score(g):
            cnt = g[1]
            # 4-30 条最佳，过长（>60）降权
            if 4 <= cnt <= 30:
                return cnt
            elif cnt > 30:
                return 30 - (cnt - 30) * 0.3
            else:
                return cnt * 0.5

        preferred_sorted = sorted(preferred, key=priority_score, reverse=True)
        short_sorted = sorted(short_ones, key=lambda g: g[1], reverse=True)

        selected_groups = []
        seen_batches = set()
        # 先取 preferred
        for g in preferred_sorted:
            if len(selected_groups) >= CASES_PER_SCENARIO:
                break
            selected_groups.append(g)
        # 补足短对话
        for g in short_sorted:
            if len(selected_groups) >= CASES_PER_SCENARIO:
                break
            selected_groups.append(g)

        selected_groups = selected_groups[:CASES_PER_SCENARIO]

        # Step3: 生成本场景 markdown
        sc_lines = []
        sc_lines.append(f'\n---\n')
        sc_lines.append(f'# {sc_code} {sc_name}\n')
        sc_lines.append(f'**场景描述**：{sc["desc"]}  ')
        sc_lines.append(f'**商业重要性**：{sc["importance"]}  ')
        sc_lines.append(f'**数据来源**：wecom_raw_import | 共 {len(groups)} 个对话组可选，本文选取 {len(selected_groups)} 个\n')

        for case_idx, g in enumerate(selected_groups):
            group_key = g[0]
            msg_cnt = g[1]
            start_time = fmt_time(g[2])
            end_time = fmt_time(g[3])
            title = g[4] or '（无标题）'
            batch_id = g[8] or ''

            # 取该 group 的所有消息，按时间排序
            msgs = c.execute(text("""
                SELECT id, role, content, msg_time, sender, receiver, row_index
                FROM wecom_raw_import
                WHERE group_key = :gk
                  AND content IS NOT NULL AND content != ''
                ORDER BY msg_time ASC, row_index ASC
            """), {'gk': group_key}).fetchall()

            if not msgs:
                continue

            # 判断对话类型：单轮 or 多轮
            real_cnt = len(msgs)
            dialog_type = '多轮对话' if real_cnt >= 4 else '单轮/短对话'

            sc_lines.append(f'\n## 案例 {sc_code}-{case_idx+1:02d}：{title}\n')
            sc_lines.append(f'| 字段 | 值 |')
            sc_lines.append(f'|------|-----|')
            sc_lines.append(f'| **对话ID (group_key)** | `{group_key}` |')
            sc_lines.append(f'| **批次ID (batch_id)** | `{batch_id}` |')
            sc_lines.append(f'| **对话类型** | {dialog_type} |')
            sc_lines.append(f'| **消息总数** | {real_cnt} 条 |')
            sc_lines.append(f'| **开始时间** | {start_time} |')
            sc_lines.append(f'| **结束时间** | {end_time} |')
            sc_lines.append(f'| **场景** | {sc_name} |')
            sc_lines.append(f'| **数据库表** | wecom_raw_import |')
            sc_lines.append('')

            # 如消息过多，只展示前 MAX_MSGS_DISPLAY 条
            display_msgs = msgs[:MAX_MSGS_DISPLAY]
            truncated = len(msgs) > MAX_MSGS_DISPLAY

            sc_lines.append(f'**完整对话记录**（共 {real_cnt} 条{"，以下展示前" + str(MAX_MSGS_DISPLAY) + "条" if truncated else ""}）：\n')

            for msg in display_msgs:
                msg_id = msg[0]
                role = msg[1]
                content = msg[2]
                msg_time = fmt_time(msg[3])
                sender = msg[4] or ''
                row_idx = msg[6]

                rl = role_label(role)
                content_clean = truncate(content, 800)
                # 处理换行，使markdown中保持段落
                content_clean = content_clean.replace('\n', '  \n  ')

                sc_lines.append(f'> **{rl}** `{msg_time}` (id={msg_id}, row={row_idx})')
                sc_lines.append(f'> ')
                sc_lines.append(f'> {content_clean}')
                sc_lines.append(f'>')

            if truncated:
                sc_lines.append(f'\n> ⚠️ 对话过长，已截断。完整数据请查询：`SELECT * FROM wecom_raw_import WHERE group_key = \'{group_key}\' ORDER BY msg_time, row_index`')

            sc_lines.append('')

        all_md_sections.extend(sc_lines)

    # ──────────────────────────────────────────────────────────────
    # 组装最终文档
    # ──────────────────────────────────────────────────────────────
    today = datetime.now().strftime('%Y-%m-%d')

    header = f"""# 销售场景典型案例集

**版本**：v1.0
**生成日期**：{today}
**数据来源**：wecom_raw_import 表（企微历史会话原始数据）
**用途**：作为销售AI训练语料、评价标准参考及销售话术对比基准

## 说明

- 本文档从 `wecom_raw_import` 数据库表提取，**未对对话内容进行改写或创作**
- 每个案例包含 `group_key`（对话组ID）和 `batch_id`（导入批次ID），可精确回溯原始数据
- 案例选取优先多轮完整对话（≥4条），单轮短对话作为补充
- 敏感信息（手机、邮箱、姓名）在原始导入时已按规则脱敏
- 查询原始数据示例：`SELECT * FROM wecom_raw_import WHERE group_key = 'xxx' ORDER BY msg_time, row_index`

## 场景大类目录

| 编号 | 场景名称 | 商业重要度 |
|------|---------|-----------|
| S01 | 方案确认与正式报价 | ★★★★★ 直接成交 |
| S02 | 新客激活 | ★★★★★ 业务增量来源 |
| S03 | 产品/服务细节对标 | ★★★★☆ 转化关键 |
| S04 | 价格竞争/比价 | ★★★★☆ 毛利守护 |
| S05 | 紧急响应/确定性交付 | ★★★★☆ 客户满意度 |
| S06 | 售后纠偏/客诉处理 | ★★★★☆ 留存与口碑 |
| S07 | 预算收紧 | ★★★☆☆ 存量客户守护 |
| S08 | 业务深度介绍 | ★★★☆☆ 认知建立 |
| S09 | 节气/开工问候 | ★★★☆☆ 客情维护 |
| S10 | 案例分享 | ★★★☆☆ 软性促单 |

"""

    full_md = header + '\n'.join(all_md_sections)

    out_path = os.path.join(os.path.dirname(__file__), '..', 'sales_scenario_cases.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(full_md)

    print(f'\n完成！输出文件：{out_path}')
    print(f'总字数约：{len(full_md)} 字符')
