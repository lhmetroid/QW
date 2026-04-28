from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

from config import settings  # noqa: E402
from database import KnowledgeChunk, KnowledgeDocument, SessionLocal  # noqa: E402
from embedding_service import EmbeddingService  # noqa: E402
from knowledge_governance import infer_library_type, infer_scenario_intent, merge_tags, score_content_governance  # noqa: E402


SOURCE_FILENAME = "业务知识、业务流程、话术、案例.csv"
SOURCE_PATH = ROOT / "docs" / SOURCE_FILENAME
SOURCE_TYPE = "business_csv"
OWNER = "codex_business_csv_import"
ROW_LIMIT = 50
IMPORT_BATCH = f"business_csv_first50_{uuid.uuid4().hex[:12]}"

SKIP_ROWS = {
    29: "too_short_generic",
    48: "too_short_generic",
}

PROCESS_ROWS = {1, 2, 3}
SCRIPT_ROWS = {
    17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
    30, 31, 32, 33, 34, 35, 36, 38, 39, 40, 41, 42,
    43, 46, 47, 49, 50,
}
CAPABILITY_ROWS = {6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
EXAMPLE_ROWS = set()
ROW_OVERRIDES = {
    1: {"knowledge_class": "process", "business_line": "printing", "service_scope": "printing_general"},
    2: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_general"},
    3: {"knowledge_class": "process", "business_line": "interpretation", "service_scope": "simultaneous_interpretation"},
    4: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    5: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    6: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    7: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    8: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    9: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    10: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "technical_translation"},
    11: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    12: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "translation_general"},
    13: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    14: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    15: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    16: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    17: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    18: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    19: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    20: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    21: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    22: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    23: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    24: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    25: {"knowledge_class": "script", "business_line": "interpretation", "service_scope": "cross_sell"},
    26: {"knowledge_class": "script", "business_line": "printing", "service_scope": "cross_sell"},
    27: {"knowledge_class": "script", "business_line": "multimedia", "service_scope": "cross_sell"},
    28: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    30: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    31: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    32: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_refresh"},
    33: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    34: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    35: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    36: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    37: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    38: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    39: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    40: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    41: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    42: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    43: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    44: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    45: {"knowledge_class": "faq", "business_line": "general", "service_scope": "company_background"},
    46: {"knowledge_class": "script", "business_line": "general", "service_scope": "procurement_path"},
    47: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    49: {"knowledge_class": "script", "business_line": "general", "service_scope": "security_response"},
    50: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
}


def normalize_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalized_fingerprint(title: str, content: str) -> str:
    raw = re.sub(r"\s+", "", f"{title}|{content}")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def title_for_row(row_no: int, title: str) -> str:
    return f"业务资料{row_no:02d}·{title[:120]}"


def infer_business_line(title: str, content: str) -> str:
    text = f"{title}\n{content}"
    if any(word in text for word in ["印刷", "样本", "骑马钉", "胶装", "纸张", "打样"]):
        return "printing"
    if any(word in text for word in ["同传", "交传", "口译", "耳机", "彩排", "会议"]):
        return "interpretation"
    if any(word in text for word in ["视频", "字幕", "配音", "听写"]):
        return "multimedia"
    if any(word in text for word in ["展会", "展台", "易拉宝"]):
        return "exhibition"
    if any(word in text for word in ["礼品", "台历", "笔记本"]):
        return "gifts"
    if any(word in text for word in ["翻译", "译员", "语种", "译审", "笔译"]):
        return "translation"
    return "general"


def infer_service_scope(title: str, content: str, business_line: str) -> str | None:
    text = f"{title}\n{content}"
    if business_line == "printing":
        if "样本" in text:
            return "marketing_material"
        return "printing_general"
    if business_line == "interpretation":
        if "同传" in text:
            return "simultaneous_interpretation"
        return "interpretation_general"
    if business_line == "multimedia":
        return "video_localization"
    if business_line == "exhibition":
        return "event_marketing"
    if business_line == "gifts":
        return "promotional_gifts"
    if business_line == "translation":
        if "技术资料" in text:
            return "technical_translation"
        return "translation_general"
    return "general"


def infer_knowledge_class(row_no: int, title: str, content: str) -> str:
    override = ROW_OVERRIDES.get(row_no, {})
    if override.get("knowledge_class"):
        return override["knowledge_class"]
    if row_no in PROCESS_ROWS or "流程" in title or "流程" in content:
        return "process"
    if row_no in SCRIPT_ROWS:
        return "script"
    if row_no in EXAMPLE_ROWS or "案例" in title:
        return "example"
    if row_no in CAPABILITY_ROWS:
        return "capability"
    if title.endswith("？") or "何时成立" in title or "有哪些" in title:
        return "faq"
    return "faq"


