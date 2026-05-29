"""从知识库 (KnowledgeChunk) 抽取 constraint / quotation 类切片入 email_fragment_asset (v1.7.213)

背景:
- 邮件 AI 回复 12 个 step 里有 6 step 需 constraint, 3 step 需 quotation 类 Few-Shot.
- 之前的 25 条黄金种子源自销售开发邮件 CSV, 全是 greetings/example/process, 真实 0 条 constraint/quotation.
- 但知识库 KnowledgeChunk 表里已有 constraint=1612 条 + rule(knowledge_type=pricing)=1121 条 高质量话术规则,
  完全可作为这两类切片的 Few-Shot 范例来源.

策略:
- constraint: 从 chunk_type='constraint' AND status='active' 按 useful_score 取前 N 条
- quotation: 从 chunk_type='rule' AND knowledge_type='pricing' AND status='active' 按 useful_score 取前 N 条
- 新条目入 email_fragment_asset 表, source_type='mail_pricing_constraint_seed' (不复用 mail_gold_seed 以区分来源)
- scenario_label 统一 'new_business_promotion' (因为 mail_sequence_strategy step 4 报价场景主要属此场景;
  其他场景 step 3/4 实际也会召回 — _mail_generate_draft_fewshot 不强匹配 scenario 字段, 只匹配 function_fragment)
- 跑前先 --clean-first DELETE 旧的 mail_pricing_constraint_seed 行避免污染

幂等:
- 以 (source_type='mail_pricing_constraint_seed', source_ref=kb_chunk_<chunk_id>) 为唯一键
- 带 --clean-first 时先全删再插

使用:
    cd backend && python seed_mail_pricing_constraint_from_kb.py --clean-first
    # 或自定义条数:
    python seed_mail_pricing_constraint_from_kb.py --clean-first --top 15
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from database import EmailFragmentAsset, KnowledgeChunk, SessionLocal  # noqa: E402

SEED_SOURCE_TYPE = "mail_pricing_constraint_seed"
SEED_LIBRARY_TYPE = "gold_seed"

# 默认场景标签 (mail_sequence_strategy 里报价主要出现在 new_business_promotion step 4)
DEFAULT_SCENARIO = "new_business_promotion"

# 简易脱敏: 知识库切片大多没具体客户名, 但保险起见过滤一下
PATTERN_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
PATTERN_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
# 已知敏感实体 (跟 v1.7.212 黄金种子脱敏表对齐)
KB_SENSITIVE_REPLACE = [
    ("Joyce Sheng", "您的销售顾问"),
    ("Tiffany", "您的销售顾问"),
    ("王慧莹", "您的销售顾问"),
    ("帝斯曼-芬美意", "[国际生命科学企业]"),
    ("帝斯曼芬美意", "[国际生命科学企业]"),
    ("帝斯曼", "[国际生命科学企业]"),
    ("EVONIK", "[国际化工品牌]"),
    ("BASF SE", "[国际化工企业]"),
    ("BASF", "[国际化工企业]"),
    ("巴斯夫", "[国际化工企业]"),
    ("科思创", "[国际化工企业]"),
    ("德固赛", "[国际化工企业]"),
    ("凯密特尔", "[国际化工企业]"),
    ("Medtronic", "[国际医疗器械企业]"),
    ("Johnson & Johnson", "[国际医药企业]"),
    ("Edwards Lifesciences", "[国际医疗器械企业]"),
    ("GE HealthCare", "[国际医疗器械企业]"),
    ("Boston Scientific", "[国际医疗器械企业]"),
    ("Fresenius Medical Care", "[国际医疗器械企业]"),
    ("Standard Chartered Bank", "[国际金融机构]"),
    ("DBS Bank", "[国际金融机构]"),
    ("BNP Paribas", "[国际金融机构]"),
    ("Allspring", "[国际金融科技品牌]"),
    ("Jumio", "[国际金融科技品牌]"),
    ("拜耳", "[国际医药企业]"),
    ("碧迪", "[国际医疗器械企业]"),
    ("Apple", "[国际科技品牌]"),
    ("恒瑞医药", "[国内大型医药企业]"),
    ("信达生物", "[国内大型医药企业]"),
    ("复星医药", "[国内大型医药企业]"),
    ("石药集团", "[国内大型医药企业]"),
    ("上海电气", "[国内大型装备制造企业]"),
]


def desensitize(text: str) -> tuple[str, list[str]]:
    hits = set()
    out = text or ""
    for src, dst in KB_SENSITIVE_REPLACE:
        if src in out:
            out = out.replace(src, dst)
            hits.add("customer_industry_or_company")
    if PATTERN_PHONE.search(out):
        out = PATTERN_PHONE.sub("***手机号***", out)
        hits.add("phone_number")
    if PATTERN_EMAIL.search(out):
        out = PATTERN_EMAIL.sub("***邮箱***", out)
        hits.add("email_address")
    return out, sorted(hits)


def upsert_kb_chunk_as_fewshot(
    db,
    chunk: KnowledgeChunk,
    function_fragment: str,
) -> tuple[str, str]:
    candidate_id = f"kb_chunk_{chunk.chunk_id}"

    body_text, hit_fields = desensitize(chunk.content or "")
    if not body_text.strip():
        raise ValueError(f"chunk {chunk.chunk_id} content 为空, 拒绝入库")

    subject, _subj_hits = desensitize(chunk.title or "")
    if not subject.strip():
        raise ValueError(f"chunk {chunk.chunk_id} title 为空, 拒绝入库")
    subject = subject[:255]

    existing = (
        db.query(EmailFragmentAsset)
        .filter(
            EmailFragmentAsset.source_type == SEED_SOURCE_TYPE,
            EmailFragmentAsset.source_ref == candidate_id,
        )
        .first()
    )

    if existing is None:
        item = EmailFragmentAsset(
            source_type=SEED_SOURCE_TYPE,
            source_ref=candidate_id,
            thread_id=candidate_id,
            title=subject,
            content=body_text,
        )
        db.add(item)
        db.flush()
        action = "inserted"
    else:
        item = existing
        item.title = subject
        item.content = body_text
        action = "updated"

    item.function_fragment = function_fragment
    item.scenario_label = DEFAULT_SCENARIO
    item.intent_label = DEFAULT_SCENARIO
    item.language_style = "formal_email"
    item.library_type = SEED_LIBRARY_TYPE
    item.allowed_for_generation = True
    item.usable_for_reply = True
    item.publishable = True
    # useful_score 直接复用 KB 的分数
    item.useful_score = chunk.useful_score or Decimal("0.7")
    item.topic_clarity_score = chunk.topic_clarity_score or item.useful_score
    item.completeness_score = chunk.completeness_score or item.useful_score
    item.reusability_score = chunk.reusability_score or item.useful_score
    item.evidence_reliability_score = chunk.evidence_reliability_score or item.useful_score
    item.status = "ready"
    item.source_snapshot = {
        "seed_loader_version": "v1.7.213",
        "kb_chunk_id": str(chunk.chunk_id),
        "kb_chunk_type": chunk.chunk_type,
        "kb_knowledge_type": chunk.knowledge_type,
        "kb_business_line": chunk.business_line,
        "kb_sub_service": chunk.sub_service,
        "kb_useful_score": float(chunk.useful_score) if chunk.useful_score is not None else None,
        "function_fragment": function_fragment,
        "scenario_label": DEFAULT_SCENARIO,
        "desensitized_status": "desensitized",
        "desensitized_fields": hit_fields,
        "source_loader": "seed_mail_pricing_constraint_from_kb.py",
    }
    item.quality_notes = {
        "loader": "seed_mail_pricing_constraint_from_kb.py",
        "loader_version": "v1.7.213",
        "curation_method": "kb_chunk_top_n_by_useful_score",
        "note": "话术规则类 Few-Shot. 不强匹配 scenario, 适用 3 场景的 step 3/4.",
    }
    return (action, str(item.fragment_id))


def fetch_top_constraint_chunks(db, *, top: int) -> list[KnowledgeChunk]:
    return (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.chunk_type == "constraint",
            KnowledgeChunk.status == "active",
            KnowledgeChunk.useful_score.isnot(None),
        )
        .order_by(KnowledgeChunk.useful_score.desc())
        .limit(top)
        .all()
    )


def fetch_top_quotation_chunks(db, *, top: int) -> list[KnowledgeChunk]:
    return (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.chunk_type == "rule",
            KnowledgeChunk.knowledge_type == "pricing",
            KnowledgeChunk.status == "active",
            KnowledgeChunk.useful_score.isnot(None),
        )
        .order_by(KnowledgeChunk.useful_score.desc())
        .limit(top)
        .all()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Seed email_fragment_asset with KB pricing/constraint chunks (v1.7.213)"
    )
    parser.add_argument("--top", type=int, default=10,
                        help="每类取前 N 条 (默认 10, 共 2N 条入库)")
    parser.add_argument("--clean-first", action="store_true",
                        help="跑前先 DELETE 旧 mail_pricing_constraint_seed 行")
    parser.add_argument("--dry-run", action="store_true", help="不提交事务")
    args = parser.parse_args()

    db = SessionLocal()
    inserted = 0
    updated = 0
    try:
        if args.clean_first:
            deleted = db.query(EmailFragmentAsset).filter(
                EmailFragmentAsset.source_type == SEED_SOURCE_TYPE
            ).delete(synchronize_session=False)
            print(f"[seed] --clean-first: 已删除 {deleted} 行旧 {SEED_SOURCE_TYPE}")

        constraint_chunks = fetch_top_constraint_chunks(db, top=args.top)
        print(f"[seed] 取到 {len(constraint_chunks)} 条 constraint 类切片")
        for chunk in constraint_chunks:
            action, info = upsert_kb_chunk_as_fewshot(db, chunk, "constraint")
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
            print(f"  [constraint] {action} | {chunk.business_line} | score={chunk.useful_score} | {chunk.title[:60]}")

        quotation_chunks = fetch_top_quotation_chunks(db, top=args.top)
        print(f"[seed] 取到 {len(quotation_chunks)} 条 quotation 类切片")
        for chunk in quotation_chunks:
            action, info = upsert_kb_chunk_as_fewshot(db, chunk, "quotation")
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
            print(f"  [quotation ] {action} | {chunk.business_line} | score={chunk.useful_score} | {chunk.title[:60]}")

        if args.dry_run:
            db.rollback()
            print(f"[seed] DRY-RUN 已回滚。inserted={inserted} updated={updated}")
        else:
            db.commit()
            print(f"[seed] COMMIT 完成。inserted={inserted} updated={updated}")

        from collections import Counter
        rows = db.query(EmailFragmentAsset).filter(
            EmailFragmentAsset.source_type == SEED_SOURCE_TYPE
        ).all()
        fr = Counter(r.function_fragment for r in rows)
        print(f"[seed] {SEED_SOURCE_TYPE} 共 {len(rows)} 行, function_fragment 分布: {dict(fr)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
