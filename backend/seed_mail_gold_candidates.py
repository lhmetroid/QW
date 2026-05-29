"""邮件黄金种子灌库脚本 (Phase 5 / Task 76 / v1.7.209 重写)

把 docs/mail_gold_candidates/latest_mail_gold_candidates.json 里的 25 条候选切片
真实写入 email_fragment_asset 表，作为 POST /api/v1/mail/generate-draft 的
Few-Shot 检索数据源。

v1.7.209 改动:
- 不再把 function_fragment 写死成 "example" — 改为读 JSON 里每条的真实分类
  ( ∈ {greetings, example, process, constraint, quotation} )，跟
  mail_sequence_strategy.MailSnippetType 对齐。
- 不再把 scenario 全部当 re_activation — 改为读 JSON 里每条的真实 scenario
  ( ∈ {re_activation, new_business_promotion, new_contact_intro} )。
- 默认 --clean-first 开关：跑前先 DELETE 旧的 mail_gold_seed 行，避免重灌污染。
- 不再用 v1.7.208 注释掉的 _to_decimal default 兜底；JSON 缺 useful_score
  直接 raise，按 v1.7.208 "宁报错或为空" 原则。

使用:
    cd backend && python seed_mail_gold_candidates.py --clean-first
    # 或自定义路径:
    python seed_mail_gold_candidates.py --json /abs/path/to/seeds.json --dry-run

幂等:
    以 (source_type='mail_gold_seed', source_ref=<candidate_id>) 为唯一键，
    重复跑只 update 不 insert。带 --clean-first 时先全删再插。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED_JSON = REPO_ROOT / "docs" / "mail_gold_candidates" / "latest_mail_gold_candidates.json"

sys.path.insert(0, str(REPO_ROOT / "backend"))

from database import EmailFragmentAsset, SessionLocal  # noqa: E402
from knowledge_governance import infer_function_fragment  # noqa: E402

SEED_SOURCE_TYPE = "mail_gold_seed"
SEED_LIBRARY_TYPE = "gold_seed"


VALID_FRAGMENTS = {"greetings", "example", "process", "constraint", "quotation"}
VALID_SCENARIOS = {"re_activation", "new_business_promotion", "new_contact_intro"}


# v1.7.219: 把 CSV 原文里的项目符号字符 (转 UTF-8 时变 ?) 清洗为可读符号
_LEADING_BULLET_RE = re.compile(r"^[\??¿　\s]*[\?¿]\s*(?=[一-鿿A-Za-z0-9])", re.MULTILINE)
_LEADING_T_C_RE = re.compile(r"^[tC]\s*(?=[一-鿿])", re.MULTILINE)


def _clean_bullet_chars(text: str) -> str:
    """清洗 CSV 原文里转码失败的项目符号 ?/¿/t/C → •"""
    if not text:
        return text
    out = _LEADING_BULLET_RE.sub("• ", text)
    out = _LEADING_T_C_RE.sub("• ", out)
    return out


# v1.7.219: knowledge_governance 6 类 → mail_sequence_strategy 5 类映射
# (knowledge_chunk 表用 6 类, mail_sequence_strategy.MailSnippetType 用 5 类, 必须映射对齐)
def _kg_to_mss_fragment(kg_fragment: str | None, paragraph_text: str) -> str:
    """把 knowledge_governance 推断的 6 类映射到 mail_sequence_strategy 5 类。

    映射规则 (优先按段落关键词命中 quotation/constraint, 再按 kg 类型默认归类):
    """
    text_lower = (paragraph_text or "").lower()
    # 优先: 含报价数字 → quotation
    if any(k in text_lower for k in ["报价", "单价", "折扣", "折后", "总价", "元/", "美元/", "￥", "rmb", "usd", "quote"]):
        return "quotation"
    # 含工期/账期/约束 → constraint
    if any(k in text_lower for k in ["账期", "付款", "结算", "天后付", "工期", "交期", "deadline", "天内", "周期"]):
        return "constraint"
    # 含流程/服务范围 → process
    if any(k in text_lower for k in ["流程", "步骤", "服务范围", "操作", "方式", "如何"]):
        return "process"
    # 按 kg 类型默认归类
    if kg_fragment == "highlight":
        return "example"   # 亮点案例 → 案例示范
    if kg_fragment in ("greeting", "closing"):
        return "greetings"  # 开场/收尾 → 问候开场
    if kg_fragment == "background":
        return "greetings"  # 背景介绍 → 开场铺垫
    if kg_fragment == "core_answer":
        return "process"    # 核心方案 → 流程说明
    if kg_fragment == "cta":
        return "example"    # 行动呼吁 → 案例性收尾
    return "example"        # 兜底


def _split_email_into_mail_seq_fragments(subject: str, content: str, *, max_segments: int = 6) -> list[dict]:
    """v1.7.219 按段切邮件, 每段标 mail_sequence_strategy 5 类 function_fragment。

    切分逻辑 (v1.7.219.1 简化, 避免切得太碎):
    - 只按双换行 \\n{2,} 切段, 不再按单换行细分 (展会列表等行行拆开会过碎)
    - 短段 (<60 字) 跟前段合并 (避免行首 • 项目符号变成独立段)
    - 最多 max_segments=6 段, 超出的并入最后一段
    """
    text = (content or "").strip()
    if not text:
        return []
    # 一级切: 按双换行
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not raw_paragraphs:
        raw_paragraphs = [text]
    # 短段合并: <60 字的段并入前段, 避免碎片
    merged = []
    for p in raw_paragraphs:
        if merged and len(p) < 60:
            merged[-1] = merged[-1] + "\n" + p
        else:
            merged.append(p)
    paragraphs = merged
    # 超 max_segments 的并入最后一段
    if len(paragraphs) > max_segments:
        head = paragraphs[: max_segments - 1]
        tail = "\n".join(paragraphs[max_segments - 1:])
        paragraphs = head + [tail]

    fragments = []
    char_cursor = 0
    for index, paragraph in enumerate(paragraphs[:max_segments], start=1):
        kg_kind = infer_function_fragment(
            title=subject,
            content=paragraph,
            source_type="email_excel",
            tags={},
        ) or ("core_answer" if index == len(paragraphs) else "background")
        mss_kind = _kg_to_mss_fragment(kg_kind, paragraph)
        # 算 segment 在原邮件里的字符位置
        seg_start = text.find(paragraph[:40], char_cursor)
        if seg_start < 0:
            seg_start = char_cursor
        seg_end = seg_start + len(paragraph)
        char_cursor = seg_end
        fragments.append({
            "segment_no": index,
            "content": paragraph,
            "function_fragment": mss_kind,
            "kg_fragment_inferred": kg_kind,
            "char_count": len(paragraph),
            "segment_start_char": seg_start,
            "segment_end_char": seg_end,
        })
    return fragments


def _require_decimal(value, field: str, candidate_id: str) -> Decimal:
    # v1.7.208 "宁报错不兜底" — 缺字段或非法值直接 raise, 不再 default '0.0' 兜底.
    if value is None:
        raise ValueError(f"candidate {candidate_id} 缺 {field} 字段（v1.7.209 不再 default 兜底）")
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except Exception as exc:
        raise ValueError(f"candidate {candidate_id} 的 {field}={value!r} 不是合法 Decimal: {exc}") from exc


def upsert_seed_segments(db, candidate: dict, idx: int) -> list[tuple[str, str, dict]]:
    """v1.7.219: 一条 candidate 切成 N 段, 每段独立 upsert 一条 email_fragment_asset。

    返回 [(action, fragment_id_str, segment_meta), ...]
    """
    candidate_id = (candidate.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError(f"row#{idx} 缺 candidate_id")

    raw_body = (candidate.get("body_text") or "").strip()
    if not raw_body:
        raise ValueError(f"{candidate_id} body_text 为空")
    # v1.7.219: 清洗 ? 项目符号
    body_text = _clean_bullet_chars(raw_body)

    raw_subject = (candidate.get("subject") or "").strip()
    if not raw_subject:
        raise ValueError(f"{candidate_id} subject 为空")
    subject = _clean_bullet_chars(raw_subject)[:255]

    scenario = (candidate.get("scenario") or "").strip()
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"{candidate_id} scenario={scenario!r} 不在 {VALID_SCENARIOS}")

    useful_score = _require_decimal(candidate.get("useful_score"), "useful_score", candidate_id)

    # 切段
    segments = _split_email_into_mail_seq_fragments(subject, body_text)
    if not segments:
        raise ValueError(f"{candidate_id} 切段后段数=0, body_text={body_text[:60]!r}")

    results = []
    for seg in segments:
        seg_source_ref = f"{candidate_id}_seg{seg['segment_no']}_{seg['function_fragment']}"
        seg_title = f"{subject} · 段{seg['segment_no']}·{seg['function_fragment']}"[:255]
        existing = (
            db.query(EmailFragmentAsset)
            .filter(
                EmailFragmentAsset.source_type == SEED_SOURCE_TYPE,
                EmailFragmentAsset.source_ref == seg_source_ref,
            )
            .first()
        )
        if existing is None:
            item = EmailFragmentAsset(
                source_type=SEED_SOURCE_TYPE,
                source_ref=seg_source_ref,
                thread_id=candidate_id,
                title=seg_title,
                content=seg["content"],
            )
            db.add(item)
            db.flush()
            action = "inserted"
        else:
            item = existing
            item.title = seg_title
            item.content = seg["content"]
            action = "updated"

        # v1.7.219: 段级 function_fragment (来自 knowledge_governance 推断 + KG→MSS 映射)
        item.function_fragment = seg["function_fragment"]
        item.scenario_label = scenario
        item.intent_label = scenario
        item.language_style = "mixed_cn_en"
        item.library_type = SEED_LIBRARY_TYPE
        item.allowed_for_generation = True
        item.usable_for_reply = True
        item.publishable = True
        item.useful_score = useful_score
        item.topic_clarity_score = useful_score
        item.completeness_score = useful_score
        item.reusability_score = useful_score
        item.evidence_reliability_score = useful_score
        item.status = "ready"
        item.source_snapshot = {
            "seed_loader_version": "v1.7.219",
            "seed_source_file": str(DEFAULT_SEED_JSON.relative_to(REPO_ROOT)),
            "candidate_rank": candidate.get("rank"),
            "parent_candidate_id": candidate_id,
            "parent_subject": subject,
            "csv_source_ref": candidate.get("source_ref"),
            "scenario": scenario,
            "scenario_label_cn": candidate.get("scenario_label_cn"),
            # 段级元信息 (前端用来展示"切片怎么切的")
            "segment_no": seg["segment_no"],
            "segment_total": len(segments),
            "segment_char_count": seg["char_count"],
            "segment_start_char": seg["segment_start_char"],
            "segment_end_char": seg["segment_end_char"],
            "kg_fragment_inferred": seg["kg_fragment_inferred"],
            "function_fragment_mapped": seg["function_fragment"],
            "split_method": "split_by_double_newline + infer_function_fragment + kg_to_mss_mapping",
            "bullet_cleaned": raw_body != body_text,
            "desensitized_status": candidate.get("desensitized_status"),
            "desensitized_fields": candidate.get("desensitized_fields") or [],
            "useful_score": float(useful_score),
            "score_source": candidate.get("score_source"),
            "csv_source_file": candidate.get("csv_source_file"),
            "email_stage": candidate.get("email_stage"),
        }
        item.quality_notes = {
            "loader": "seed_mail_gold_candidates.py",
            "loader_version": "v1.7.219",
            "curation_method": "segment_split_kg_inferred_mss_mapped",
        }
        results.append((action, str(item.fragment_id), {
            "seg_no": seg["segment_no"],
            "fragment": seg["function_fragment"],
            "char_count": seg["char_count"],
        }))
    return results


def main():
    parser = argparse.ArgumentParser(description="Seed email_fragment_asset with mail gold candidates (v1.7.209)")
    parser.add_argument("--json", default=str(DEFAULT_SEED_JSON), help="JSON file path")
    parser.add_argument("--dry-run", action="store_true", help="不提交事务，只打印将要做什么")
    parser.add_argument("--clean-first", action="store_true",
                        help="跑前先 DELETE 所有 source_type='mail_gold_seed' 旧行（v1.7.209 推荐用，重灌新分类）")
    args = parser.parse_args()

    seed_path = Path(args.json)
    if not seed_path.exists():
        print(f"[seed] ERROR: seed file not found: {seed_path}", file=sys.stderr)
        sys.exit(2)

    with seed_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    candidates = payload.get("candidates") or []
    print(f"[seed] 读到 {len(candidates)} 条候选，源文件: {seed_path}")
    print(f"[seed] payload version: {payload.get('version')!r}")

    db = SessionLocal()
    inserted = 0
    updated = 0
    try:
        if args.clean_first:
            deleted = db.query(EmailFragmentAsset).filter(
                EmailFragmentAsset.source_type == SEED_SOURCE_TYPE
            ).delete(synchronize_session=False)
            print(f"[seed] --clean-first: 已删除 {deleted} 行旧 mail_gold_seed")

        for idx, candidate in enumerate(candidates, start=1):
            seg_results = upsert_seed_segments(db, candidate, idx)
            for action, frag_id, meta in seg_results:
                if action == "inserted":
                    inserted += 1
                else:
                    updated += 1
                print(f"  [{idx:02d} seg{meta['seg_no']}] {action:8s}  {frag_id}  | "
                      f"{candidate.get('candidate_id')}  fragment={meta['fragment']}  chars={meta['char_count']}")

        if args.dry_run:
            db.rollback()
            print(f"[seed] DRY-RUN 已回滚。inserted={inserted} updated={updated}")
        else:
            db.commit()
            print(f"[seed] COMMIT 完成。inserted={inserted} updated={updated}")

        total = (
            db.query(EmailFragmentAsset)
            .filter(EmailFragmentAsset.source_type == SEED_SOURCE_TYPE)
            .count()
        )
        print(f"[seed] 当前 email_fragment_asset 表中 source_type='{SEED_SOURCE_TYPE}' 共 {total} 行")

        # 打印分类分布以便验证
        from collections import Counter
        rows = db.query(EmailFragmentAsset).filter(
            EmailFragmentAsset.source_type == SEED_SOURCE_TYPE
        ).all()
        sc = Counter(r.scenario_label for r in rows)
        fr = Counter(r.function_fragment for r in rows)
        print(f"[seed] scenario distribution: {dict(sc)}")
        print(f"[seed] function_fragment distribution: {dict(fr)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