def infer_chunk_type(knowledge_class: str) -> tuple[str, str]:
    mapping = {
        "process": ("process", "rule"),
        "capability": ("capability", "rule"),
        "example": ("faq", "example"),
        "script": ("faq", "template"),
        "faq": ("faq", "faq"),
    }
    return mapping.get(knowledge_class, ("faq", "faq"))


def risk_level_for_row(row_no: int, title: str, content: str, knowledge_class: str) -> str:
    text = f"{title}\n{content}"
    if knowledge_class == "script" and any(word in text for word in ["保密", "供应商系统", "合同", "签单"]):
        return "high"
    if any(word in text for word in ["第一", "市场份额", "最大", "95%", "70%", "100多名", "30名"]):
        return "medium"
    return "medium"


def build_tags(
    *,
    row_no: int,
    title: str,
    knowledge_class: str,
    business_line: str,
    service_scope: str | None,
) -> dict:
    scenario_label, intent_label, language_style = infer_scenario_intent(
        title=title,
        content=title,
        tags={
            "knowledge_class": knowledge_class,
            "scenario_label": "process" if knowledge_class == "process" else None,
            "intent_label": "script" if knowledge_class == "script" else None,
            "language_style": "spoken_sales" if knowledge_class == "script" else None,
        },
    )
    return {
        "knowledge_class": knowledge_class,
        "source_filename": SOURCE_FILENAME,
        "source_row": row_no,
        "row_scope": f"1-{ROW_LIMIT}",
        "dataset_kind": "business_knowledge_csv",
        "business_line_hint": business_line,
        "service_scope_hint": service_scope,
        "scenario_label": scenario_label,
        "intent_label": intent_label,
        "language_style": language_style,
    }


def strip_leading_list_marker(text: str) -> str:
    return re.sub(r"^\s*(?:\d+|[一二三四五六七八九十]+)[\.\)）．、]\s*", "", str(text or "").strip())


def split_numbered_sections(content: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in lines:
        marker = re.match(r"^(\d+[\.\)）]|[一二三四五六七八九十]+[、\.])\s*(.*)$", line)
        if marker:
            if current_lines:
                sections.append((current_title or current_lines[0][:40], current_lines))
            current_title = marker.group(2).strip() or line
            current_lines = [line]
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title or current_lines[0][:40], current_lines))
    result: list[tuple[str, str]] = []
    for section_title, section_lines in sections:
        block = "\n".join(section_lines).strip()
        if block:
            result.append((section_title[:80], block))
    return result


def split_numbered_points(
    content: str,
    *,
    title_map: dict[int, str] | None = None,
    default_title_prefix: str = "要点",
) -> list[tuple[str, str]]:
    matches = re.findall(
        r"(?:^|\n)\s*((?:\d+|[一二三四五六七八九十]+)[\.\)）．、])\s*(.*?)(?=(?:\n\s*(?:\d+|[一二三四五六七八九十]+)[\.\)）．、])|\Z)",
        content.strip(),
        flags=re.S,
    )
    chunks: list[tuple[str, str]] = []
    for idx, (_marker, body) in enumerate(matches, start=1):
        block = strip_leading_list_marker(body)
        if not block:
            continue
        title = (title_map or {}).get(idx, f"{default_title_prefix}{idx}")
        chunks.append((title, block))
    return chunks


def split_formula_example(content: str) -> list[tuple[str, str]]:
    parts = re.split(r"话术示例[:：]", content, maxsplit=1)
    if len(parts) == 2:
        formula = re.sub(r"^公式[:：]\s*", "", parts[0].strip())
        sample = parts[1].strip()
        chunks: list[tuple[str, str]] = []
        if formula:
            chunks.append(("话术公式", formula))
        if sample:
            chunks.append(("话术示例", sample))
        return chunks
    return [("话术内容", content.strip())]


def split_security_points(content: str) -> list[tuple[str, str]]:
    return split_numbered_points(
        content,
        title_map={
            1: "保密协议与长期合作承诺",
            2: "ERP 权限隔离说明",
            3: "译员与员工保密约束",
            4: "长期外企客户与零事故记录",
            5: "客户仍担心时可补签保密协议",
        },
        default_title_prefix="保密回复要点",
    ) or [("保密回复", content.strip())]


def split_capability_points(row_no: int, content: str) -> list[tuple[str, str]]:
    title_map_by_row = {
        8: {
            1: "长期合作客户背书",
            2: "可提供的一体化业务范围",
        },
        11: {
            1: "ERP 自研与长期建设",
            2: "海量语料与术语资源积累",
        },
    }
    return split_numbered_points(
        content,
        title_map=title_map_by_row.get(row_no),
        default_title_prefix="能力要点",
    )


