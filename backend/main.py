from fastapi import FastAPI, Request, BackgroundTasks, Query, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
import os
import logging
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from sqlalchemy.orm import Session
from pydantic import BaseModel
from config import settings
from logging_config import setup_logging
setup_logging()
from qywx_utils import QYWXUtils
from intent_engine import IntentEngine
from embedding_service import EmbeddingService
from database import (
    SessionLocal, MessageLog, init_db, KnowledgeBase, IntentSummary, get_db,
    KnowledgeDocument, KnowledgeChunk, PricingRule
)

app = FastAPI(title="企微智能实时提醒后台")
logger = logging.getLogger(__name__)

from callback import router as callback_router
app.include_router(callback_router)

from crm_profile import router as crm_profile_router
app.include_router(crm_profile_router)

# 挂载前端静态文件
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path, html=True), name="static")

# 初始化数据库结构
def auto_patch_db():
    from sqlalchemy import text
    try:
        init_db() # 基础建表
        db = SessionLocal()
        # 强制补丁：为旧表增加 is_mock 列
        db.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS is_mock BOOLEAN DEFAULT FALSE;"))
        db.commit()
        db.close()
        logger.info("数据库 Schema 自动检查/修复完成")
    except Exception as e:
        logger.error(f"数据库补丁执行异常 (可能由于已存在): {e}")

auto_patch_db()

import asyncio
from archive_service import ArchiveService

@app.on_event("startup")
async def startup_event():
    logger.info("🔄 启动本地 20秒 异步抗阻塞定时刷盘时钟 (兼顾 Webhook 失效或本地未连通公网情况)")
    async def background_poll_worker():
        while True:
            try:
                # 使用 to_thread 将底层 C-SDK 同步阻塞(10秒超时网络I/O) 推到独立线程池，绝不卡死 FastAPI 主服务
                await asyncio.to_thread(ArchiveService.sync_today_data)
            except Exception as e:
                logger.error(f"⚠️ 自动轮询线程异常: {e}")
            await asyncio.sleep(20)
    
    asyncio.create_task(background_poll_worker())

@app.get("/cb/qywx")
async def qywx_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...)
):
    """企微回调开启时的 URL 验证接口"""
    logger.info(f"收到企微验证请求")
    res = QYWXUtils.decrypt_message(msg_signature, timestamp, nonce, echostr, is_verify=True)
    return res

@app.post("/cb/qywx")
async def qywx_receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...)
):
    """企微回调消息接收接口"""
    body = await request.body()
    xml_content = QYWXUtils.decrypt_message(msg_signature, timestamp, nonce, body, is_verify=False)
    if not xml_content:
        raise HTTPException(status_code=400, detail="Decrypt failed")
    
    # 此处省略 XML 解析逻辑，直接模拟
    from_user = "mock_user" 
    content = "测试消息内容" 
    
    # 1. 实时旁路扫描 (主线程)
    IntentEngine.fast_track_scan(from_user, content)
    
    # 2. 异步深度分析 (改用原生 BackgroundTasks 以适配 Windows)
    background_tasks.add_task(process_deep_analyze_task, from_user, content, "customer")
    
    return "success"

def process_deep_analyze_task(user_id, content, sender_type):
    """后台长对话分析任务"""
    db = SessionLocal()
    try:
        # 消息持久化
        log = MessageLog(user_id=user_id, content=content, sender_type=sender_type)
        db.add(log)
        db.commit()
        
        # 获取上下文
        context_logs = db.query(MessageLog).filter(MessageLog.user_id == user_id).order_by(MessageLog.id.desc()).limit(10).all()
        context = [{"content": l.content, "sender_type": l.sender_type} for l in reversed(context_logs)]
        
        # 执行 AI 分析链路
        IntentEngine.slow_track_analyze(user_id, context)
    finally:
        db.close()

# --- 知识库管理 API ---

@app.post("/api/knowledge")
async def add_knowledge(title: str, content: str, category: str = "通用"):
    embedding = IntentEngine.get_embedding(content)
    if not embedding:
        raise HTTPException(status_code=500, detail="Embedding failed")
    
    db = SessionLocal()
    try:
        new_item = KnowledgeBase(title=title, content=content, category=category, embedding=embedding)
        db.add(new_item)
        db.commit()
        return {"status": "success", "id": new_item.id}
    finally:
        db.close()

@app.get("/api/knowledge")
async def list_knowledge():
    db = SessionLocal()
    try:
        items = db.query(KnowledgeBase.id, KnowledgeBase.title, KnowledgeBase.category).all()
        return [{"id": i.id, "title": i.title, "category": i.category} for i in items]
    finally:
        db.close()

# --- 知识库 V2 治理 API：仅负责知识入库、审核状态和证据管理 ---

class KnowledgeManualCreate(BaseModel):
    title: str
    content: str
    knowledge_type: str = "faq"
    business_line: str = "general"
    sub_service: str | None = None
    chunk_type: str = "rule"
    language_pair: str | None = None
    service_scope: str | None = None
    region: str | None = None
    customer_tier: str | None = None
    source_type: str = "manual"
    source_ref: str | None = None
    owner: str | None = None
    priority: int = 50
    risk_level: str = "medium"
    review_required: bool = True
    tags: dict | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    pricing_rule: dict | None = None

class KnowledgeRetrieveRequest(BaseModel):
    query_text: str
    query_features: dict | None = None
    top_k: int = 5
    request_id: str | None = None
    session_id: str | None = None

class KnowledgeChunkCreate(BaseModel):
    title: str
    content: str
    knowledge_type: str = "faq"
    chunk_type: str = "rule"
    business_line: str = "general"
    sub_service: str | None = None
    language_pair: str | None = None
    service_scope: str | None = None
    region: str | None = None
    customer_tier: str | None = None
    priority: int = 50
    tags: dict | None = None
    pricing_rule: dict | None = None

class KnowledgeMultiChunkCreate(BaseModel):
    title: str
    knowledge_type: str = "faq"
    business_line: str = "general"
    sub_service: str | None = None
    source_type: str = "manual"
    source_ref: str | None = None
    owner: str | None = None
    risk_level: str = "medium"
    review_required: bool = True
    tags: dict | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    chunks: list[KnowledgeChunkCreate]

class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = None
    knowledge_type: str | None = None
    business_line: str | None = None
    sub_service: str | None = None
    risk_level: str | None = None
    review_required: bool | None = None
    tags: dict | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None

class KnowledgeChunkUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    chunk_type: str | None = None
    knowledge_type: str | None = None
    business_line: str | None = None
    sub_service: str | None = None
    language_pair: str | None = None
    service_scope: str | None = None
    region: str | None = None
    customer_tier: str | None = None
    priority: int | None = None
    structured_tags: dict | None = None

class KnowledgeAssistTextImport(BaseModel):
    title: str
    content: str
    business_line: str = "general"
    source_type: str = "manual_text"
    source_ref: str | None = None
    owner: str | None = None

class KnowledgeBulkAction(BaseModel):
    document_ids: list[str]

class PricingRulePayload(BaseModel):
    business_line: str | None = None
    sub_service: str | None = None
    language_pair: str | None = None
    service_scope: str | None = None
    unit: str = "per_1000_chars"
    currency: str = "CNY"
    price_min: float | str | None = None
    price_max: float | str | None = None
    urgent_multiplier: float | str | None = None
    tax_policy: str | None = None
    min_charge: float | str | None = None
    customer_tier: str | None = None
    region: str | None = None
    source_ref: str | None = None

