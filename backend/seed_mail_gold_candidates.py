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
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED_JSON = REPO_ROOT / "docs" / "mail_gold_candidates" / "latest_mail_gold_candidates.json"

sys.path.insert(0, str(REPO_ROOT / "backend"))

from database import EmailFragmentAsset, SessionLocal  # noqa: E402

SEED_SOURCE_TYPE = "mail_gold_seed"
SEED_LIBRARY_TYPE = "gold_seed"


VALID_FRAGMENTS = {"greetings", "example", "process", "constraint", "quotation"}
VALID_SCENARIOS = {"re_activation", "new_business_promotion", "new_contact_intro"}


def _require_decimal(value, field: str, candidate_id: str) -> Decimal:
    # v1.7.208 "宁报错不兜底" — 缺字段或非法值直接 raise, 不再 default '0.0' 兜底.
    if value is None:
        raise ValueError(f"candidate {candidate_id} 缺 {field} 字段（v1.7.209 不再 default 兜底）")
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except Exception as exc:
        raise ValueError(f"candidate {candidate_id} 的 {field}={value!r} 不是合法 Decimal: {exc}") from exc


def upsert_seed(db, candidate: dict, idx: int) -> tuple[str, str]:
    """返回 (action, fragment_id_str)，action 取值 inserted / updated。v1.7.209 不再 skip — 缺字段直接 raise。"""
    candidate_id = (candidate.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError(f"row#{idx} 缺 candidate_id（v1.7.209 不再 skip, 直接 raise）")

    body_text = (candidate.get("body_text") or "").strip()
    if not body_text:
        raise ValueError(f"{candidate_id} body_text 为空（v1.7.209 不再 skip）")

    subject = (candidate.get("subject") or "").strip()
    if not subject:
        raise ValueError(f"{candidate_id} subject 为空（v1.7.209 不再用 candidate_id 兜底）")
    subject = subject[:255]

    scenario = (candidate.get("scenario") or "").strip()
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"{candidate_id} scenario={scenario!r} 不在 {VALID_SCENARIOS}（v1.7.209 不再放任）")

    function_fragment = (candidate.get("function_fragment") or "").strip()
    if function_fragment not in VALID_FRAGMENTS:
        raise ValueError(f"{candidate_id} function_fragment={function_fragment!r} 不在 {VALID_FRAGMENTS}")

    useful_score = _require_decimal(candidate.get("useful_score"), "useful_score", candidate_id)

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

    # v1.7.209: 真实分类而非写死
    item.function_fragment = function_fragment
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
        "seed_loader_version": "v1.7.209",
        "seed_source_file": str(DEFAULT_SEED_JSON.relative_to(REPO_ROOT)),
        "candidate_rank": candidate.get("rank"),
        "candidate_id": candidate_id,
        "source_ref": candidate.get("source_ref"),
        "scenario": scenario,
        "scenario_label_cn": candidate.get("scenario_label_cn"),
        "function_fragment": function_fragment,
        "function_fragment_label_cn": candidate.get("function_fragment_label_cn"),
        "desensitized_status": candidate.get("desensitized_status"),
        "desensitized_fields": candidate.get("desensitized_fields") or [],
        "useful_score": float(useful_score),
        "score_source": candidate.get("score_source"),
        "csv_source_file": candidate.get("csv_source_file"),
        "email_stage": candidate.get("email_stage"),
    }
    item.quality_notes = {
        "loader": "seed_mail_gold_candidates.py",
        "loader_version": "v1.7.209",
        "curation_method": "manual_classification_from_csv",
    }
    return (action, str(item.fragment_id))


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
            action, info = upsert_seed(db, candidate, idx)
            if action == "inserted":
                inserted += 1
                print(f"  [{idx:02d}] inserted  {info}  | {candidate.get('candidate_id')}  "
                      f"scenario={candidate.get('scenario')}  fragment={candidate.get('function_fragment')}")
            elif action == "updated":
                updated += 1
                print(f"  [{idx:02d}] updated   {info}  | {candidate.get('candidate_id')}  "
                      f"scenario={candidate.get('scenario')}  fragment={candidate.get('function_fragment')}")

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