def split_follow_up_points(row_no: int, content: str) -> list[tuple[str, str]]:
    if row_no == 41:
        points = split_numbered_points(
            content,
            title_map={
                1: "KP 基础身份信息",
                2: "需求情况确认",
            },
            default_title_prefix="跟进要点",
        )
        if len(points) >= 2 and len(points[1][1]) < 12:
            merged = f"{points[0][1]}，并同步确认{points[1][1].rstrip('。；;，,')}"
            return [("KP 基础信息与需求情况确认", merged)]
        return points
    title_map_by_row = {
        23: {
            1: "企微邀请留档",
            2: "邮件资料与转介绍请求",
        },
        42: {
            1: "未来需求探询",
            2: "过往需求回溯",
        },
    }
    return split_numbered_points(
        content,
        title_map=title_map_by_row.get(row_no),
        default_title_prefix="跟进要点",
    )


def build_chunks(row_no: int, title: str, content: str, knowledge_class: str) -> list[dict]:
    override = ROW_OVERRIDES.get(row_no, {})
    business_line = override.get("business_line") or infer_business_line(title, content)
    service_scope = override.get("service_scope") or infer_service_scope(title, content, business_line)
    risk_level = risk_level_for_row(row_no, title, content, knowledge_class)
    tags = build_tags(
        row_no=row_no,
        title=title,
        knowledge_class=knowledge_class,
        business_line=business_line,
        service_scope=service_scope,
    )
    knowledge_type, chunk_type = infer_chunk_type(knowledge_class)

    raw_chunks: list[tuple[str, str]] = []
    if knowledge_class == "process":
        raw_chunks = split_numbered_sections(content)
    elif row_no in {8, 11}:
        raw_chunks = split_capability_points(row_no, content)
    elif row_no in {24, 25, 26, 27}:
        raw_chunks = split_formula_example(content)
    elif row_no == 49:
        raw_chunks = split_security_points(content)
    elif row_no in {23, 41, 42}:
        raw_chunks = split_follow_up_points(row_no, content)
    else:
        raw_chunks = [(title, content)]

    chunks: list[dict] = []
    for idx, (chunk_title, chunk_content) in enumerate(raw_chunks, start=1):
        chunk_content = normalize_text(chunk_content)
        if len(chunk_content) < 12:
            continue
        chunk_tags = merge_tags(tags, chunk_index=idx)
        chunks.append(
            {
                "title": f"{title[:80]} · {chunk_title[:80]}" if len(raw_chunks) > 1 else title,
                "content": chunk_content,
                "knowledge_type": knowledge_type,
                "chunk_type": chunk_type,
                "knowledge_class": knowledge_class,
                "business_line": business_line,
                "service_scope": service_scope,
                "risk_level": risk_level,
                "priority": 78 if knowledge_class == "script" else 72 if knowledge_class == "process" else 68,
                "tags": chunk_tags,
            }
        )
    return chunks


def purge_existing(db, *, row_limit: int) -> dict:
    doc_count = 0
    chunk_count = 0
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_type == SOURCE_TYPE).all()
    for doc in docs:
        meta = dict(doc.source_meta or {})
        row_no = meta.get("source_row") or meta.get("row")
        filename = str(meta.get("source_filename") or meta.get("filename") or "").strip()
        if filename == SOURCE_FILENAME and isinstance(row_no, int) and 1 <= row_no <= row_limit:
            chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).all()
            for chunk in chunks:
                db.delete(chunk)
                chunk_count += 1
            db.delete(doc)
            doc_count += 1
    db.flush()
    return {"deleted_documents": doc_count, "deleted_chunks": chunk_count}


def apply_chunk_governance(chunk: KnowledgeChunk, *, source_ref: str) -> dict:
    tags = dict(chunk.structured_tags or {})
    quality = score_content_governance(
        title=chunk.title,
        content=chunk.content,
        knowledge_type=chunk.knowledge_type,
        chunk_type=chunk.chunk_type,
        source_type=SOURCE_TYPE,
        tags=tags,
        has_source_ref=bool(source_ref),
        metadata={
            "business_line": chunk.business_line,
            "service_scope": chunk.service_scope,
            "customer_tier": chunk.customer_tier,
            "language_pair": chunk.language_pair,
        },
    )
    chunk.library_type = quality["library_type"]
    chunk.allowed_for_generation = bool(quality["allowed_for_generation"])
    chunk.usable_for_reply = bool(quality["usable_for_reply"])
    chunk.publishable = bool(quality["publishable"])
    chunk.topic_clarity_score = Decimal(str(quality["topic_clarity_score"]))
    chunk.completeness_score = Decimal(str(quality["completeness_score"]))
    chunk.reusability_score = Decimal(str(quality["reusability_score"]))
    chunk.evidence_reliability_score = Decimal(str(quality["evidence_reliability_score"]))
    chunk.useful_score = Decimal(str(quality["useful_score"]))
    return quality