KB_LABELS = {
    "business_line": {
        "general": "通用",
        "translation": "翻译",
        "printing": "印刷",
        "exhibition": "展台/展会",
    },
    "knowledge_type": {
        "capability": "能力知识",
        "pricing": "报价知识",
        "process": "流程知识",
        "faq": "常见问答",
    },
    "status": {
        "draft": "草稿",
        "review": "审核中",
        "active": "已发布",
        "archived": "已归档",
        "rejected": "已驳回",
    },
    "review_status": {
        "pending": "待审核",
        "in_review": "审核中",
        "approved": "审核通过",
        "rejected": "审核驳回",
        "rolled_back": "已回滚",
        "auto_ready": "自动就绪",
    },
    "risk_level": {
        "low": "低",
        "medium": "中",
        "high": "高",
    },
    "language_pair": {
        "en->fr": "英译法",
        "en->zh": "英译中",
        "zh->en": "中译英",
        "en->ru": "英译俄",
        "ja->zh": "日译中",
        "ko->zh": "韩译中",
    },
    "service_scope": {
        "general": "普通资料",
        "medical": "医学资料",
        "legal": "法律资料",
        "technical": "技术资料",
        "financial": "财务/金融资料",
        "marketing": "市场宣传资料",
        "certified": "认证/盖章文件",
        "confidential": "保密资料",
    },
    "customer_tier": {
        "common": "普通客户",
        "key": "重点客户",
        "strategic": "战略客户",
        "vip": "VIP客户",
    },
    "chunk_type": {
        "rule": "规则",
        "faq": "FAQ",
        "example": "案例",
        "template": "模板",
        "constraint": "限制条件",
        "definition": "定义",
    },
    "intent_type": {
        "pricing": "报价咨询",
        "capability": "能力咨询",
        "process": "流程咨询",
        "faq": "常见问题",
    },
}

def label_for(dict_type: str, code: str | None) -> str | None:
    if code is None:
        return None
    return KB_LABELS.get(dict_type, {}).get(code, code)

def normalize_code(dict_type: str, value):
    if value is None:
        return None, None
    code = str(value).strip()
    if not code:
        return None, None
    if code in KB_LABELS.get(dict_type, {}):
        return code, None
    return None, code

def infer_faq_business_line(title: str, content: str) -> str:
    text = f"{title or ''}\n{content or ''}"
    if any(word in text for word in ["翻译需求", "口译需求", "同传需求", "语种需求"]):
        return "translation"
    general_words = ["公司", "身份", "哪位", "没听说", "业务范围", "服务范围"]
    business_hits = sum(1 for word in ["翻译", "口译", "同传", "字幕", "配音", "语种", "印刷", "画册", "易拉宝", "样本", "手册", "展台", "展会", "搭建", "撤展"] if word in text)
    if any(word in text for word in general_words) and business_hits >= 2:
        return "general"
    if any(word in text for word in ["印刷", "画册", "易拉宝", "样本", "手册"]):
        return "printing"
    if any(word in text for word in ["展台", "展会", "搭建", "撤展"]):
        return "exhibition"
    if any(word in text for word in ["翻译", "口译", "同传", "字幕", "配音", "语种"]):
        return "translation"
    return "general"

def infer_faq_risk_level(title: str, content: str) -> str:
    text = f"{title or ''}\n{content or ''}"
    high_words = ["报价", "价格", "收费", "费用", "折扣", "合同", "赔付", "保证", "承诺", "税", "发票"]
    return "high" if any(word in text for word in high_words) else "medium"

def normalize_header(value) -> str:
    return str(value or "").strip().replace(" ", "").replace("\n", "")

def find_column_index(headers: list, candidates: list[str]) -> int | None:
    normalized = [normalize_header(h) for h in headers]
    for candidate in candidates:
        target = normalize_header(candidate)
        if target in normalized:
            return normalized.index(target)
    return None

def _doc_to_dict(doc: KnowledgeDocument) -> dict:
    return {
        "document_id": str(doc.document_id),
        "title": doc.title,
        "knowledge_type": doc.knowledge_type,
        "knowledge_type_label": label_for("knowledge_type", doc.knowledge_type),
        "business_line": doc.business_line,
        "business_line_label": label_for("business_line", doc.business_line),
        "sub_service": doc.sub_service,
        "source_type": doc.source_type,
        "source_ref": doc.source_ref,
        "source_meta": doc.source_meta,
        "status": doc.status,
        "status_label": label_for("status", doc.status),
        "version_no": doc.version_no,
        "effective_from": doc.effective_from,
        "effective_to": doc.effective_to,
        "owner": doc.owner,
        "import_batch": doc.import_batch,
        "risk_level": doc.risk_level,
        "risk_level_label": label_for("risk_level", doc.risk_level),
        "review_required": doc.review_required,
        "review_status": doc.review_status,
        "review_status_label": label_for("review_status", doc.review_status),
        "tags": doc.tags,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }

def _chunk_to_dict(chunk: KnowledgeChunk) -> dict:
    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "chunk_no": chunk.chunk_no,
        "chunk_type": chunk.chunk_type,
        "title": chunk.title,
        "content": chunk.content,
        "business_line": chunk.business_line,
        "business_line_label": label_for("business_line", chunk.business_line),
        "sub_service": chunk.sub_service,
        "knowledge_type": chunk.knowledge_type,
        "knowledge_type_label": label_for("knowledge_type", chunk.knowledge_type),
        "language_pair": chunk.language_pair,
        "language_pair_label": label_for("language_pair", chunk.language_pair),
        "service_scope": chunk.service_scope,
        "service_scope_label": label_for("service_scope", chunk.service_scope),
        "region": chunk.region,
        "customer_tier": chunk.customer_tier,
        "customer_tier_label": label_for("customer_tier", chunk.customer_tier),
        "priority": chunk.priority,
        "structured_tags": chunk.structured_tags,
        "effective_from": chunk.effective_from,
        "effective_to": chunk.effective_to,
        "status": chunk.status,
        "status_label": label_for("status", chunk.status),
        "embedding_provider": chunk.embedding_provider,
        "embedding_model": chunk.embedding_model,
        "embedding_dim": chunk.embedding_dim,
        "created_at": chunk.created_at,
        "updated_at": chunk.updated_at,
    }

def _decimal_or_none(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail=f"Invalid decimal value: {value}")

def _pricing_rule_to_dict(rule: PricingRule) -> dict:
    return {
        "rule_id": str(rule.rule_id),
        "document_id": str(rule.document_id),
        "chunk_id": str(rule.chunk_id) if rule.chunk_id else None,
        "business_line": rule.business_line,
        "business_line_label": label_for("business_line", rule.business_line),
        "sub_service": rule.sub_service,
        "language_pair": rule.language_pair,
        "language_pair_label": label_for("language_pair", rule.language_pair),
        "service_scope": rule.service_scope,
        "service_scope_label": label_for("service_scope", rule.service_scope),
        "unit": rule.unit,
        "currency": rule.currency,
        "price_min": float(rule.price_min) if rule.price_min is not None else None,
        "price_max": float(rule.price_max) if rule.price_max is not None else None,
        "urgent_multiplier": float(rule.urgent_multiplier) if rule.urgent_multiplier is not None else None,
        "tax_policy": rule.tax_policy,
        "min_charge": float(rule.min_charge) if rule.min_charge is not None else None,
        "customer_tier": rule.customer_tier,
        "customer_tier_label": label_for("customer_tier", rule.customer_tier),
        "region": rule.region,
        "status": rule.status,
        "status_label": label_for("status", rule.status),
        "effective_from": rule.effective_from,
        "effective_to": rule.effective_to,
        "version_no": rule.version_no,
        "source_ref": rule.source_ref,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }

def _create_pricing_rule(
    db: Session,
    document: KnowledgeDocument,
    chunk: KnowledgeChunk | None,
    payload: dict | PricingRulePayload | None,
):
    if not payload:
        return None
    rule_payload = payload if isinstance(payload, PricingRulePayload) else PricingRulePayload(**payload)
    rule = PricingRule(
        document_id=document.document_id,
        chunk_id=chunk.chunk_id if chunk else None,
        business_line=rule_payload.business_line or (chunk.business_line if chunk else document.business_line),
        sub_service=rule_payload.sub_service or (chunk.sub_service if chunk else document.sub_service),
        language_pair=rule_payload.language_pair or (chunk.language_pair if chunk else None),
        service_scope=rule_payload.service_scope or (chunk.service_scope if chunk else None),
        unit=rule_payload.unit,
        currency=rule_payload.currency,
        price_min=_decimal_or_none(rule_payload.price_min),
        price_max=_decimal_or_none(rule_payload.price_max),
        urgent_multiplier=_decimal_or_none(rule_payload.urgent_multiplier),
        tax_policy=rule_payload.tax_policy,
        min_charge=_decimal_or_none(rule_payload.min_charge),
        customer_tier=rule_payload.customer_tier or (chunk.customer_tier if chunk else None),
        region=rule_payload.region or (chunk.region if chunk else None),
        status=document.status,
        effective_from=document.effective_from,
        effective_to=document.effective_to,
        version_no=document.version_no,
        source_ref=rule_payload.source_ref or document.source_ref,
    )
    db.add(rule)
    return rule

def _sync_related_status(db: Session, doc: KnowledgeDocument, status: str, review_status: str | None = None):
    doc.status = status
    if review_status:
        doc.review_status = review_status
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).all()
    for chunk in chunks:
        chunk.status = status
        chunk.effective_from = doc.effective_from
        chunk.effective_to = doc.effective_to
    pricing_rules = db.query(PricingRule).filter(PricingRule.document_id == doc.document_id).all()
    for rule in pricing_rules:
        rule.status = status
        rule.effective_from = doc.effective_from
        rule.effective_to = doc.effective_to
        rule.version_no = doc.version_no
    return len(chunks), len(pricing_rules)

@app.post("/api/kb/documents/manual")
async def create_manual_knowledge(payload: KnowledgeManualCreate, db: Session = Depends(get_db)):
    """手工新增一条知识，默认进入 draft，不直接发布。"""
    embedding_text = f"{payload.title}\n{payload.content}"
    embedding = EmbeddingService.embed(embedding_text)
    if not embedding:
        raise HTTPException(status_code=500, detail="Embedding failed")

    now_status = "draft"
    document = KnowledgeDocument(
        title=payload.title,
        knowledge_type=payload.knowledge_type,
        business_line=payload.business_line,
        sub_service=payload.sub_service,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        status=now_status,
        owner=payload.owner,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        risk_level=payload.risk_level,
        review_required=payload.review_required,
        review_status="pending" if payload.review_required else "auto_ready",
        tags=payload.tags,
    )
    db.add(document)
    db.flush()

    chunk = KnowledgeChunk(
        document_id=document.document_id,
        chunk_no=1,
        chunk_type=payload.chunk_type,
        title=payload.title,
        content=payload.content,
        keyword_text=f"{payload.title}\n{payload.content}",
        embedding=embedding,
        embedding_provider=settings.EMBEDDING_PROVIDER,
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dim=settings.EMBEDDING_DIM,
        priority=payload.priority,
        business_line=payload.business_line,
        sub_service=payload.sub_service,
        knowledge_type=payload.knowledge_type,
        language_pair=payload.language_pair,
        service_scope=payload.service_scope,
        region=payload.region,
        customer_tier=payload.customer_tier,
        structured_tags=payload.tags,
        status=now_status,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(chunk)
    db.flush()
    pricing_rule = _create_pricing_rule(db, document, chunk, payload.pricing_rule)
    db.commit()
    db.refresh(document)
    db.refresh(chunk)
    if pricing_rule:
        db.refresh(pricing_rule)
    return {
        "status": "success",
        "document": _doc_to_dict(document),
        "chunk": _chunk_to_dict(chunk),
        "pricing_rule": _pricing_rule_to_dict(pricing_rule) if pricing_rule else None,
    }

@app.post("/api/kb/documents/manual_multi")
async def create_manual_multi_knowledge(payload: KnowledgeMultiChunkCreate, db: Session = Depends(get_db)):
    """手工新增一个文档、多条切片，默认 draft。"""
    if not payload.chunks:
        raise HTTPException(status_code=400, detail="chunks 不能为空")

    document = KnowledgeDocument(
        title=payload.title,
        knowledge_type=payload.knowledge_type,
        business_line=payload.business_line,
        sub_service=payload.sub_service,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        status="draft",
        owner=payload.owner,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        risk_level=payload.risk_level,
        review_required=payload.review_required,
        review_status="pending" if payload.review_required else "auto_ready",
        tags=payload.tags,
    )
    db.add(document)
    db.flush()

    created_chunks = []
    created_pricing_rules = []
    for idx, item in enumerate(payload.chunks, start=1):
        embedding = EmbeddingService.embed(f"{item.title}\n{item.content}")
        if not embedding:
            raise HTTPException(status_code=500, detail=f"Embedding failed at chunk {idx}: {item.title}")
        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=idx,
            chunk_type=item.chunk_type,
            title=item.title,
            content=item.content,
            keyword_text=f"{item.title}\n{item.content}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            priority=item.priority,
            business_line=item.business_line or payload.business_line,
            sub_service=item.sub_service or payload.sub_service,
            knowledge_type=item.knowledge_type or payload.knowledge_type,
            language_pair=item.language_pair,
            service_scope=item.service_scope,
            region=item.region,
            customer_tier=item.customer_tier,
            structured_tags=item.tags,
            status="draft",
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )
        db.add(chunk)
        db.flush()
        pricing_rule = _create_pricing_rule(db, document, chunk, item.pricing_rule)
        if pricing_rule:
            created_pricing_rules.append(pricing_rule)
        created_chunks.append(chunk)

    db.commit()
    db.refresh(document)
    for chunk in created_chunks:
        db.refresh(chunk)
    for rule in created_pricing_rules:
        db.refresh(rule)
    return {
        "status": "success",
        "document": _doc_to_dict(document),
        "chunks": [_chunk_to_dict(chunk) for chunk in created_chunks],
        "pricing_rules": [_pricing_rule_to_dict(rule) for rule in created_pricing_rules],
    }

@app.get("/api/kb/dictionaries")
async def get_kb_dictionaries():
    return KB_LABELS

@app.get("/api/kb/documents")
async def list_kb_documents(
    status: str | None = None,
    business_line: str | None = None,
    knowledge_type: str | None = None,
    import_batch: str | None = None,
    review_status: str | None = None,
    source_type: str | None = None,
    risk_level: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeDocument)
    if status:
        query = query.filter(KnowledgeDocument.status == status)
    if business_line:
        query = query.filter(KnowledgeDocument.business_line == business_line)
    if knowledge_type:
        query = query.filter(KnowledgeDocument.knowledge_type == knowledge_type)
    if import_batch:
        query = query.filter(KnowledgeDocument.import_batch == import_batch)
    if review_status:
        query = query.filter(KnowledgeDocument.review_status == review_status)
    if source_type:
        query = query.filter(KnowledgeDocument.source_type == source_type)
    if risk_level:
        query = query.filter(KnowledgeDocument.risk_level == risk_level)
    docs = query.order_by(KnowledgeDocument.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_doc_to_dict(doc) for doc in docs]

@app.get("/api/kb/documents/{document_id}")
async def get_kb_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id).order_by(KnowledgeChunk.chunk_no.asc()).all()
    pricing_rules = db.query(PricingRule).filter(PricingRule.document_id == document_id).order_by(PricingRule.created_at.asc()).all()
    return {
        "document": _doc_to_dict(doc),
        "chunks": [_chunk_to_dict(chunk) for chunk in chunks],
        "pricing_rules": [_pricing_rule_to_dict(rule) for rule in pricing_rules],
    }

