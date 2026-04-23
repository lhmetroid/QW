from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta

from database import KnowledgeChunk, KnowledgeDocument, KnowledgeHitLog, SessionLocal
from embedding_service import EmbeddingService
from intent_engine import IntentEngine


def create_active_chunk(
    db,
    *,
    title: str,
    content: str,
    knowledge_class: str,
    knowledge_type: str,
    chunk_type: str,
    business_line: str,
    priority: int,
    risk_level: str,
    source_ref: str,
):
    effective_from = datetime.now() - timedelta(days=1)
    effective_to = datetime.now() + timedelta(days=30)
    embedding = EmbeddingService.embed(f"{title}\n{content}")
    if not embedding:
        raise RuntimeError(f"Embedding failed for: {title}")
    document = KnowledgeDocument(
        title=title,
        knowledge_type=knowledge_type,
        business_line=business_line,
        source_type="verification",
        source_ref=source_ref,
        status="active",
        version_no=1,
        effective_from=effective_from,
        effective_to=effective_to,
        owner="kb_verify_v1742",
        risk_level=risk_level,
        review_required=False,
        review_status="approved",
        tags={"knowledge_class": knowledge_class, "verification_run": source_ref},
    )
    db.add(document)
    db.flush()
    chunk = KnowledgeChunk(
        document_id=document.document_id,
        chunk_no=1,
        chunk_type=chunk_type,
        title=title,
        content=content,
        keyword_text=f"{title}\n{content}",
        embedding=embedding,
        embedding_provider="verification",
        embedding_model="verification",
        embedding_dim=len(embedding),
        priority=priority,
        business_line=business_line,
        knowledge_type=knowledge_type,
        structured_tags={"knowledge_class": knowledge_class, "verification_run": source_ref},
        status="active",
        effective_from=effective_from,
        effective_to=effective_to,
    )
    db.add(chunk)
    db.flush()
    return str(document.document_id), str(chunk.chunk_id)


def main() -> int:
    run_id = f"kb_verify_v1742_{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    created_document_ids: list[str] = []
    created_chunk_ids: list[str] = []
    request_ids: list[str] = []
    try:
        fixtures = [
            {
                "title": "同传",
                "content": "同传是同步传译，指发言进行时译员几乎同步输出译文的口译服务。",
                "knowledge_class": "definition",
                "knowledge_type": "faq",
                "chunk_type": "definition",
                "business_line": "interpretation",
                "priority": 60,
                "risk_level": "low",
            },
            {
                "title": "同传耳机配置规则",
                "content": "同传耳机数量应按现场听众人数、语言通道和备用比例综合配置，先确认参会人数，再按流程准备设备清单。",
                "knowledge_class": "process",
                "knowledge_type": "process",
                "chunk_type": "rule",
                "business_line": "interpretation",
                "priority": 95,
                "risk_level": "medium",
            },
            {
                "title": "嘉赛",
                "content": "嘉赛是事必达的公司简称和品牌别名，客户提到嘉赛时应归一理解为事必达。",
                "knowledge_class": "definition",
                "knowledge_type": "faq",
                "chunk_type": "definition",
                "business_line": "interpretation",
                "priority": 55,
                "risk_level": "low",
            },
            {
                "title": "事必达法语同传能力",
                "content": "事必达可提供法语同传服务，支持会前需求确认、译员协调和现场执行。",
                "knowledge_class": "capability",
                "knowledge_type": "capability",
                "chunk_type": "rule",
                "business_line": "interpretation",
                "priority": 98,
                "risk_level": "medium",
            },
        ]

        for item in fixtures:
            document_id, chunk_id = create_active_chunk(db, source_ref=run_id, **item)
            created_document_ids.append(document_id)
            created_chunk_ids.append(chunk_id)
        db.commit()

        checks = [
            {
                "name": "definition_query_prefers_definition",
                "query_text": "同传是什么",
                "query_features": {"business_line": "interpretation", "knowledge_type": ["faq", "process", "capability"]},
                "expect_top_class": "definition",
            },
            {
                "name": "business_query_demotes_definition",
                "query_text": "同传耳机应该怎么配",
                "query_features": {"business_line": "interpretation", "knowledge_type": ["faq", "process", "capability"]},
                "expect_top_class": "process",
                "expect_top_not_definition": True,
            },
            {
                "name": "alias_query_normalizes_to_capability",
                "query_text": "嘉赛能做法语同传吗",
                "query_features": {"business_line": "interpretation", "knowledge_type": ["faq", "capability"]},
                "expect_top_class": "capability",
                "expect_normalized_contains": "事必达",
            },
            {
                "name": "alias_definition_query_still_hits_definition",
                "query_text": "嘉赛是什么意思",
                "query_features": {"business_line": "interpretation", "knowledge_type": ["faq", "capability"]},
                "expect_top_class": "definition",
                "expect_normalized_contains": "事必达",
            },
        ]

        results = []
        failures = []
        for index, check in enumerate(checks, start=1):
            request_id = f"{run_id}_{index}"
            request_ids.append(request_id)
            result = IntentEngine.retrieve_knowledge_v2(
                query_text=check["query_text"],
                query_features=check["query_features"],
                top_k=5,
                request_id=request_id,
                session_id=run_id,
            )
            hits = result.get("hits") or []
            top_hit = hits[0] if hits else {}
            top_class = top_hit.get("knowledge_class")
            normalized_query_text = (result.get("filters_used") or {}).get("normalized_query_text", "")
            check_failures = []
            if check.get("expect_top_class") and top_class != check["expect_top_class"]:
                check_failures.append(f"top knowledge_class expected {check['expect_top_class']} but got {top_class}")
            if check.get("expect_top_not_definition") and top_class == "definition":
                check_failures.append("business query was still topped by definition")
            expected_term = check.get("expect_normalized_contains")
            if expected_term and expected_term not in normalized_query_text:
                check_failures.append(f"normalized_query_text missing {expected_term}")
            if not hits:
                check_failures.append("no hits returned")
            results.append(
                {
                    "name": check["name"],
                    "query_text": check["query_text"],
                    "normalized_query_text": normalized_query_text,
                    "top_hit": {
                        "title": top_hit.get("title"),
                        "knowledge_class": top_class,
                        "knowledge_type": top_hit.get("knowledge_type"),
                        "score": top_hit.get("score"),
                    },
                    "passed": not check_failures,
                    "failures": check_failures,
                }
            )
            failures.extend([f"{check['name']}: {item}" for item in check_failures])

        print(
            json.dumps(
                {
                    "status": "success" if not failures else "failed",
                    "run_id": run_id,
                    "fixture_count": len(fixtures),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not failures else 1
    finally:
        try:
            if created_chunk_ids:
                db.query(KnowledgeChunk).filter(KnowledgeChunk.chunk_id.in_(created_chunk_ids)).delete(synchronize_session=False)
            if created_document_ids:
                db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id.in_(created_document_ids)).delete(synchronize_session=False)
            if request_ids:
                db.query(KnowledgeHitLog).filter(KnowledgeHitLog.request_id.in_(request_ids)).delete(synchronize_session=False)
            db.commit()
        except Exception as cleanup_error:
            db.rollback()
            print(json.dumps({"cleanup_error": str(cleanup_error), "run_id": run_id}, ensure_ascii=False), file=sys.stderr)
        finally:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