def create_document(db, *, row_no: int, title: str, content: str, chunks_payload: list[dict]) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    primary = chunks_payload[0]
    source_ref = f"{SOURCE_FILENAME}:row:{row_no}"
    doc_tags = merge_tags(
        primary["tags"],
        chunk_count=len(chunks_payload),
        source_ref=source_ref,
    )
    document = KnowledgeDocument(
        title=title_for_row(row_no, title),
        knowledge_type=primary["knowledge_type"],
        business_line=primary["business_line"],
        sub_service=None,
        source_type=SOURCE_TYPE,
        source_ref=source_ref,
        source_meta={
            "source_filename": SOURCE_FILENAME,
            "source_row": row_no,
            "original_title": title,
            "original_content_length": len(content),
            "row_limit": ROW_LIMIT,
            "chunk_count": len(chunks_payload),
        },
        status="review",
        owner=OWNER,
        import_batch=IMPORT_BATCH,
        risk_level=primary["risk_level"],
        review_required=True,
        review_status="in_review",
        library_type=infer_library_type(
            source_type=SOURCE_TYPE,
            knowledge_type=primary["knowledge_type"],
            chunk_type=primary["chunk_type"],
            tags=doc_tags,
        ),
        tags=doc_tags,
    )
    db.add(document)
    db.flush()

    chunks: list[KnowledgeChunk] = []
    for idx, payload in enumerate(chunks_payload, start=1):
        embedding = EmbeddingService.embed(f"{payload['title']}\n{payload['content']}")
        if not embedding:
            raise RuntimeError(f"embedding_failed row={row_no} chunk={idx}")
        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=idx,
            chunk_type=payload["chunk_type"],
            title=payload["title"][:255],
            content=payload["content"],
            keyword_text=f"{payload['title']}\n{payload['content']}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER if embedding else None,
            embedding_model=settings.EMBEDDING_MODEL if embedding else None,
            embedding_dim=len(embedding),
            priority=payload["priority"],
            retrieval_weight=Decimal("1.000"),
            business_line=payload["business_line"],
            sub_service=None,
            knowledge_type=payload["knowledge_type"],
            language_pair=None,
            service_scope=payload["service_scope"],
            region=None,
            customer_tier=None,
            structured_tags=payload["tags"],
            status="review",
        )
        db.add(chunk)
        db.flush()
        quality = apply_chunk_governance(chunk, source_ref=source_ref)
        document.library_type = chunk.library_type
        document.tags = merge_tags(document.tags, library_type=document.library_type)
        if quality["function_fragment"]:
            chunk.structured_tags = merge_tags(chunk.structured_tags, function_fragment=quality["function_fragment"])
        chunks.append(chunk)
    return document, chunks


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(SOURCE_PATH)
    db = SessionLocal()
    created_documents = 0
    created_chunks = 0
    skipped: list[dict] = []
    imported: list[dict] = []
    seen_hashes: dict[str, int] = {}
    try:
        purged = purge_existing(db, row_limit=ROW_LIMIT)
        with SOURCE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row_no, row in enumerate(reader, start=1):
                if row_no > ROW_LIMIT:
                    break
                title = normalize_text(row[0] if len(row) > 0 else "")
                content = normalize_text(row[1] if len(row) > 1 else "")
                if row_no in SKIP_ROWS:
                    skipped.append({"row": row_no, "title": title, "reason": SKIP_ROWS[row_no]})
                    continue
                if not title or not content:
                    skipped.append({"row": row_no, "title": title, "reason": "empty_title_or_content"})
                    continue
                fingerprint = normalized_fingerprint(title, content)
                if fingerprint in seen_hashes:
                    skipped.append({"row": row_no, "title": title, "reason": f"duplicate_of_row_{seen_hashes[fingerprint]}"})
                    continue
                seen_hashes[fingerprint] = row_no
                knowledge_class = infer_knowledge_class(row_no, title, content)
                chunks_payload = build_chunks(row_no, title, content, knowledge_class)
                if not chunks_payload:
                    skipped.append({"row": row_no, "title": title, "reason": "no_valid_chunks"})
                    continue
                document, chunks = create_document(db, row_no=row_no, title=title, content=content, chunks_payload=chunks_payload)
                created_documents += 1
                created_chunks += len(chunks)
                imported.append(
                    {
                        "row": row_no,
                        "title": title,
                        "document_id": str(document.document_id),
                        "knowledge_class": knowledge_class,
                        "business_line": chunks_payload[0]["business_line"],
                        "chunk_count": len(chunks),
                    }
                )
        db.commit()
        print(
            json.dumps(
                {
                    "status": "success",
                    "source_file": str(SOURCE_PATH),
                    "import_batch": IMPORT_BATCH,
                    "created_documents": created_documents,
                    "created_chunks": created_chunks,
                    "skipped_count": len(skipped),
                    "purged": purged,
                    "imported": imported,
                    "skipped": skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