@app.patch("/api/kb/documents/{document_id}")
async def update_kb_document(document_id: str, payload: KnowledgeDocumentUpdate, db: Session = Depends(get_db)):
    """人工审核时修改文档级信息，保持 draft/pending。"""
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    for field in [
        "title", "knowledge_type", "business_line", "sub_service", "risk_level",
        "review_required", "tags", "effective_from", "effective_to"
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(doc, field, value)
    if doc.status == "draft":
        doc.review_status = "pending" if doc.review_required else "auto_ready"
    db.commit()
    db.refresh(doc)
    return {"status": "success", "document": _doc_to_dict(doc)}

@app.patch("/api/kb/chunks/{chunk_id}")
async def update_kb_chunk(chunk_id: str, payload: KnowledgeChunkUpdate, db: Session = Depends(get_db)):
    """人工审核时修改切片，标题或正文变化会重算 embedding。"""
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found")

    old_title = chunk.title
    old_content = chunk.content
    for field in [
        "title", "content", "chunk_type", "knowledge_type", "business_line", "sub_service",
        "language_pair", "service_scope", "region", "customer_tier", "priority", "structured_tags"
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(chunk, field, value)

    if chunk.title != old_title or chunk.content != old_content:
        embedding = EmbeddingService.embed(f"{chunk.title}\n{chunk.content}")
        if not embedding:
            raise HTTPException(status_code=500, detail="Embedding failed")
        chunk.keyword_text = f"{chunk.title}\n{chunk.content}"
        chunk.embedding = embedding
        chunk.embedding_provider = settings.EMBEDDING_PROVIDER
        chunk.embedding_model = settings.EMBEDDING_MODEL
        chunk.embedding_dim = settings.EMBEDDING_DIM

    db.commit()
    db.refresh(chunk)
    return {"status": "success", "chunk": _chunk_to_dict(chunk)}

@app.post("/api/kb/chunks/{chunk_id}/pricing_rule")
async def create_kb_chunk_pricing_rule(chunk_id: str, payload: PricingRulePayload, db: Session = Depends(get_db)):
    """为某条报价切片补充结构化报价规则。"""
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found")
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == chunk.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    rule = _create_pricing_rule(db, doc, chunk, payload)
    db.commit()
    db.refresh(rule)
    return {"status": "success", "pricing_rule": _pricing_rule_to_dict(rule)}

@app.get("/api/kb/pricing_rules")
async def list_kb_pricing_rules(
    status: str | None = None,
    business_line: str | None = None,
    language_pair: str | None = None,
    service_scope: str | None = None,
    customer_tier: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = db.query(PricingRule)
    if status:
        query = query.filter(PricingRule.status == status)
    if business_line:
        query = query.filter(PricingRule.business_line == business_line)
    if language_pair:
        query = query.filter(PricingRule.language_pair == language_pair)
    if service_scope:
        query = query.filter(PricingRule.service_scope == service_scope)
    if customer_tier:
        query = query.filter(PricingRule.customer_tier == customer_tier)
    rules = query.order_by(PricingRule.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_pricing_rule_to_dict(rule) for rule in rules]

@app.post("/api/kb/documents/{document_id}/publish")
async def publish_kb_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    updated_chunks, updated_pricing_rules = _sync_related_status(db, doc, "active", "approved")
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/documents/{document_id}/submit_review")
async def submit_review_kb_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    updated_chunks, updated_pricing_rules = _sync_related_status(db, doc, "review", "in_review")
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/documents/{document_id}/archive")
async def archive_kb_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    updated_chunks, updated_pricing_rules = _sync_related_status(db, doc, "archived")
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/documents/{document_id}/reject")
async def reject_kb_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    updated_chunks, updated_pricing_rules = _sync_related_status(db, doc, "rejected", "rejected")
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

def _load_bulk_docs(db: Session, document_ids: list[str]):
    unique_ids = [doc_id for doc_id in dict.fromkeys(document_ids or []) if doc_id]
    if not unique_ids:
        raise HTTPException(status_code=400, detail="document_ids 不能为空")
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id.in_(unique_ids)).all()
    found = {str(doc.document_id) for doc in docs}
    missing = [doc_id for doc_id in unique_ids if doc_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail={"message": "Some documents not found", "missing": missing})
    return docs

def _bulk_set_documents_status(db: Session, docs, status: str, review_status: str | None = None):
    updated_chunks = 0
    updated_pricing_rules = 0
    for doc in docs:
        chunk_count, rule_count = _sync_related_status(db, doc, status, review_status)
        updated_chunks += chunk_count
        updated_pricing_rules += rule_count
    db.commit()
    return {
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/bulk/documents/submit_review")
async def submit_review_kb_documents(payload: KnowledgeBulkAction, db: Session = Depends(get_db)):
    docs = _load_bulk_docs(db, payload.document_ids)
    result = _bulk_set_documents_status(db, docs, "review", "in_review")
    return {"status": "success", **result}

@app.post("/api/kb/bulk/documents/publish")
async def publish_kb_documents(payload: KnowledgeBulkAction, db: Session = Depends(get_db)):
    docs = _load_bulk_docs(db, payload.document_ids)
    result = _bulk_set_documents_status(db, docs, "active", "approved")
    return {"status": "success", **result}

@app.post("/api/kb/bulk/documents/archive")
async def archive_kb_documents(payload: KnowledgeBulkAction, db: Session = Depends(get_db)):
    docs = _load_bulk_docs(db, payload.document_ids)
    result = _bulk_set_documents_status(db, docs, "archived")
    return {"status": "success", **result}

@app.get("/api/kb/import_batches")
async def list_kb_import_batches(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = db.query(
        KnowledgeDocument.import_batch,
        KnowledgeDocument.status,
        func.count(KnowledgeDocument.document_id).label("count"),
        func.min(KnowledgeDocument.created_at).label("created_from"),
        func.max(KnowledgeDocument.created_at).label("created_to"),
    ).filter(KnowledgeDocument.import_batch.isnot(None)).group_by(
        KnowledgeDocument.import_batch,
        KnowledgeDocument.status,
    ).order_by(func.max(KnowledgeDocument.created_at).desc()).all()
    batches = {}
    for row in rows:
        item = batches.setdefault(row.import_batch, {
            "import_batch": row.import_batch,
            "total_count": 0,
            "status_counts": {},
            "created_from": row.created_from,
            "created_to": row.created_to,
        })
        item["total_count"] += row.count
        item["status_counts"][row.status] = row.count
        item["created_from"] = min(item["created_from"], row.created_from)
        item["created_to"] = max(item["created_to"], row.created_to)
    return list(batches.values())

def _build_import_batch_summary(docs: list[KnowledgeDocument]) -> dict:
    status_counts = {}
    risk_counts = {}
    business_line_counts = {}
    knowledge_type_counts = {}
    for doc in docs:
        status_counts[doc.status] = status_counts.get(doc.status, 0) + 1
        risk_counts[doc.risk_level] = risk_counts.get(doc.risk_level, 0) + 1
        business_line_counts[doc.business_line] = business_line_counts.get(doc.business_line, 0) + 1
        knowledge_type_counts[doc.knowledge_type] = knowledge_type_counts.get(doc.knowledge_type, 0) + 1
    return {
        "total_count": len(docs),
        "status_counts": status_counts,
        "risk_counts": risk_counts,
        "business_line_counts": business_line_counts,
        "knowledge_type_counts": knowledge_type_counts,
    }

@app.get("/api/kb/import_batches/{import_batch}")
async def get_kb_import_batch(import_batch: str, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).order_by(KnowledgeDocument.created_at.asc()).all()
    if not docs:
        raise HTTPException(status_code=404, detail="Import batch not found")
    doc_ids = [doc.document_id for doc in docs]
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id.in_(doc_ids)).all()
    pricing_rules = db.query(PricingRule).filter(PricingRule.document_id.in_(doc_ids)).all()
    chunk_counts = {}
    for chunk in chunks:
        key = str(chunk.document_id)
        chunk_counts[key] = chunk_counts.get(key, 0) + 1
    pricing_counts = {}
    for rule in pricing_rules:
        key = str(rule.document_id)
        pricing_counts[key] = pricing_counts.get(key, 0) + 1
    documents = []
    for doc in docs:
        item = _doc_to_dict(doc)
        doc_id = str(doc.document_id)
        item["chunk_count"] = chunk_counts.get(doc_id, 0)
        item["pricing_rule_count"] = pricing_counts.get(doc_id, 0)
        documents.append(item)
    return {
        "import_batch": import_batch,
        "summary": _build_import_batch_summary(docs),
        "documents": documents,
    }

@app.get("/api/kb/import_batches/{import_batch}/documents")
async def list_kb_import_batch_documents(import_batch: str, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).order_by(KnowledgeDocument.created_at.asc()).all()
    return [_doc_to_dict(doc) for doc in docs]

def set_documents_status(db: Session, docs, status: str, review_status: str | None = None):
    updated_chunks = 0
    updated_pricing_rules = 0
    for doc in docs:
        chunk_count, rule_count = _sync_related_status(db, doc, status, review_status)
        updated_chunks += chunk_count
        updated_pricing_rules += rule_count
    db.commit()
    return updated_chunks, updated_pricing_rules

@app.post("/api/kb/import_batches/{import_batch}/submit_review")
async def submit_review_kb_import_batch(import_batch: str, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).all()
    if not docs:
        raise HTTPException(status_code=404, detail="Import batch not found")
    updated_chunks, updated_pricing_rules = set_documents_status(db, docs, "review", "in_review")
    return {
        "status": "success",
        "import_batch": import_batch,
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/import_batches/{import_batch}/publish")
async def publish_kb_import_batch(import_batch: str, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).all()
    if not docs:
        raise HTTPException(status_code=404, detail="Import batch not found")
    updated_chunks, updated_pricing_rules = set_documents_status(db, docs, "active", "approved")
    return {
        "status": "success",
        "import_batch": import_batch,
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/import_batches/{import_batch}/archive")
async def archive_kb_import_batch(import_batch: str, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).all()
    if not docs:
        raise HTTPException(status_code=404, detail="Import batch not found")
    updated_chunks, updated_pricing_rules = set_documents_status(db, docs, "archived")
    return {
        "status": "success",
        "import_batch": import_batch,
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/import_batches/{import_batch}/rollback")
async def rollback_kb_import_batch(import_batch: str, db: Session = Depends(get_db)):
    """非破坏性回滚：将该批次全部归档，并标记 review_status=rolled_back。"""
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.import_batch == import_batch).all()
    if not docs:
        raise HTTPException(status_code=404, detail="Import batch not found")
    updated_chunks, updated_pricing_rules = set_documents_status(db, docs, "archived", "rolled_back")
    return {
        "status": "success",
        "import_batch": import_batch,
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
    }

@app.post("/api/kb/retrieve")
async def retrieve_kb(payload: KnowledgeRetrieveRequest):
    """知识库 V2 检索接口：只返回知识证据包，不生成回复。"""
    top_k = max(1, min(payload.top_k, 20))
    result = IntentEngine.retrieve_knowledge_v2(
        query_text=payload.query_text,
        query_features=payload.query_features or {},
        top_k=top_k,
        request_id=payload.request_id,
        session_id=payload.session_id,
    )
    for hit in result.get("hits", []):
        hit["business_line_label"] = label_for("business_line", hit.get("business_line"))
        hit["knowledge_type_label"] = label_for("knowledge_type", hit.get("knowledge_type"))
        hit["language_pair_label"] = label_for("language_pair", hit.get("language_pair"))
        hit["service_scope_label"] = label_for("service_scope", hit.get("service_scope"))
    return result

@app.post("/api/kb/import/faq_excel")
async def import_faq_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """导入 FAQ Excel：按“节点名/内容”列生成 draft 知识。"""
    filename = file.filename or "faq_import.xlsx"
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx/.xlsm 文件")

    try:
        from openpyxl import load_workbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openpyxl 未安装或不可用: {e}")

    raw = await file.read()
    try:
        workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 文件无法解析: {e}")

    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel 为空")

    header_row_index = None
    title_col = None
    content_col = None
    for idx, row in enumerate(rows[:10]):
        headers = list(row)
        title_col = find_column_index(headers, ["节点名", "标题", "问题", "场景"])
        content_col = find_column_index(headers, ["内容", "答案", "回复", "话术"])
        if title_col is not None and content_col is not None:
            header_row_index = idx
            break

    if header_row_index is None:
        raise HTTPException(status_code=400, detail="未找到必要列：节点名/内容")

    import_batch = f"faq_excel_{uuid.uuid4().hex[:12]}"
    created = []
    skipped = []
    failed = []

    for row_index, row in enumerate(rows[header_row_index + 1:], start=header_row_index + 2):
        title = str(row[title_col] or "").strip() if title_col < len(row) else ""
        content = str(row[content_col] or "").strip() if content_col < len(row) else ""
        if not title and not content:
            skipped.append({"row": row_index, "reason": "empty"})
            continue
        if not title or not content:
            skipped.append({"row": row_index, "reason": "missing_title_or_content", "title": title})
            continue

        business_line = infer_faq_business_line(title, content)
        risk_level = infer_faq_risk_level(title, content)
        embedding = EmbeddingService.embed(f"{title}\n{content}")
        if not embedding:
            failed.append({"row": row_index, "title": title, "reason": "embedding_failed"})
            continue

        source_ref = f"{filename} / {sheet.title} / row {row_index}"
        document = KnowledgeDocument(
            title=title,
            knowledge_type="faq",
            business_line=business_line,
            source_type="excel",
            source_ref=source_ref,
            source_meta={"filename": filename, "sheet": sheet.title, "row": row_index},
            status="draft",
            owner="faq_excel_import",
            import_batch=import_batch,
            risk_level=risk_level,
            review_required=True,
            review_status="pending",
            tags={"scenario": title, "raw_source": "faq_excel"},
        )
        db.add(document)
        db.flush()

        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=1,
            chunk_type="faq",
            title=title,
            content=content,
            keyword_text=f"{title}\n{content}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            priority=50,
            business_line=business_line,
            knowledge_type="faq",
            structured_tags={"scenario": title, "raw_source": "faq_excel"},
            status="draft",
        )
        db.add(chunk)
        created.append({
            "row": row_index,
            "document_id": str(document.document_id),
            "title": title,
            "business_line": business_line,
            "risk_level": risk_level,
        })

    db.commit()
    logger.info("KB_FAQ_EXCEL_IMPORT %s", json.dumps({
        "filename": filename,
        "sheet": sheet.title,
        "import_batch": import_batch,
        "created": len(created),
        "skipped": len(skipped),
        "failed": len(failed),
    }, ensure_ascii=False))

    return {
        "status": "success",
        "filename": filename,
        "sheet": sheet.title,
        "import_batch": import_batch,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }

@app.post("/api/kb/import/assisted_text")
async def import_assisted_text(payload: KnowledgeAssistTextImport, db: Session = Depends(get_db)):
    """使用 LLM-1 辅助把长文本拆成候选知识切片，全部保存为 draft。"""
    prompt = f"""
你是企业知识库整理助手。请只根据原文整理候选知识切片，不要编造事实、价格、客户名称或承诺。

输出必须是 JSON，格式如下：
{{
  "chunks": [
    {{
      "title": "简短标题",
      "content": "只包含一个业务知识点的原文或规范化表述",
      "knowledge_type": "capability|pricing|process|faq",
      "chunk_type": "rule|faq|constraint|definition",
      "business_line": "general|translation|printing|exhibition",
      "sub_service": null,
      "language_pair": null,
      "service_scope": null,
      "priority": 50,
      "risk_level": "low|medium|high",
      "review_required": true,
      "tags": {{}}
    }}
  ]
}}

字段约束：
- knowledge_type 只能使用 capability、pricing、process、faq。
- business_line 只能使用 general、translation、printing、exhibition。
- 价格、费用、折扣、税费、合同、承诺、赔付类内容 risk_level 必须为 high 且 review_required=true。
- 一条 chunk 只能表达一个知识点；如果一句话里有报价、最低收费、加急规则，必须拆成多条。
- 不确定的字段填 null，不要自造 code。

资料标题：{payload.title}
默认业务线：{payload.business_line}
原文：
{payload.content}
"""
    llm_result = IntentEngine.run_llm1_json_prompt(prompt, user_id="kb_assisted_text_import")
    if not llm_result or not isinstance(llm_result.get("chunks"), list):
        raise HTTPException(status_code=502, detail="LLM 辅助拆分失败或返回格式错误")

    chunks_payload = []
    for idx, raw_chunk in enumerate(llm_result["chunks"], start=1):
        title = str(raw_chunk.get("title") or "").strip()
        content = str(raw_chunk.get("content") or "").strip()
        if not title or not content:
            continue
        knowledge_type, raw_knowledge_type = normalize_code("knowledge_type", raw_chunk.get("knowledge_type") or "faq")
        business_line, raw_business_line = normalize_code("business_line", raw_chunk.get("business_line") or payload.business_line)
        language_pair, raw_language_pair = normalize_code("language_pair", raw_chunk.get("language_pair"))
        service_scope, raw_service_scope = normalize_code("service_scope", raw_chunk.get("service_scope"))
        tags = raw_chunk.get("tags") or {}
        raw_codes = {
            "raw_knowledge_type": raw_knowledge_type,
            "raw_business_line": raw_business_line,
            "raw_language_pair": raw_language_pair,
            "raw_service_scope": raw_service_scope,
        }
        tags.update({key: value for key, value in raw_codes.items() if value})
        chunks_payload.append(KnowledgeChunkCreate(
            title=title,
            content=content,
            knowledge_type=knowledge_type or "faq",
            chunk_type=raw_chunk.get("chunk_type") or "rule",
            business_line=business_line or payload.business_line,
            sub_service=raw_chunk.get("sub_service"),
            language_pair=language_pair,
            service_scope=service_scope,
            priority=int(raw_chunk.get("priority") or 50),
            tags=tags,
        ))

    if not chunks_payload:
        raise HTTPException(status_code=422, detail="LLM 未返回可入库的有效切片")

    import_batch = f"assist_text_{uuid.uuid4().hex[:12]}"
    document = KnowledgeDocument(
        title=payload.title,
        knowledge_type="faq",
        business_line=payload.business_line,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        source_meta={"assist_provider": settings.KB_LLM_ASSIST_PROVIDER, "raw_content_chars": len(payload.content)},
        status="draft",
        owner=payload.owner or "kb_assisted_text",
        import_batch=import_batch,
        risk_level="medium",
        review_required=True,
        review_status="pending",
        tags={"assist_import": True},
    )
    db.add(document)
    db.flush()

    created_chunks = []
    for idx, item in enumerate(chunks_payload, start=1):
        embedding = EmbeddingService.embed(f"{item.title}\n{item.content}")
        if not embedding:
            raise HTTPException(status_code=500, detail=f"Embedding failed at assisted chunk {idx}: {item.title}")
        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=idx,
            chunk_type=item.chunk_type,
            title=item.title,
            content=item.content,
            keyword_text=f"{item.title}\n{item.content}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            priority=item.priority,
            business_line=item.business_line,
            sub_service=item.sub_service,
            knowledge_type=item.knowledge_type,
            language_pair=item.language_pair,
            service_scope=item.service_scope,
            structured_tags=item.tags,
            status="draft",
        )
        db.add(chunk)
        created_chunks.append(chunk)

    db.commit()
    db.refresh(document)
    for chunk in created_chunks:
        db.refresh(chunk)
    logger.info("KB_ASSISTED_TEXT_IMPORT %s", json.dumps({
        "title": payload.title,
        "import_batch": import_batch,
        "chunks": len(created_chunks),
    }, ensure_ascii=False))
    return {
        "status": "success",
        "import_batch": import_batch,
        "document": _doc_to_dict(document),
        "chunks": [_chunk_to_dict(chunk) for chunk in created_chunks],
        "raw_llm_chunks_count": len(llm_result["chunks"]),
    }

# --- 系统运行时脚本管理 API ---

@app.get("/api/system/ai_scripts")
async def get_ai_scripts():
    import os, json
    filepath = os.path.join(os.path.dirname(__file__), "ai_settings.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    # 兜底返回默认框架
    from intent_engine import IntentEngine
    return {
        "SYSTEM_PROMPT_LLM1": IntentEngine.get_prompt1(),
        "SYSTEM_PROMPT_LLM2": IntentEngine.get_prompt2(),
        "FAST_TRACK_RULES": IntentEngine.get_rules()
    }

@app.post("/api/system/ai_scripts")
async def save_ai_scripts(payload: dict):
    import os, json
    filepath = os.path.join(os.path.dirname(__file__), "ai_settings.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 会话查询 API (供前端使用) ---

@app.get("/api/sessions")
async def get_sessions(db: Session = Depends(get_db)):
    """获取会话列表 (包含今日真实消息与模拟案例)"""
    from sqlalchemy import func, cast, Integer, text
    results = db.query(
        MessageLog.user_id,
        func.max(MessageLog.timestamp).label("last_msg"),
        func.max(cast(MessageLog.is_mock, Integer)).label("is_mock_int")
    ).group_by(MessageLog.user_id).order_by(text("last_msg DESC")).all()
    
    return [
        {"user_id": r.user_id, "last_msg": r.last_msg, "is_mock": bool(r.is_mock_int)} for r in results
    ]

@app.get("/api/sessions/{user_id}/messages")
async def get_messages(user_id: str):
    db = SessionLocal()
    try:
        messages = db.query(MessageLog).filter(MessageLog.user_id == user_id).order_by(MessageLog.id.asc()).all()
        logger.info(f"查询到用户 {user_id} 的消息，数量: {len(messages)}")
        return [{"id": m.id, "sender": m.sender_type, "content": m.content, "time": m.timestamp} for m in messages]
    finally:
        db.close()

def build_single_session_id(userid: str, external_userid: str) -> str:
    """保持与会话存档 1v1 session_id 生成规则一致"""
    participants = sorted([userid.strip(), external_userid.strip()])
    session_id = f"single_{'_'.join(participants)}"
    return session_id[:50]

def collect_fast_track_signals(logs) -> list:
    """扫描最近消息命中的强信号规则，规则异常不阻断主流程"""
    import re
    fast_track_signals = []
    for log in logs:
        content = log.content or ""
        for rule in IntentEngine.get_rules():
            name = rule.get("name", "未命名规则")
            pattern = rule.get("pattern", "")
            try:
                if pattern and re.search(pattern, content, re.IGNORECASE) and name not in fast_track_signals:
                    fast_track_signals.append(name)
            except re.error as e:
                logger.error(f"Fast-Track 正则规则异常 [{name}]: {e}")
    return fast_track_signals

def log_sidebar_result(event: str, payload: dict):
    """Log one compact JSON line for each sidebar request result."""
    logger.info(
        "SIDEBAR_ASSIST_%s %s",
        event,
        json.dumps(payload, ensure_ascii=False, default=str),
    )

def reanalyze_session_task(user_id: str, step: int = 1):
    """由界面主动测算触发：抓取特定会话并投递给 LLM 大语言模型进行意图重算"""
    db = SessionLocal()
    try:
        if step == 1:
            logger.info(f"⏳ 正在执行阶段 1: 调遣 Dify 大语言模型提取会话 {user_id} 结构化画像...")
            context_logs = db.query(MessageLog).filter(MessageLog.user_id == user_id).order_by(MessageLog.id.desc()).limit(15).all()
            context = [{"content": l.content, "sender_type": l.sender_type} for l in reversed(context_logs)]
            if context:
                IntentEngine.slow_track_analyze(user_id, context)
                logger.info(f"✅ 会话 {user_id} 的 AI 结构化特征(V1) 以及连带(V2)推送已生成完毕！")
        
        elif step == 2:
            logger.info(f"⏳ 正在执行阶段 2: 调遣 DeepSeek 针对 {user_id} 发放销售实战指令...")
            summary = db.query(IntentSummary).filter(IntentSummary.user_id == user_id).order_by(IntentSummary.id.desc()).first()
            if summary:
                # 重新构建 json 体传给 llm2
                recent_logs = db.query(MessageLog).filter(MessageLog.user_id == user_id).order_by(MessageLog.id.desc()).limit(15).all()
                fast_track_signals = collect_fast_track_signals(recent_logs)
                summary_json = {
                    "topic": summary.topic, "core_demand": summary.core_demand, "key_facts": summary.key_facts,
                    "todo_items": summary.todo_items, "risks": summary.risks, "to_be_confirmed": summary.to_be_confirmed,
                    "fast_track_signals": fast_track_signals
                }
                # RAG
                knowledge = []
                if summary.core_demand and summary.core_demand != "未明确":
                    knowledge = IntentEngine.retrieve_knowledge(summary.core_demand)
                # CRM Context
                crm_context = IntentEngine.get_crm_context(user_id)
                # LLM2
                assist_content = IntentEngine.generate_sales_assist(summary_json, knowledge, crm_context)
                if assist_content:
                    summary.sales_advice_v2 = assist_content
                    db.commit()
                    title = f"💡 [AI销售辅助更新] - {summary.topic}"
                    QYWXUtils.send_text_card(user_id, title, assist_content)
                    logger.info("✅ 实战建议(V2)指令下发完成！")
            
    except Exception as e:
        logger.error(f"AI 推理过程崩坏: {e}")
    finally:
        db.close()

@app.get("/api/sessions/{user_id}/analysis")
async def get_latest_analysis(user_id: str):
    db = SessionLocal()
    try:
        # 1. 实时扫描 Fast-Track 信号供前台色块展示
        recent_logs = db.query(MessageLog).filter(MessageLog.user_id == user_id).order_by(MessageLog.id.desc()).limit(15).all()
        fast_track_signals = collect_fast_track_signals(recent_logs)

        # 2. 获取 V1 及 V2 结果
        summary = db.query(IntentSummary).filter(IntentSummary.user_id == user_id).order_by(IntentSummary.id.desc()).first()
        
        result = {
            "fast_track": fast_track_signals,
            "has_v1": False,
            "has_v2": False
        }
        
        if summary:
            result.update({
                "has_v1": True,
                "topic": summary.topic, "core_demand": summary.core_demand, "key_facts": summary.key_facts,
                "todo_items": summary.todo_items, "risks": summary.risks, "to_be_confirmed": summary.to_be_confirmed,
                "status": summary.status, "at": summary.summarized_at
            })
            if summary.sales_advice_v2:
                result["has_v2"] = True
                result["sales_advice_v2"] = summary.sales_advice_v2
                
        return result
    finally:
        db.close()

from pydantic import BaseModel
class TriggerReq(BaseModel):
    step: int

@app.post("/api/sessions/{user_id}/trigger_llm")
async def trigger_llm_post(user_id: str, req: TriggerReq, background_tasks: BackgroundTasks):
    """前端手动拔枪按钮请求"""
    logger.info(f"收到前台发起的 LLM 手动指令！正在执行阶段 {req.step} ...")
    background_tasks.add_task(reanalyze_session_task, user_id, req.step)
    return {"status": "success", "msg": f"已将步骤 {req.step} 投入后台大模型运算池"}

class SidebarAssistRequest(BaseModel):
    external_userid: str
    userid: str
    force_refresh: bool = False

@app.post("/api/wecom/sidebar_assist")
async def sidebar_assist(request: SidebarAssistRequest):
    """供企微原生右侧边栏应用调用的同步直出接口"""
    from time import perf_counter

    total_started = perf_counter()
    timings_ms = {}
    stage_status = {}
    knowledge_status = "not_started"
    crm_context = None
    knowledge_base = None

    def mark_timing(name: str, started_at: float):
        timings_ms[name] = round((perf_counter() - started_at) * 1000, 2)

    db = SessionLocal()
    try:
        stage_started = perf_counter()
        external_userid = request.external_userid.strip()
        sales_userid = request.userid.strip()
        mark_timing("normalize_request_ms", stage_started)

        if not external_userid or not sales_userid:
            timings_ms["total_ms"] = round((perf_counter() - total_started) * 1000, 2)
            log_sidebar_result("ERROR", {
                "reason": "empty_required_params",
                "external_userid": external_userid,
                "sales_userid": sales_userid,
                "timings_ms": timings_ms,
            })
            return {
                "status": "error",
                "msg": "external_userid 和 userid 不能为空",
                "timings_ms": timings_ms
            }

        stage_started = perf_counter()
        session_id = build_single_session_id(sales_userid, external_userid)
        mark_timing("build_session_id_ms", stage_started)
        logger.info(f"🔰 收到侧边栏辅助请求：客服[{sales_userid}] -> 客户[{external_userid}] -> 会话[{session_id}]")
        
        # 获取当前销售与客户这条 1v1 会话的最近消息
        stage_started = perf_counter()
        recent_logs = db.query(MessageLog).filter(MessageLog.user_id == session_id).order_by(MessageLog.id.desc()).limit(15).all()
        mark_timing("load_recent_messages_ms", stage_started)

        # Fast-Track 前置扫描：既返回给侧边栏展示，也作为 LLM-2 的输入信号
        stage_started = perf_counter()
        fast_track_signals = collect_fast_track_signals(recent_logs)
        mark_timing("fast_track_scan_ms", stage_started)
        
        # 1. 触发同步测算 (阶段1 和 阶段2)
        stage_started = perf_counter()
        summary = db.query(IntentSummary).filter(IntentSummary.user_id == session_id).order_by(IntentSummary.id.desc()).first()
        mark_timing("load_summary_ms", stage_started)
        
        need_v1 = request.force_refresh or summary is None
        if need_v1:
            stage_status["analysis_mode"] = "force_refresh" if request.force_refresh else "first_analyze"
            if recent_logs:
                context = [{"content": l.content, "sender_type": l.sender_type} for l in reversed(recent_logs)]
                # 同步执行 V1
                stage_started = perf_counter()
                IntentEngine.slow_track_analyze(session_id, context)
                mark_timing("llm1_analyze_ms", stage_started)
                stage_status["llm1"] = "done"
            else:
                stage_status["llm1"] = "skipped_no_recent_logs"
                
            stage_started = perf_counter()
            summary = db.query(IntentSummary).filter(IntentSummary.user_id == session_id).order_by(IntentSummary.id.desc()).first()
            mark_timing("reload_summary_ms", stage_started)
        else:
            stage_status["analysis_mode"] = "complete_missing_v2" if not summary.sales_advice_v2 else "cache"
            stage_status["llm1"] = "skipped_summary_exists"

        if summary and (request.force_refresh or not summary.sales_advice_v2):
            # 同步执行 V2
            summary_json = {
                "topic": summary.topic, "core_demand": summary.core_demand, "key_facts": summary.key_facts,
                "todo_items": summary.todo_items, "risks": summary.risks, "to_be_confirmed": summary.to_be_confirmed,
                "fast_track_signals": fast_track_signals
            }
            # CRM 画像按外部联系人 ID 查询，不使用组合会话 ID
            stage_started = perf_counter()
            crm_context = IntentEngine.get_crm_context(external_userid)
            mark_timing("crm_profile_ms", stage_started)

            if summary.core_demand and summary.core_demand != "未明确":
                stage_started = perf_counter()
                knowledge_base = IntentEngine.retrieve_knowledge(summary.core_demand)
                mark_timing("knowledge_retrieve_ms", stage_started)
                knowledge_status = "ok" if knowledge_base else "empty_or_unavailable"
            else:
                knowledge_base = []
                knowledge_status = "skipped_no_core_demand"

            stage_started = perf_counter()
            assist_content = IntentEngine.generate_sales_assist(summary_json, knowledge_base, crm_context)
            mark_timing("llm2_generate_ms", stage_started)
            if assist_content:
                stage_started = perf_counter()
                summary.sales_advice_v2 = assist_content
                db.commit()
                mark_timing("persist_llm2_ms", stage_started)
                stage_status["llm2"] = "done"
            else:
                stage_status["llm2"] = "failed_no_content"
        else:
            stage_status["llm2"] = "skipped_advice_exists" if summary and summary.sales_advice_v2 else "skipped_no_summary"

        # 3. 封装全量字段给侧边栏前端
        result = {
            "status": "success",
            "external_userid": external_userid,
            "sales_userid": sales_userid,
            "session_id": session_id,
            "latest_dialog_count": len(recent_logs),
            "fast_track": fast_track_signals,
            "has_v1": False,
            "has_v2": False,
            "stage_status": stage_status
        }
        
        if summary:
            result.update({
                "has_v1": True,
                "topic": summary.topic,
                "core_demand": summary.core_demand,
                "key_facts": summary.key_facts,
                "risks": summary.risks,
                "todo_items": summary.todo_items,
                "to_be_confirmed": summary.to_be_confirmed
            })
            if summary.sales_advice_v2:
                result["has_v2"] = True
                result["sales_advice_v2"] = summary.sales_advice_v2
                # 回传检索到的原始知识块参考文档
                if knowledge_base is not None:
                    result["knowledge_base"] = knowledge_base
                elif summary.core_demand and summary.core_demand != "未明确":
                    stage_started = perf_counter()
                    result["knowledge_base"] = IntentEngine.retrieve_knowledge(summary.core_demand)
                    mark_timing("knowledge_retrieve_ms", stage_started)
                    knowledge_status = "ok" if result["knowledge_base"] else "empty_or_unavailable"
                else:
                    result["knowledge_base"] = []
                    knowledge_status = "skipped_no_core_demand"
            
            # 始终回传 CRM 画像供前端显示
            if crm_context is None:
                stage_started = perf_counter()
                crm_context = IntentEngine.get_crm_context(external_userid)
                mark_timing("crm_profile_ms", stage_started)
            result["crm_info"] = crm_context
        else:
            if crm_context is None:
                stage_started = perf_counter()
                crm_context = IntentEngine.get_crm_context(external_userid)
                mark_timing("crm_profile_ms", stage_started)
            result["crm_info"] = crm_context

        result["crm_status"] = (crm_context or {}).get("crm_profile_status", "unknown")
        result["knowledge_status"] = knowledge_status
        timings_ms["total_ms"] = round((perf_counter() - total_started) * 1000, 2)
        result["timings_ms"] = timings_ms
        log_sidebar_result("SUCCESS", {
            "external_userid": external_userid,
            "sales_userid": sales_userid,
            "session_id": session_id,
            "latest_dialog_count": len(recent_logs),
            "has_v1": result.get("has_v1"),
            "has_v2": result.get("has_v2"),
            "crm_status": result.get("crm_status"),
            "knowledge_status": result.get("knowledge_status"),
            "stage_status": stage_status,
            "timings_ms": timings_ms,
        })

        return result
    except Exception as e:
        logger.error(f"侧边栏接口异常退出: {e}")
        timings_ms["total_ms"] = round((perf_counter() - total_started) * 1000, 2)
        log_sidebar_result("ERROR", {
            "error": str(e),
            "stage_status": stage_status,
            "timings_ms": timings_ms,
        })
        return {
            "status": "error",
            "msg": str(e),
            "stage_status": stage_status,
            "timings_ms": timings_ms
        }
    finally:
        db.close()

@app.post("/api/test/seed")
async def seed_test_data():
    db = SessionLocal()
    try:
        # 案例 1: 价格冲突 (1v1 私聊场景)
        user1 = "case_price_conflict"
        db.query(MessageLog).filter(MessageLog.user_id == user1).delete()
        db.query(IntentSummary).filter(IntentSummary.user_id == user1).delete()
        
        db.add_all([
            MessageLog(user_id=user1, sender_type="customer", content="你们的报价单我收到了，但感觉比去年涨了不少啊。", is_mock=True),
            MessageLog(user_id=user1, sender_type="sales", content="今年原材料成本确实有波动，但我可以帮您申请大客户优惠。", is_mock=True),
            MessageLog(user_id=user1, sender_type="customer", content="如果能打8折我就定1000套，你们尽快确认，我等下要开会。", is_mock=True)
        ])
        db.add(IntentSummary(
            user_id=user1, topic="价格异议与折扣申请", core_demand="申请8折优惠以购买1000套",
            key_facts=["当前状态: 已获初次报价", "核心痛点: 成本上涨", "期望价格: 8折"], 
            todo_items=["核算8折毛利空间", "回复确认最后期限"],
            risks="客户极度敏感，不排除对比竞品", to_be_confirmed="能否通过高管折扣特批", status="报价中"
        ))

        # 案例 2: 售后服务纠纷 (群聊场景)
        user2 = "group_after_sales_998"
        db.query(MessageLog).filter(MessageLog.user_id == user2).delete()
        db.query(IntentSummary).filter(IntentSummary.user_id == user2).delete()

        db.add_all([
            MessageLog(user_id=user2, sender_type="customer", content="上周发的那批货有3箱破损了，能不能给个说法？", is_mock=True),
            MessageLog(user_id=user2, sender_type="sales", content="非常抱歉，我马上让物流查一下，图片拍了吗？", is_mock=True),
            MessageLog(user_id=user2, sender_type="customer", content="[图片] 看下，这都没法用了，急着等补货。", is_mock=True)
        ])
        db.add(IntentSummary(
            user_id=user2, topic="物流损毁赔付与补货", core_demand="尽快安排补发3箱货物并解决赔付",
            key_facts=["损毁详情: 3箱", "业务影响: 导致生产停滞", "优先等级: 紧急"], 
            todo_items=["向仓储部申请急速补货", "启动物流赔付流程"],
            risks="客户可能因此减少后续订单份额", to_be_confirmed="损毁的具体原因定位", status="售后处理中"
        ))

        # 案例 3: 产品规格深度咨询
        user3 = "case_tech_consult"
        db.query(MessageLog).filter(MessageLog.user_id == user3).delete()
        db.query(IntentSummary).filter(IntentSummary.user_id == user3).delete()

        db.add_all([
            MessageLog(user_id=user3, sender_type="customer", content="请问你们这款智能传感器的 IP 等级是多少？支持 Modbus 吗？", is_mock=True),
            MessageLog(user_id=user3, sender_type="sales", content="支持 Modbus-RTU 协议，且具备 IP67 防护等级，适合户外使用。", is_mock=True),
            MessageLog(user_id=user3, sender_type="customer", content="那我们需要 1.2m 长度的连接线，你们有现成的规格吗？", is_mock=True)
        ])
        db.add(IntentSummary(
            user_id=user3, topic="产品规格匹配确认", core_demand="确认传感器防护等级与线缆定制可行性",
            key_facts=["协议需求: Modbus-RTU", "防护等级: IP67", "定制项: 1.2m 线缆"], 
            todo_items=["咨询技术部线缆定制成本", "发送 IP67 测试报告"],
            risks="竞争对手可能提供更低价的同级别产品", to_be_confirmed="定制线缆的起订量", status="方案咨询"
        ))
        
        db.commit()
        logger.info(f"Mock 场景全量加载成功 [严谨性标识: is_mock=True]")
        return {"status": "seeded", "cases": [user1, user2, user3]}
    except Exception as e:
        logger.error(f"Mock 场景加载失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/sync/today")
async def sync_today_messages():
    """触发真实会话存档同步"""
    from archive_service import ArchiveService
    res = ArchiveService.sync_today_data()
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("msg"))
    return res

def health_check():
    from archive_service import ArchiveService
    return {
        "status": "running", 
        "archive_sdk": ArchiveService.get_token_status()
    }
