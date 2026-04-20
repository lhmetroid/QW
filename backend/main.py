from fastapi import FastAPI, Request, BackgroundTasks, Query, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
import os
import logging
import json
import uuid
import re
import requests
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from time import perf_counter
from typing import Any
from sqlalchemy import or_, text, func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from config import settings
from logging_config import setup_logging, sanitize_text
setup_logging()
from qywx_utils import QYWXUtils
from intent_engine import IntentEngine
from embedding_service import EmbeddingService
from email_import_service import EmailImportService
from database import (
    SessionLocal, MessageLog, init_db, KnowledgeBase, IntentSummary, get_db,
    KnowledgeDocument, KnowledgeChunk, PricingRule, KnowledgeHitLog, KnowledgeCandidate,
    KnowledgeVersionSnapshot, JobTask,
)
from worker import start_job

app = FastAPI(title="企微智能实时提醒后台")
logger = logging.getLogger(__name__)

@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((perf_counter() - started) * 1000)
        logger.exception(
            "REQUEST_ERROR path=%s method=%s request_id=%s elapsed_ms=%s",
            request.url.path,
            request.method,
            request_id,
            elapsed_ms,
        )
        raise
    elapsed_ms = round((perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    if elapsed_ms >= settings.SLOW_REQUEST_MS:
        logger.warning(
            "SLOW_REQUEST path=%s method=%s status=%s request_id=%s elapsed_ms=%s",
            request.url.path,
            request.method,
            response.status_code,
            request_id,
            elapsed_ms,
        )
    return response

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
    try:
        init_db() # 基础建表
        db = SessionLocal()
        # 强制补丁：为旧表增加 is_mock 列
        db.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS is_mock BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS retrieval_quality VARCHAR(50);"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(8, 6);"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS insufficient_info BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS manual_review_required BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS final_response TEXT;"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS manual_feedback JSON;"))
        db.execute(text("ALTER TABLE knowledge_hit_logs ADD COLUMN IF NOT EXISTS feedback_status VARCHAR(50);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_kc_active_effective ON knowledge_chunk (status, business_line, knowledge_type, effective_from, effective_to);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_kc_priority ON knowledge_chunk (priority DESC);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_pr_active_scope ON pricing_rule (status, business_line, language_pair, service_scope, customer_tier);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_kd_effective_to ON knowledge_document (status, effective_to);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_kcand_status_created ON knowledge_candidate (status, created_at DESC);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_kcand_source ON knowledge_candidate (source_type, source_ref);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_khl_status_created ON knowledge_hit_logs (status, created_at DESC);"))
        if settings.KB_FULLTEXT_INDEX_ENABLED:
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kc_fulltext_simple ON knowledge_chunk "
                "USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(keyword_text,'') || ' ' || coalesce(content,'')));"
            ))
        if settings.PGVECTOR_ENABLED:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
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
    force: bool = False
    force_reason: str | None = None
    operator: str | None = None

class KnowledgeHitFeedback(BaseModel):
    feedback_status: str
    manual_feedback: dict | None = None

class AssistFeedback(BaseModel):
    session_id: str
    feedback_status: str
    manual_feedback: dict | None = None
    final_response: str | None = None

class KnowledgeRegressionRunRequest(BaseModel):
    case_ids: list[str] | None = None
    groups: list[str] | None = None
    category: str | None = None
    risk_level: str | None = None
    business_line: str | None = None
    top_k: int = 5
    min_score: float | None = None
    cleanup_logs: bool = True
    include_hits: bool = False
    run_id: str | None = None

class JobRetryRequest(BaseModel):
    operator: str | None = None

class KnowledgePublishRequest(BaseModel):
    force: bool = False
    force_reason: str | None = None
    operator: str | None = None

class KnowledgeCandidateUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    knowledge_type: str | None = None
    chunk_type: str | None = None
    business_line: str | None = None
    sub_service: str | None = None
    language_pair: str | None = None
    service_scope: str | None = None
    region: str | None = None
    customer_tier: str | None = None
    priority: int | None = None
    risk_level: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    pricing_rule: dict | None = None
    owner: str | None = None
    operator: str | None = None
    review_notes: str | None = None
    status: str | None = None

class KnowledgeCandidateFromFeedbackRequest(BaseModel):
    log_id: str
    owner: str | None = None
    operator: str | None = None
    note: str | None = None
    title: str | None = None

class KnowledgeCandidatePromoteRequest(BaseModel):
    owner: str | None = None
    operator: str | None = None
    title: str | None = None
    content: str | None = None
    knowledge_type: str | None = None
    chunk_type: str | None = None
    business_line: str | None = None
    sub_service: str | None = None
    language_pair: str | None = None
    service_scope: str | None = None
    region: str | None = None
    customer_tier: str | None = None
    priority: int | None = None
    risk_level: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    pricing_rule: dict | None = None
    review_notes: str | None = None

class KnowledgeExtractFromMessagesRequest(BaseModel):
    session_id: str | None = None
    messages: list[str] | None = None
    title: str | None = None
    source_type: str = "message_extract"
    owner: str | None = None
    operator: str | None = None
    max_messages: int = 50
    max_candidates: int = 20

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
    "candidate_status": {
        "candidate": "候选中",
        "promoted": "已转知识",
        "rejected": "已拒绝",
        "archived": "已归档",
    },
    "candidate_source_type": {
        "feedback": "销售反馈",
        "message_extract": "会话抽取",
        "case_extract": "历史案例",
        "email_excel": "邮件整理表",
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
    for item_code, label in KB_LABELS.get(dict_type, {}).items():
        if code == label:
            return item_code, None
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

def is_pricing_text(title: str | None, content: str | None, knowledge_type: str | None = None) -> bool:
    text = f"{title or ''}\n{content or ''}"
    pricing_words = ["报价", "价格", "收费", "费用", "最低收费", "加急", "税点", "折扣", "元/千字", "元每千字"]
    return knowledge_type == "pricing" or any(word in text for word in pricing_words)

def infer_pricing_rule_candidate(
    title: str,
    content: str,
    business_line: str,
    language_pair: str | None = None,
    service_scope: str | None = None,
    customer_tier: str | None = None,
    raw_pricing_rule: dict | None = None,
) -> dict | None:
    """从 LLM 结果或文本中生成结构化报价规则候选，候选仍随文档进入 draft/review。"""
    if raw_pricing_rule:
        candidate = {key: value for key, value in dict(raw_pricing_rule).items() if value is not None}
    elif is_pricing_text(title, content):
        candidate = {}
    else:
        return None

    text = f"{title or ''}\n{content or ''}"
    candidate.setdefault("business_line", business_line)
    candidate.setdefault("language_pair", language_pair)
    candidate.setdefault("service_scope", service_scope)
    candidate.setdefault("customer_tier", customer_tier)
    candidate.setdefault("currency", "CNY")

    if not candidate.get("unit"):
        if any(word in text for word in ["千字", "千字符", "每千字", "元/千字", "元每千字"]):
            candidate["unit"] = "per_1000_chars"
        elif "小时" in text:
            candidate["unit"] = "per_hour"
        elif "天" in text or "日" in text:
            candidate["unit"] = "per_day"
        else:
            candidate["unit"] = "per_project"

    price_match = re.search(r"(\d+(?:\.\d+)?)\s*元\s*/?\s*(?:每)?千字", text)
    if price_match and candidate.get("price_min") is None:
        candidate["price_min"] = price_match.group(1)

    min_charge_match = re.search(r"最低收费(?:为|是|:|：)?\s*(\d+(?:\.\d+)?)\s*元", text)
    if min_charge_match and candidate.get("min_charge") is None:
        candidate["min_charge"] = min_charge_match.group(1)

    urgent_multiplier_match = re.search(r"加急.*?(\d+(?:\.\d+)?)\s*倍", text)
    if urgent_multiplier_match and candidate.get("urgent_multiplier") is None:
        candidate["urgent_multiplier"] = urgent_multiplier_match.group(1)

    tax_match = re.search(r"(含税|不含税|税点\s*\d+(?:\.\d+)?%?|发票[^，。；;]*)", text)
    if tax_match and not candidate.get("tax_policy"):
        candidate["tax_policy"] = tax_match.group(1)

    candidate["source_ref"] = candidate.get("source_ref") or "auto_candidate_from_text"
    return candidate

def normalize_header(value) -> str:
    return str(value or "").strip().replace(" ", "").replace("\n", "")

def find_column_index(headers: list, candidates: list[str]) -> int | None:
    normalized = [normalize_header(h) for h in headers]
    for candidate in candidates:
        target = normalize_header(candidate)
        if target in normalized:
            return normalized.index(target)
    return None

KB_EXCEL_IMPORT_TYPES = {
    "faq": {"label": "FAQ", "knowledge_type": "faq", "chunk_type": "faq", "risk_level": "medium"},
    "pricing": {"label": "报价表", "knowledge_type": "pricing", "chunk_type": "rule", "risk_level": "high"},
    "process": {"label": "流程 SOP", "knowledge_type": "process", "chunk_type": "rule", "risk_level": "medium"},
    "capability": {"label": "能力清单", "knowledge_type": "capability", "chunk_type": "rule", "risk_level": "medium"},
    "case": {"label": "历史案例", "knowledge_type": "faq", "chunk_type": "example", "risk_level": "medium"},
    "script": {"label": "销售话术", "knowledge_type": "faq", "chunk_type": "template", "risk_level": "medium"},
    "email_digest": {"label": "邮件整理", "knowledge_type": "faq", "chunk_type": "faq", "risk_level": "medium"},
}

KB_EXCEL_TEMPLATE_COLUMNS = [
    "标题",
    "内容",
    "知识类型",
    "切片类型",
    "业务线",
    "子服务",
    "语种",
    "服务范围",
    "地区",
    "客户层级",
    "优先级",
    "风险等级",
    "生效日期",
    "失效日期",
    "单位",
    "币种",
    "价格",
    "最高价格",
    "最低收费",
    "加急倍率",
    "税费",
    "标签",
]

KB_EXCEL_TEMPLATE_SAMPLE = {
    "faq": ["客户问公司主要做什么", "公司提供翻译、印刷、展会等企业服务。", "faq", "faq", "general", "", "", "general", "", "", 50, "medium", "", "", "", "", "", "", "", "", "", "公司介绍"],
    "pricing": ["英译法普通商务资料报价", "英译法普通商务资料按220元/千字报价，最低收费300元。", "pricing", "rule", "translation", "written_translation", "en->fr", "general", "", "", 95, "high", "2026-04-20", "2030-12-31", "per_1000_chars", "CNY", 220, 220, 300, "", "不含税", "报价"],
    "process": ["翻译下单流程", "收文件、确认语种用途、评估报价交期、付款立项、译审交付。", "process", "rule", "translation", "", "", "general", "", "", 80, "medium", "", "", "", "", "", "", "", "", "", "流程"],
    "capability": ["英译法能力说明", "可承接英译法普通商务资料。", "capability", "rule", "translation", "", "en->fr", "general", "", "", 80, "medium", "", "", "", "", "", "", "", "", "", "能力"],
    "case": ["价格异议案例", "客户质疑价格高，销售解释译审流程与交付保障后成交。", "faq", "example", "translation", "", "", "general", "", "", 60, "medium", "", "", "", "", "", "", "", "", "", "案例"],
    "script": ["价格异议话术", "可以先说明价格包含译审和交付保障，再按已发布报价规则说明。", "faq", "template", "translation", "", "", "general", "", "", 60, "medium", "", "", "", "", "", "", "", "", "", "话术"],
    "email_digest": ["邮件询价整理", "客户邮件询问英译法报价和交期，需先确认文件字数和用途。", "faq", "faq", "translation", "", "en->fr", "general", "", "", 60, "medium", "", "", "", "", "", "", "", "", "", "邮件"],
}

KB_EXCEL_COLUMN_ALIASES = {
    "title": ["标题", "节点名", "问题", "场景", "主题", "案例标题", "话术标题", "邮件主题", "title"],
    "content": ["内容", "答案", "回复", "话术", "正文", "案例内容", "邮件内容", "处理方式", "流程", "content"],
    "knowledge_type": ["知识类型", "knowledge_type", "类型"],
    "chunk_type": ["切片类型", "chunk_type"],
    "business_line": ["业务线", "business_line", "业务"],
    "sub_service": ["子服务", "sub_service"],
    "language_pair": ["语种", "语言对", "language_pair"],
    "service_scope": ["服务范围", "资料类型", "service_scope"],
    "region": ["地区", "region"],
    "customer_tier": ["客户层级", "客户类型", "customer_tier"],
    "priority": ["优先级", "priority", "权重"],
    "risk_level": ["风险等级", "risk_level"],
    "effective_from": ["生效时间", "生效日期", "effective_from"],
    "effective_to": ["失效时间", "失效日期", "effective_to"],
    "unit": ["单位", "计价单位", "unit"],
    "currency": ["币种", "currency"],
    "price_min": ["最低价格", "价格", "单价", "price_min"],
    "price_max": ["最高价格", "price_max"],
    "min_charge": ["最低收费", "起步价", "min_charge"],
    "urgent_multiplier": ["加急倍率", "urgent_multiplier"],
    "tax_policy": ["税费", "税点", "发票", "tax_policy"],
    "tags": ["标签", "tags"],
}

def _parse_datetime_or_none(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text_value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime value: {value}")

def _cell(row: tuple, index: int | None):
    if index is None or index >= len(row):
        return None
    value = row[index]
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value

def _safe_int(value, default: int = 50) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _resolve_excel_header(rows: list[tuple]) -> tuple[int, dict[str, int | None]]:
    best_index = None
    best_columns = None
    best_score = -1
    for idx, row in enumerate(rows[:10]):
        headers = list(row)
        columns = {
            field: find_column_index(headers, aliases)
            for field, aliases in KB_EXCEL_COLUMN_ALIASES.items()
        }
        score = sum(1 for value in columns.values() if value is not None)
        if columns["title"] is not None and columns["content"] is not None and score > best_score:
            best_index = idx
            best_columns = columns
            best_score = score
    if best_index is None or best_columns is None:
        raise HTTPException(status_code=400, detail="未找到必要列：标题/内容")
    return best_index, best_columns

def _load_excel_rows(raw: bytes, filename: str) -> tuple[str, list[tuple]]:
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx/.xlsm 文件")
    try:
        from openpyxl import load_workbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openpyxl 未安装或不可用: {e}")
    try:
        workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 文件无法解析: {e}")
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel 为空")
    return sheet.title, rows

def parse_kb_excel_import(raw: bytes, filename: str, import_type: str) -> dict:
    if import_type not in KB_EXCEL_IMPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported import_type: {import_type}")
    sheet_title, rows = _load_excel_rows(raw, filename)
    header_row_index, columns = _resolve_excel_header(rows)
    import_config = KB_EXCEL_IMPORT_TYPES[import_type]
    valid_rows = []
    skipped = []
    failed = []

    for row_index, row in enumerate(rows[header_row_index + 1:], start=header_row_index + 2):
        title = str(_cell(row, columns["title"]) or "").strip()
        content = str(_cell(row, columns["content"]) or "").strip()
        if not title and not content:
            skipped.append({"row": row_index, "reason": "empty"})
            continue
        row_errors = []
        if not title:
            row_errors.append("missing_title")
        if not content:
            row_errors.append("missing_content")

        knowledge_type, raw_knowledge_type = normalize_code(
            "knowledge_type",
            _cell(row, columns["knowledge_type"]) or import_config["knowledge_type"],
        )
        business_line, raw_business_line = normalize_code(
            "business_line",
            _cell(row, columns["business_line"]) or infer_faq_business_line(title, content),
        )
        language_pair, raw_language_pair = normalize_code("language_pair", _cell(row, columns["language_pair"]))
        service_scope, raw_service_scope = normalize_code("service_scope", _cell(row, columns["service_scope"]))
        customer_tier, raw_customer_tier = normalize_code("customer_tier", _cell(row, columns["customer_tier"]))

        raw_chunk_type = str(_cell(row, columns["chunk_type"]) or import_config["chunk_type"]).strip()
        chunk_type = raw_chunk_type if raw_chunk_type in KB_LABELS["chunk_type"] else import_config["chunk_type"]
        risk_level_value = str(_cell(row, columns["risk_level"]) or import_config["risk_level"]).strip()
        risk_level = risk_level_value if risk_level_value in KB_LABELS["risk_level"] else import_config["risk_level"]
        if knowledge_type == "pricing" or is_pricing_text(title, content, knowledge_type):
            risk_level = "high"

        tags = {
            "import_type": import_type,
            "raw_source": "kb_excel_import",
        }
        for key, value in {
            "raw_knowledge_type": raw_knowledge_type,
            "raw_business_line": raw_business_line,
            "raw_language_pair": raw_language_pair,
            "raw_service_scope": raw_service_scope,
            "raw_customer_tier": raw_customer_tier,
        }.items():
            if value:
                tags[key] = value
        raw_tags = _cell(row, columns["tags"])
        if raw_tags:
            tags["source_tags"] = str(raw_tags)

        pricing_rule = None
        if knowledge_type == "pricing" or import_type == "pricing":
            pricing_rule = {
                "business_line": business_line,
                "sub_service": _cell(row, columns["sub_service"]),
                "language_pair": language_pair,
                "service_scope": service_scope,
                "unit": _cell(row, columns["unit"]) or "per_project",
                "currency": _cell(row, columns["currency"]) or "CNY",
                "price_min": _cell(row, columns["price_min"]),
                "price_max": _cell(row, columns["price_max"]),
                "min_charge": _cell(row, columns["min_charge"]),
                "urgent_multiplier": _cell(row, columns["urgent_multiplier"]),
                "tax_policy": _cell(row, columns["tax_policy"]),
            }
            if not any(pricing_rule.get(field) not in (None, "") for field in ["price_min", "price_max", "min_charge", "urgent_multiplier", "tax_policy"]):
                inferred_rule = infer_pricing_rule_candidate(title, content, business_line or "general", language_pair, service_scope, customer_tier)
                pricing_rule = inferred_rule or pricing_rule
            if not any(pricing_rule.get(field) not in (None, "") for field in ["price_min", "price_max", "min_charge", "urgent_multiplier", "tax_policy"]):
                row_errors.append("pricing_rule_missing_value")

        item = {
            "row": row_index,
            "title": title,
            "content": content,
            "knowledge_type": knowledge_type or import_config["knowledge_type"],
            "chunk_type": chunk_type,
            "business_line": business_line or "general",
            "sub_service": _cell(row, columns["sub_service"]),
            "language_pair": language_pair,
            "service_scope": service_scope,
            "region": _cell(row, columns["region"]),
            "customer_tier": customer_tier,
            "priority": _safe_int(_cell(row, columns["priority"]), 50),
            "risk_level": risk_level,
            "effective_from": _parse_datetime_or_none(_cell(row, columns["effective_from"])),
            "effective_to": _parse_datetime_or_none(_cell(row, columns["effective_to"])),
            "tags": tags,
            "pricing_rule": pricing_rule,
            "errors": row_errors,
        }
        if row_errors:
            failed.append({"row": row_index, "title": title, "errors": row_errors})
        else:
            valid_rows.append(item)

    return {
        "filename": filename,
        "sheet": sheet_title,
        "import_type": import_type,
        "import_type_label": KB_EXCEL_IMPORT_TYPES[import_type]["label"],
        "header_row": header_row_index + 1,
        "columns": columns,
        "valid_rows": valid_rows,
        "skipped": skipped,
        "failed": failed,
    }

def _excel_item_preview(item: dict) -> dict:
    return {
        "row": item["row"],
        "title": item["title"],
        "knowledge_type": item["knowledge_type"],
        "knowledge_type_label": label_for("knowledge_type", item["knowledge_type"]),
        "chunk_type": item["chunk_type"],
        "business_line": item["business_line"],
        "business_line_label": label_for("business_line", item["business_line"]),
        "language_pair": item.get("language_pair"),
        "language_pair_label": label_for("language_pair", item.get("language_pair")),
        "service_scope": item.get("service_scope"),
        "service_scope_label": label_for("service_scope", item.get("service_scope")),
        "risk_level": item["risk_level"],
        "pricing_rule": item.get("pricing_rule"),
    }

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

def _redact_value(value):
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value

def _hit_log_to_dict(log: KnowledgeHitLog, redact: bool = False) -> dict:
    query_text = log.query_text
    final_response = log.final_response
    manual_feedback = log.manual_feedback
    if redact:
        query_text = _redact_value(query_text)
        final_response = _redact_value(final_response)
        manual_feedback = _redact_value(manual_feedback)
    return {
        "log_id": str(log.log_id),
        "request_id": log.request_id,
        "session_id": log.session_id,
        "query_text": query_text,
        "query_features": log.query_features,
        "filters_used": log.filters_used,
        "hit_chunk_ids": log.hit_chunk_ids,
        "scores": log.scores,
        "no_hit_reason": log.no_hit_reason,
        "status": log.status,
        "retrieval_quality": log.retrieval_quality,
        "confidence_score": float(log.confidence_score) if log.confidence_score is not None else None,
        "insufficient_info": log.insufficient_info,
        "manual_review_required": log.manual_review_required,
        "final_response": final_response,
        "manual_feedback": manual_feedback,
        "feedback_status": log.feedback_status,
        "latency_ms": log.latency_ms,
        "created_at": log.created_at,
    }

def _candidate_to_dict(candidate: KnowledgeCandidate) -> dict:
    return {
        "candidate_id": str(candidate.candidate_id),
        "title": candidate.title,
        "content": candidate.content,
        "knowledge_type": candidate.knowledge_type,
        "knowledge_type_label": label_for("knowledge_type", candidate.knowledge_type),
        "chunk_type": candidate.chunk_type,
        "chunk_type_label": label_for("chunk_type", candidate.chunk_type),
        "business_line": candidate.business_line,
        "business_line_label": label_for("business_line", candidate.business_line),
        "sub_service": candidate.sub_service,
        "language_pair": candidate.language_pair,
        "language_pair_label": label_for("language_pair", candidate.language_pair),
        "service_scope": candidate.service_scope,
        "service_scope_label": label_for("service_scope", candidate.service_scope),
        "region": candidate.region,
        "customer_tier": candidate.customer_tier,
        "customer_tier_label": label_for("customer_tier", candidate.customer_tier),
        "priority": candidate.priority,
        "risk_level": candidate.risk_level,
        "risk_level_label": label_for("risk_level", candidate.risk_level),
        "effective_from": candidate.effective_from,
        "effective_to": candidate.effective_to,
        "pricing_rule": candidate.pricing_rule,
        "source_type": candidate.source_type,
        "source_type_label": label_for("candidate_source_type", candidate.source_type),
        "source_ref": candidate.source_ref,
        "source_snapshot": candidate.source_snapshot,
        "status": candidate.status,
        "status_label": label_for("candidate_status", candidate.status),
        "owner": candidate.owner,
        "operator": candidate.operator,
        "review_notes": candidate.review_notes,
        "promoted_document_id": str(candidate.promoted_document_id) if candidate.promoted_document_id else None,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }

def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))

def _version_snapshot_to_dict(snapshot: KnowledgeVersionSnapshot) -> dict:
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "document_id": str(snapshot.document_id),
        "version_no": snapshot.version_no,
        "action": snapshot.action,
        "operator": snapshot.operator,
        "note": snapshot.note,
        "created_at": snapshot.created_at,
    }

def _job_to_dict(job: JobTask) -> dict:
    return {
        "job_id": str(job.job_id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "summary": job.summary,
        "task_payload": job.task_payload,
        "result": job.result,
        "error_message": job.error_message,
        "retry_of": job.retry_of,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
    }

def _document_snapshot_payload(doc: KnowledgeDocument, chunks: list[KnowledgeChunk], pricing_rules: list[PricingRule]) -> dict:
    return _jsonable({
        "document": _doc_to_dict(doc),
        "chunks": [_chunk_to_dict(chunk) for chunk in chunks],
        "pricing_rules": [_pricing_rule_to_dict(rule) for rule in pricing_rules],
    })

def _next_publish_version_no(db: Session, document_id: str, current_version: int | None) -> int:
    latest_snapshot = db.query(func.max(KnowledgeVersionSnapshot.version_no)).filter(
        KnowledgeVersionSnapshot.document_id == document_id
    ).scalar()
    if latest_snapshot:
        return int(latest_snapshot) + 1
    return max(int(current_version or 1), 1)

def _create_version_snapshot(
    db: Session,
    doc: KnowledgeDocument,
    *,
    action: str = "publish",
    operator: str | None = None,
    note: str | None = None,
    version_no: int | None = None,
) -> KnowledgeVersionSnapshot:
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).order_by(KnowledgeChunk.chunk_no.asc()).all()
    pricing_rules = db.query(PricingRule).filter(PricingRule.document_id == doc.document_id).order_by(PricingRule.created_at.asc()).all()
    snapshot = KnowledgeVersionSnapshot(
        document_id=doc.document_id,
        version_no=version_no or int(doc.version_no or 1),
        action=action,
        operator=operator,
        note=note,
        snapshot_data=_document_snapshot_payload(doc, chunks, pricing_rules),
    )
    db.add(snapshot)
    db.flush()
    return snapshot

def _restore_document_from_snapshot(db: Session, doc: KnowledgeDocument, snapshot: KnowledgeVersionSnapshot) -> dict:
    payload = snapshot.snapshot_data or {}
    doc_payload = payload.get("document") or {}
    chunks_payload = payload.get("chunks") or []
    pricing_payload = payload.get("pricing_rules") or []

    for field in [
        "title", "knowledge_type", "business_line", "sub_service", "source_type",
        "source_ref", "risk_level", "owner", "import_batch", "review_required", "tags",
    ]:
        if field in doc_payload:
            setattr(doc, field, doc_payload.get(field))
    doc.source_meta = dict(doc_payload.get("source_meta") or {})
    doc.effective_from = _parse_datetime_or_none(doc_payload.get("effective_from"))
    doc.effective_to = _parse_datetime_or_none(doc_payload.get("effective_to"))
    doc.version_no = int(snapshot.version_no)
    doc.status = "review"
    doc.review_required = True
    doc.review_status = "in_review"

    db.query(PricingRule).filter(PricingRule.document_id == doc.document_id).delete(synchronize_session=False)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).delete(synchronize_session=False)
    db.flush()

    chunk_id_map: dict[str, str] = {}
    recreated_chunks = []
    recreated_rules = []
    for chunk_payload in sorted(chunks_payload, key=lambda item: int(item.get("chunk_no") or 1)):
        embedding = EmbeddingService.embed(f"{chunk_payload.get('title') or ''}\n{chunk_payload.get('content') or ''}")
        if not embedding:
            raise HTTPException(status_code=500, detail=f"Embedding failed when restoring chunk: {chunk_payload.get('title')}")
        chunk = KnowledgeChunk(
            document_id=doc.document_id,
            chunk_no=int(chunk_payload.get("chunk_no") or 1),
            chunk_type=chunk_payload.get("chunk_type") or "faq",
            title=chunk_payload.get("title") or doc.title,
            content=chunk_payload.get("content") or "",
            keyword_text=chunk_payload.get("keyword_text") or f"{chunk_payload.get('title') or ''}\n{chunk_payload.get('content') or ''}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            priority=int(chunk_payload.get("priority") or 50),
            retrieval_weight=_decimal_or_none(chunk_payload.get("retrieval_weight")) or Decimal("1.000"),
            business_line=chunk_payload.get("business_line") or doc.business_line,
            sub_service=chunk_payload.get("sub_service"),
            knowledge_type=chunk_payload.get("knowledge_type") or doc.knowledge_type,
            language_pair=chunk_payload.get("language_pair"),
            service_scope=chunk_payload.get("service_scope"),
            region=chunk_payload.get("region"),
            customer_tier=chunk_payload.get("customer_tier"),
            structured_tags=chunk_payload.get("structured_tags"),
            status="review",
            effective_from=doc.effective_from,
            effective_to=doc.effective_to,
        )
        db.add(chunk)
        db.flush()
        if chunk_payload.get("chunk_id"):
            chunk_id_map[str(chunk_payload["chunk_id"])] = str(chunk.chunk_id)
        recreated_chunks.append(chunk)

    for rule_payload in pricing_payload:
        rule = PricingRule(
            document_id=doc.document_id,
            chunk_id=chunk_id_map.get(str(rule_payload.get("chunk_id"))) if rule_payload.get("chunk_id") else None,
            business_line=rule_payload.get("business_line") or doc.business_line,
            sub_service=rule_payload.get("sub_service"),
            language_pair=rule_payload.get("language_pair"),
            service_scope=rule_payload.get("service_scope"),
            unit=rule_payload.get("unit") or "per_project",
            currency=rule_payload.get("currency") or "CNY",
            price_min=_decimal_or_none(rule_payload.get("price_min")),
            price_max=_decimal_or_none(rule_payload.get("price_max")),
            urgent_multiplier=_decimal_or_none(rule_payload.get("urgent_multiplier")),
            tax_policy=rule_payload.get("tax_policy"),
            min_charge=_decimal_or_none(rule_payload.get("min_charge")),
            customer_tier=rule_payload.get("customer_tier"),
            region=rule_payload.get("region"),
            status="review",
            effective_from=doc.effective_from,
            effective_to=doc.effective_to,
            version_no=doc.version_no,
            source_ref=rule_payload.get("source_ref") or doc.source_ref,
        )
        db.add(rule)
        recreated_rules.append(rule)

    restore_meta = dict(doc.source_meta or {})
    restore_meta["restored_from_version"] = snapshot.version_no
    restore_meta["restored_at"] = datetime.utcnow().isoformat()
    doc.source_meta = restore_meta
    return {
        "restored_version": snapshot.version_no,
        "chunk_count": len(recreated_chunks),
        "pricing_rule_count": len(recreated_rules),
    }

def _job_payload_dir() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "scratch", "job_payloads")
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)

def _create_job_task(
    db: Session,
    *,
    job_type: str,
    task_payload: dict | None = None,
    summary: str | None = None,
    retry_of: str | None = None,
) -> JobTask:
    job = JobTask(
        job_type=job_type,
        status="queued",
        progress=0,
        summary=summary or "queued",
        task_payload=_jsonable(task_payload or {}),
        retry_of=retry_of,
    )
    db.add(job)
    db.flush()
    return job

def _create_single_document_and_chunk(
    db: Session,
    *,
    title: str,
    content: str,
    knowledge_type: str,
    business_line: str,
    sub_service: str | None = None,
    chunk_type: str = "faq",
    language_pair: str | None = None,
    service_scope: str | None = None,
    region: str | None = None,
    customer_tier: str | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    source_meta: dict | None = None,
    owner: str | None = None,
    priority: int = 50,
    risk_level: str = "medium",
    review_required: bool = True,
    tags: dict | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    pricing_rule: dict | None = None,
    import_batch: str | None = None,
):
    embedding = EmbeddingService.embed(f"{title}\n{content}")
    if not embedding:
        raise HTTPException(status_code=500, detail="Embedding failed")

    document = KnowledgeDocument(
        title=title,
        knowledge_type=knowledge_type,
        business_line=business_line,
        sub_service=sub_service,
        source_type=source_type,
        source_ref=source_ref,
        source_meta=source_meta,
        status="draft",
        owner=owner,
        import_batch=import_batch,
        effective_from=effective_from,
        effective_to=effective_to,
        risk_level=risk_level,
        review_required=review_required,
        review_status="pending" if review_required else "auto_ready",
        tags=tags,
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
        embedding_provider=settings.EMBEDDING_PROVIDER,
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dim=settings.EMBEDDING_DIM,
        priority=priority,
        business_line=business_line,
        sub_service=sub_service,
        knowledge_type=knowledge_type,
        language_pair=language_pair,
        service_scope=service_scope,
        region=region,
        customer_tier=customer_tier,
        structured_tags=tags,
        status="draft",
        effective_from=effective_from,
        effective_to=effective_to,
    )
    db.add(chunk)
    db.flush()

    pricing_rule_payload = pricing_rule or infer_pricing_rule_candidate(
        title,
        content,
        business_line,
        language_pair,
        service_scope,
        customer_tier,
    )
    rule = _create_pricing_rule(db, document, chunk, pricing_rule_payload)
    return document, chunk, rule

def _extract_relevant_sentences(content: str, keywords: list[str], limit: int = 3) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"[。！？!\n]+", content or "")
        if sentence and sentence.strip()
    ]
    matched = [sentence for sentence in sentences if any(keyword in sentence for keyword in keywords)]
    selected = matched[:limit] if matched else sentences[:limit]
    text = "。".join(selected).strip("。")
    return text or (content or "")[:500]

def _fallback_extract_candidate_items_from_text(title: str, content: str, source_type: str) -> list[dict]:
    text = f"{title or ''}\n{content or ''}"
    business_line = infer_faq_business_line(title, content)
    items = []

    pricing_keywords = ["报价", "价格", "收费", "最低收费", "加急", "税费", "税点", "发票"]
    process_keywords = ["流程", "步骤", "下单", "交付", "审核", "确认交期", "立项", "安排"]
    capability_keywords = ["能做", "可做", "支持", "承接", "服务范围", "能力", "覆盖"]

    if any(keyword in text for keyword in pricing_keywords):
        pricing_content = _extract_relevant_sentences(content, pricing_keywords)
        items.append({
            "title": (title or "历史报价提醒")[:255],
            "content": pricing_content,
            "knowledge_type": "pricing",
            "chunk_type": "rule",
            "business_line": business_line,
            "risk_level": "high",
            "pricing_rule": infer_pricing_rule_candidate(title or "历史报价提醒", pricing_content, business_line),
        })

    if any(keyword in text for keyword in process_keywords):
        process_content = _extract_relevant_sentences(content, process_keywords)
        items.append({
            "title": f"{(title or '历史流程经验')[:220]} - 流程",
            "content": process_content,
            "knowledge_type": "process",
            "chunk_type": "rule",
            "business_line": business_line,
            "risk_level": "medium",
            "pricing_rule": None,
        })

    if any(keyword in text for keyword in capability_keywords):
        capability_content = _extract_relevant_sentences(content, capability_keywords)
        items.append({
            "title": f"{(title or '历史能力说明')[:220]} - 能力",
            "content": capability_content,
            "knowledge_type": "capability",
            "chunk_type": "rule",
            "business_line": business_line,
            "risk_level": "medium",
            "pricing_rule": None,
        })

    if not items:
        items.append({
            "title": (title or "历史FAQ候选")[:255],
            "content": (content or "")[:1000],
            "knowledge_type": "faq",
            "chunk_type": "example" if source_type == "case_extract" else "faq",
            "business_line": business_line,
            "risk_level": infer_faq_risk_level(title, content),
            "pricing_rule": None,
        })
    return items

def _build_candidate_entries_from_record(record: dict, source_type: str) -> list[dict]:
    title = str(record.get("title") or record.get("subject") or "历史资料候选").strip()
    content = sanitize_text(str(record.get("content") or "").strip())
    if not content:
        return []
    items = _fallback_extract_candidate_items_from_text(title, content, source_type)
    snapshot = {
        key: sanitize_text(str(value)) if isinstance(value, str) else value
        for key, value in record.items()
        if value not in (None, "")
    }
    for item in items:
        item["source_snapshot"] = snapshot
    return items

def _create_candidate_record(
    db: Session,
    *,
    title: str,
    content: str,
    knowledge_type: str,
    chunk_type: str,
    business_line: str,
    sub_service: str | None = None,
    language_pair: str | None = None,
    service_scope: str | None = None,
    region: str | None = None,
    customer_tier: str | None = None,
    priority: int = 50,
    risk_level: str = "medium",
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    pricing_rule: dict | None = None,
    source_type: str = "feedback",
    source_ref: str | None = None,
    source_snapshot: dict | None = None,
    owner: str | None = None,
    operator: str | None = None,
    review_notes: str | None = None,
):
    candidate = KnowledgeCandidate(
        title=title,
        content=content,
        knowledge_type=knowledge_type,
        chunk_type=chunk_type,
        business_line=business_line,
        sub_service=sub_service,
        language_pair=language_pair,
        service_scope=service_scope,
        region=region,
        customer_tier=customer_tier,
        priority=priority,
        risk_level=risk_level,
        effective_from=effective_from,
        effective_to=effective_to,
        pricing_rule=pricing_rule,
        source_type=source_type,
        source_ref=source_ref,
        source_snapshot=source_snapshot,
        status="candidate",
        owner=owner,
        operator=operator,
        review_notes=review_notes,
    )
    db.add(candidate)
    db.flush()
    return candidate

def _create_candidate_from_feedback_log(
    db: Session,
    log: KnowledgeHitLog,
    *,
    owner: str | None = None,
    operator: str | None = None,
    note: str | None = None,
    title: str | None = None,
):
    existing = db.query(KnowledgeCandidate).filter(
        KnowledgeCandidate.source_type == "feedback",
        KnowledgeCandidate.source_ref == str(log.log_id),
        KnowledgeCandidate.status == "candidate",
    ).first()
    if existing:
        if note and note not in (existing.review_notes or ""):
            existing.review_notes = (existing.review_notes or "").strip()
            existing.review_notes = f"{existing.review_notes}\n{note}".strip()
        return existing

    query_features = log.query_features or {}
    requested_types = query_features.get("knowledge_type") or []
    knowledge_type = requested_types[0] if requested_types else "faq"
    business_line = query_features.get("business_line") or "general"
    feedback_note = note or ((log.manual_feedback or {}).get("note") if isinstance(log.manual_feedback, dict) else None)
    candidate_title = title or f"销售反馈修正：{(log.query_text or '未命名问题')[:40]}"
    content_parts = [
        f"客户问题：{log.query_text or ''}",
        f"当前建议：{log.final_response or '暂无'}",
    ]
    if feedback_note:
        content_parts.append(f"销售修正意见：{feedback_note}")
    candidate_content = "\n".join(part for part in content_parts if part).strip()
    pricing_rule = infer_pricing_rule_candidate(candidate_title, candidate_content, business_line)
    source_snapshot = {
        "log_id": str(log.log_id),
        "query_text": sanitize_text(log.query_text or ""),
        "query_features": log.query_features,
        "manual_feedback": _redact_value(log.manual_feedback),
        "final_response": sanitize_text(log.final_response or "") if log.final_response else None,
        "hit_chunk_ids": log.hit_chunk_ids,
        "status": log.status,
        "feedback_status": log.feedback_status,
    }
    return _create_candidate_record(
        db,
        title=candidate_title,
        content=candidate_content,
        knowledge_type=knowledge_type if knowledge_type in KB_LABELS["knowledge_type"] else "faq",
        chunk_type="rule" if knowledge_type in {"pricing", "process", "capability"} else "faq",
        business_line=business_line if business_line in KB_LABELS["business_line"] else "general",
        language_pair=query_features.get("language_pair"),
        service_scope=query_features.get("service_scope"),
        customer_tier=query_features.get("customer_tier"),
        priority=70,
        risk_level="high" if knowledge_type == "pricing" or is_pricing_text(candidate_title, candidate_content, knowledge_type) else "medium",
        pricing_rule=pricing_rule,
        source_type="feedback",
        source_ref=str(log.log_id),
        source_snapshot=source_snapshot,
        owner=owner or "sales_feedback",
        operator=operator,
        review_notes=feedback_note,
    )

def _extract_candidates_from_records(
    db: Session,
    records: list[dict],
    *,
    source_type: str,
    owner: str | None = None,
    operator: str | None = None,
    source_ref_prefix: str | None = None,
    max_candidates: int = 20,
) -> list[KnowledgeCandidate]:
    created = []
    for index, record in enumerate(records, start=1):
        if len(created) >= max_candidates:
            break
        entries = _build_candidate_entries_from_record(record, source_type)
        for offset, item in enumerate(entries, start=1):
            if len(created) >= max_candidates:
                break
            candidate = _create_candidate_record(
                db,
                title=item["title"],
                content=item["content"],
                knowledge_type=item["knowledge_type"],
                chunk_type=item["chunk_type"],
                business_line=item["business_line"],
                sub_service=item.get("sub_service"),
                language_pair=item.get("language_pair"),
                service_scope=item.get("service_scope"),
                region=item.get("region"),
                customer_tier=item.get("customer_tier"),
                priority=int(item.get("priority") or 60),
                risk_level=item.get("risk_level") or "medium",
                effective_from=item.get("effective_from"),
                effective_to=item.get("effective_to"),
                pricing_rule=item.get("pricing_rule"),
                source_type=source_type,
                source_ref=f"{source_ref_prefix or source_type}_{index}_{offset}",
                source_snapshot=item.get("source_snapshot"),
                owner=owner,
                operator=operator,
                review_notes=item.get("review_notes"),
            )
            created.append(candidate)
    return created

def _load_regression_cases() -> list[dict]:
    filepath = os.path.join(os.path.dirname(__file__), "kb_regression_cases.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def _filter_regression_cases(
    cases: list[dict],
    *,
    case_ids: list[str] | None = None,
    groups: list[str] | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    business_line: str | None = None,
) -> list[dict]:
    selected_ids = set(case_ids or [])
    selected_groups = set(groups or [])
    filtered = []
    for case in cases:
        if selected_ids and case.get("case_id") not in selected_ids:
            continue
        if selected_groups and case.get("group") not in selected_groups:
            continue
        if category and case.get("category") != category:
            continue
        if risk_level and case.get("risk_level") != risk_level:
            continue
        case_business_line = (case.get("query_features") or {}).get("business_line") or case.get("business_line")
        if business_line and case_business_line != business_line:
            continue
        filtered.append(case)
    return filtered

def _evaluate_regression_case(case: dict, result: dict) -> dict:
    expected = case.get("expected") or {}
    hits = result.get("hits") or []
    failures = []
    warnings = []

    def hit_text(hit):
        return f"{hit.get('title') or ''}\n{hit.get('content') or ''}".lower()

    must_type = expected.get("must_hit_knowledge_type")
    if must_type and not any(hit.get("knowledge_type") == must_type for hit in hits):
        failures.append(f"missing knowledge_type={must_type}")

    if expected.get("must_hit_pricing_rule") and not any(hit.get("pricing_rules") for hit in hits):
        failures.append("missing structured pricing_rule")

    if expected.get("manual_review_required") is True and not result.get("manual_review_required"):
        failures.append("manual_review_required was expected but not triggered")

    if expected.get("manual_review_allowed") is False and result.get("manual_review_required"):
        failures.append("manual_review_required was triggered unexpectedly")

    service_scope = expected.get("service_scope_filter")
    if service_scope and hits and not any(hit.get("service_scope") == service_scope for hit in hits):
        failures.append(f"missing service_scope={service_scope}")

    business_line = expected.get("business_line_filter")
    if business_line and hits and not all(hit.get("business_line") == business_line for hit in hits):
        failures.append(f"hit outside business_line={business_line}")

    customer_tier = expected.get("customer_tier_filter")
    if customer_tier and not result.get("filters_used", {}).get("customer_tier") == customer_tier:
        failures.append(f"customer_tier filter not applied: {customer_tier}")

    if expected.get("must_not_use_translation_price") and any(
        hit.get("business_line") == "translation" and hit.get("knowledge_type") == "pricing" for hit in hits
    ):
        failures.append("translation pricing was used for a non-translation query")

    if expected.get("must_hit_tax_or_invoice") and not any(
        any(word in hit_text(hit) for word in ["税", "发票", "invoice", "tax"]) for hit in hits
    ):
        failures.append("tax/invoice evidence not found")

    if expected.get("should_return_process_or_faq") and not any(
        hit.get("knowledge_type") in {"process", "faq"} for hit in hits
    ):
        failures.append("process/faq evidence not found")

    if expected.get("must_check_effective_time") and result.get("filters_used", {}).get("effective_time") != "now":
        failures.append("effective_time filter not applied")

    if expected.get("must_not_use_general_if_legal_exists"):
        legal_hits = [hit for hit in hits if hit.get("service_scope") == "legal"]
        general_hits = [hit for hit in hits if hit.get("service_scope") == "general"]
        if general_hits and not legal_hits:
            failures.append("general scope used while legal scope was requested")

    if expected.get("should_include_rules_before_expression") and not result.get("evidence_context", {}).get("rules"):
        warnings.append("rule evidence not found before expression/template evidence")

    if expected.get("must_not_fabricate_price") and result.get("status") == "ok" and not hits:
        failures.append("ok status without price evidence")

    if expected.get("must_not_fabricate_capability") and result.get("status") == "ok" and not hits:
        failures.append("ok status without capability evidence")

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
    }

def _select_publish_gate_case_ids(doc: KnowledgeDocument, chunks: list[KnowledgeChunk]) -> list[str]:
    cases = _load_regression_cases()
    knowledge_types = {doc.knowledge_type}
    knowledge_types.update(chunk.knowledge_type for chunk in chunks if chunk.knowledge_type)
    chunk_types = {chunk.chunk_type for chunk in chunks if chunk.chunk_type}
    service_scopes = {chunk.service_scope for chunk in chunks if chunk.service_scope}
    customer_tiers = {chunk.customer_tier for chunk in chunks if chunk.customer_tier}
    business_line = doc.business_line
    is_high_risk = doc.risk_level == "high" or "pricing" in knowledge_types

    selected = []
    for case in cases:
        query_features = case.get("query_features") or {}
        case_types = set(query_features.get("knowledge_type") or [])
        case_business_line = query_features.get("business_line")
        category = case.get("category")

        business_match = (
            not case_business_line
            or case_business_line == business_line
            or category == business_line
            or (case_business_line == "general" and is_high_risk)
        )
        if not business_match:
            continue

        knowledge_match = bool(case_types & knowledge_types)
        if not knowledge_match:
            if category in {"low_confidence", "versioning"} and is_high_risk:
                knowledge_match = True
            elif category == "customer_tier" and is_high_risk and customer_tiers:
                knowledge_match = True
            elif category == "cross_scope" and is_high_risk and service_scopes:
                knowledge_match = True
            elif category == "template" and ("template" in chunk_types or {"pricing", "faq"} & knowledge_types):
                knowledge_match = True
        if not knowledge_match:
            continue

        service_scope = query_features.get("service_scope")
        if service_scope and service_scopes and service_scope not in service_scopes and category not in {"cross_scope", "capability"}:
            continue

        customer_tier = query_features.get("customer_tier")
        if customer_tier and customer_tiers and customer_tier not in customer_tiers and category != "customer_tier":
            continue

        selected.append(case["case_id"])

    if not selected and is_high_risk:
        selected = [case["case_id"] for case in cases if case.get("category") in {"pricing", "low_confidence", "versioning"}]
    return list(dict.fromkeys(selected))

async def _run_publish_gate_for_documents(docs: list[KnowledgeDocument], db: Session) -> dict:
    case_ids = []
    docs_report = []
    for doc in docs:
        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).all()
        selected_ids = _select_publish_gate_case_ids(doc, chunks)
        case_ids.extend(selected_ids)
        docs_report.append({
            "document_id": str(doc.document_id),
            "title": doc.title,
            "knowledge_type": doc.knowledge_type,
            "business_line": doc.business_line,
            "selected_case_ids": selected_ids,
        })

    case_ids = list(dict.fromkeys(case_ids))
    if not case_ids:
        return {
            "selected_case_ids": [],
            "documents": docs_report,
            "passed": True,
            "summary": {"selected": 0, "passed": 0, "failed": 0},
            "results": [],
            "failed_cases": [],
        }

    regression = await run_kb_regression_cases(
        KnowledgeRegressionRunRequest(
            case_ids=case_ids,
            top_k=5,
            cleanup_logs=True,
            include_hits=False,
            run_id=f"publish_gate_{uuid.uuid4().hex[:10]}",
        )
    )
    failed_cases = [item for item in regression.get("results", []) if not item.get("passed")]
    return {
        "selected_case_ids": case_ids,
        "documents": docs_report,
        "passed": not failed_cases,
        "summary": {
            "selected": len(case_ids),
            "passed": regression.get("passed_count", 0),
            "failed": regression.get("failed_count", 0),
        },
        "results": regression.get("results", []),
        "failed_cases": failed_cases,
        "run_id": regression.get("run_id"),
    }

def _append_publish_gate_audit(
    doc: KnowledgeDocument,
    *,
    gate_report: dict,
    operator: str | None,
    force: bool,
    force_reason: str | None,
):
    meta = dict(doc.source_meta or {})
    audits = list(meta.get("publish_gate_audit") or [])
    audits.append({
        "timestamp": datetime.utcnow().isoformat(),
        "operator": operator,
        "force": force,
        "force_reason": force_reason,
        "selected_case_ids": gate_report.get("selected_case_ids") or [],
        "passed": gate_report.get("passed", False),
        "failed_case_ids": [item.get("case_id") for item in gate_report.get("failed_cases", [])],
    })
    meta["publish_gate_audit"] = audits[-20:]
    meta["last_publish_gate"] = {
        "timestamp": audits[-1]["timestamp"],
        "passed": gate_report.get("passed", False),
        "selected_case_ids": gate_report.get("selected_case_ids") or [],
    }
    doc.source_meta = meta

async def _ensure_publish_gate(
    docs: list[KnowledgeDocument],
    db: Session,
    *,
    force: bool = False,
    force_reason: str | None = None,
    operator: str | None = None,
) -> dict:
    gate_report = await _run_publish_gate_for_documents(docs, db)
    if not gate_report.get("passed") and not force:
        raise HTTPException(status_code=422, detail={
            "message": "Knowledge publish gate blocked",
            "gate_report": gate_report,
        })
    if force and not force_reason:
        raise HTTPException(status_code=422, detail="force_reason is required when force publish")
    for doc in docs:
        _append_publish_gate_audit(
            doc,
            gate_report=gate_report,
            operator=operator,
            force=force,
            force_reason=force_reason,
        )
    return gate_report

def _pricing_signature(rule: PricingRule) -> tuple:
    return (
        str(rule.price_min) if rule.price_min is not None else None,
        str(rule.price_max) if rule.price_max is not None else None,
        str(rule.min_charge) if rule.min_charge is not None else None,
        str(rule.urgent_multiplier) if rule.urgent_multiplier is not None else None,
        rule.tax_policy,
    )

def _pricing_scope(rule: PricingRule) -> tuple:
    return (
        rule.business_line,
        rule.sub_service,
        rule.language_pair,
        rule.service_scope,
        rule.customer_tier,
        rule.region,
        rule.unit,
        rule.currency,
    )

def _scope_to_dict(scope: tuple) -> dict:
    keys = ["business_line", "sub_service", "language_pair", "service_scope", "customer_tier", "region", "unit", "currency"]
    return {key: value for key, value in zip(keys, scope)}

def build_kb_quality_report(db: Session, days: int = 30, limit: int = 300) -> dict:
    now = datetime.utcnow()
    deadline = now + timedelta(days=max(1, min(days, 365)))
    issues = []

    pricing_chunks = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.status == "active",
        KnowledgeChunk.knowledge_type == "pricing",
    ).limit(max(1, min(limit, 1000))).all()
    for chunk in pricing_chunks:
        rule_count = db.query(PricingRule).filter(
            PricingRule.status == "active",
            PricingRule.document_id == chunk.document_id,
            or_(PricingRule.chunk_id == chunk.chunk_id, PricingRule.chunk_id.is_(None)),
        ).count()
        if rule_count == 0:
            issues.append({
                "type": "missing_pricing_rule",
                "severity": "high",
                "message": "active pricing chunk has no active structured pricing_rule",
                "document_id": str(chunk.document_id),
                "chunk_id": str(chunk.chunk_id),
                "title": chunk.title,
                "scope": {
                    "business_line": chunk.business_line,
                    "language_pair": chunk.language_pair,
                    "service_scope": chunk.service_scope,
                    "customer_tier": chunk.customer_tier,
                },
                "actions": ["view_document", "view_chunk", "add_pricing_rule"],
            })

    active_rules = db.query(PricingRule).filter(PricingRule.status == "active").limit(max(1, min(limit, 1000))).all()
    grouped_rules: dict[tuple, list[PricingRule]] = {}
    for rule in active_rules:
        grouped_rules.setdefault(_pricing_scope(rule), []).append(rule)

    for scope, rules in grouped_rules.items():
        if len(rules) < 2:
            continue
        signatures = {_pricing_signature(rule) for rule in rules}
        issue_type = "pricing_conflict" if len(signatures) > 1 else "duplicate_pricing_rule"
        severity = "high" if issue_type == "pricing_conflict" else "medium"
        issues.append({
            "type": issue_type,
            "severity": severity,
            "message": "same pricing scope has conflicting values" if issue_type == "pricing_conflict" else "same pricing scope has duplicate values",
            "scope": _scope_to_dict(scope),
            "rule_ids": [str(rule.rule_id) for rule in rules],
            "document_ids": sorted({str(rule.document_id) for rule in rules}),
            "signatures": [list(signature) for signature in sorted(signatures, key=lambda item: str(item))],
            "actions": ["view_rules", "archive_duplicate_rules" if issue_type == "duplicate_pricing_rule" else "review_conflict_rules"],
        })

    expiring_docs = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.status == "active",
        KnowledgeDocument.effective_to.isnot(None),
        KnowledgeDocument.effective_to <= deadline,
    ).limit(max(1, min(limit, 1000))).all()
    for doc in expiring_docs:
        expired = doc.effective_to < now
        issues.append({
            "type": "expired_document" if expired else "expiring_document",
            "severity": "high" if expired else "medium",
            "message": "active document is expired" if expired else "active document will expire soon",
            "document_id": str(doc.document_id),
            "title": doc.title,
            "effective_to": doc.effective_to,
            "days_left": (doc.effective_to - now).days,
            "actions": ["view_document", "extend_effective_to", "archive_document"],
        })

    expiring_rules = db.query(PricingRule).filter(
        PricingRule.status == "active",
        PricingRule.effective_to.isnot(None),
        PricingRule.effective_to <= deadline,
    ).limit(max(1, min(limit, 1000))).all()
    for rule in expiring_rules:
        expired = rule.effective_to < now
        issues.append({
            "type": "expired_pricing_rule" if expired else "expiring_pricing_rule",
            "severity": "high" if expired else "medium",
            "message": "active pricing rule is expired" if expired else "active pricing rule will expire soon",
            "rule_id": str(rule.rule_id),
            "document_id": str(rule.document_id),
            "scope": _scope_to_dict(_pricing_scope(rule)),
            "effective_to": rule.effective_to,
            "days_left": (rule.effective_to - now).days,
            "actions": ["view_rules", "archive_pricing_rule"],
        })

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for issue in issues:
        by_type[issue["type"]] = by_type.get(issue["type"], 0) + 1
        by_severity[issue["severity"]] = by_severity.get(issue["severity"], 0) + 1

    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda issue: (severity_order.get(issue["severity"], 9), issue["type"]))
    return {
        "status": "success",
        "generated_at": now.isoformat(),
        "window_days": days,
        "total_issues": len(issues),
        "by_type": by_type,
        "by_severity": by_severity,
        "issues": issues[:max(1, min(limit, 1000))],
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

def _document_publish_errors(db: Session, doc: KnowledgeDocument) -> list[str]:
    errors = []
    if not doc.version_no:
        errors.append("version_no is required")
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).all()
    if not chunks:
        errors.append("at least one knowledge chunk is required")

    pricing_chunks = [
        chunk for chunk in chunks
        if chunk.chunk_type != "constraint" and is_pricing_text(chunk.title, chunk.content, chunk.knowledge_type)
    ]
    if pricing_chunks:
        if not doc.effective_from or not doc.effective_to:
            errors.append("pricing document requires effective_from and effective_to")
        for chunk in pricing_chunks:
            rule_count = db.query(PricingRule).filter(
                PricingRule.document_id == doc.document_id,
                or_(PricingRule.chunk_id == chunk.chunk_id, PricingRule.chunk_id.is_(None)),
            ).count()
            if rule_count == 0:
                errors.append(f"pricing chunk requires pricing_rule: {chunk.title}")
    return errors

def _validate_documents_publishable(db: Session, docs) -> None:
    all_errors = {}
    for doc in docs:
        errors = _document_publish_errors(db, doc)
        if errors:
            all_errors[str(doc.document_id)] = {"title": doc.title, "errors": errors}
    if all_errors:
        raise HTTPException(status_code=422, detail={
            "message": "Knowledge publish validation failed",
            "documents": all_errors,
        })

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
    pricing_rule_payload = payload.pricing_rule or infer_pricing_rule_candidate(
        payload.title,
        payload.content,
        payload.business_line,
        payload.language_pair,
        payload.service_scope,
        payload.customer_tier,
    )
    pricing_rule = _create_pricing_rule(db, document, chunk, pricing_rule_payload)
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
        pricing_rule_payload = item.pricing_rule or infer_pricing_rule_candidate(
            item.title,
            item.content,
            item.business_line or payload.business_line,
            item.language_pair,
            item.service_scope,
            item.customer_tier,
        )
        pricing_rule = _create_pricing_rule(db, document, chunk, pricing_rule_payload)
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

@app.get("/api/kb/import/templates")
async def list_kb_import_templates():
    return {
        "status": "success",
        "columns": KB_EXCEL_TEMPLATE_COLUMNS,
        "templates": [
            {
                "type": import_type,
                "label": config["label"],
                "knowledge_type": config["knowledge_type"],
                "chunk_type": config["chunk_type"],
                "risk_level": config["risk_level"],
            }
            for import_type, config in KB_EXCEL_IMPORT_TYPES.items()
        ],
    }

@app.get("/api/kb/import/templates/{template_type}/download")
async def download_kb_import_template(template_type: str):
    if template_type not in KB_EXCEL_IMPORT_TYPES:
        raise HTTPException(status_code=404, detail="Template type not found")
    try:
        from openpyxl import Workbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openpyxl 未安装或不可用: {e}")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = KB_EXCEL_IMPORT_TYPES[template_type]["label"][:31]
    sheet.append(KB_EXCEL_TEMPLATE_COLUMNS)
    sheet.append(KB_EXCEL_TEMPLATE_SAMPLE[template_type])
    for idx, column_name in enumerate(KB_EXCEL_TEMPLATE_COLUMNS, start=1):
        sheet.cell(row=1, column=idx).value = column_name
        sheet.column_dimensions[sheet.cell(row=1, column=idx).column_letter].width = max(12, min(len(column_name) + 8, 24))

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"kb_{template_type}_template.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/api/kb/candidates")
async def list_kb_candidates(
    status: str | None = None,
    source_type: str | None = None,
    business_line: str | None = None,
    knowledge_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeCandidate)
    if status:
        query = query.filter(KnowledgeCandidate.status == status)
    if source_type:
        query = query.filter(KnowledgeCandidate.source_type == source_type)
    if business_line:
        query = query.filter(KnowledgeCandidate.business_line == business_line)
    if knowledge_type:
        query = query.filter(KnowledgeCandidate.knowledge_type == knowledge_type)
    items = query.order_by(KnowledgeCandidate.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_candidate_to_dict(item) for item in items]

@app.patch("/api/kb/candidates/{candidate_id}")
async def update_kb_candidate(candidate_id: str, payload: KnowledgeCandidateUpdate, db: Session = Depends(get_db)):
    candidate = db.query(KnowledgeCandidate).filter(KnowledgeCandidate.candidate_id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found")
    for field in [
        "title", "content", "knowledge_type", "chunk_type", "business_line", "sub_service",
        "language_pair", "service_scope", "region", "customer_tier", "priority", "risk_level",
        "effective_from", "effective_to", "pricing_rule", "owner", "operator", "review_notes", "status",
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(candidate, field, value)
    db.commit()
    db.refresh(candidate)
    return {"status": "success", "candidate": _candidate_to_dict(candidate)}

@app.post("/api/kb/candidates/from_feedback")
async def create_kb_candidate_from_feedback(payload: KnowledgeCandidateFromFeedbackRequest, db: Session = Depends(get_db)):
    log = db.query(KnowledgeHitLog).filter(KnowledgeHitLog.log_id == payload.log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Knowledge hit log not found")
    candidate = _create_candidate_from_feedback_log(
        db,
        log,
        owner=payload.owner,
        operator=payload.operator,
        note=payload.note,
        title=payload.title,
    )
    db.commit()
    db.refresh(candidate)
    return {"status": "success", "candidate": _candidate_to_dict(candidate)}

@app.post("/api/kb/candidates/{candidate_id}/promote")
async def promote_kb_candidate(candidate_id: str, payload: KnowledgeCandidatePromoteRequest, db: Session = Depends(get_db)):
    candidate = db.query(KnowledgeCandidate).filter(KnowledgeCandidate.candidate_id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found")
    if candidate.promoted_document_id:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == candidate.promoted_document_id).first()
        return {
            "status": "success",
            "candidate": _candidate_to_dict(candidate),
            "document": _doc_to_dict(doc) if doc else None,
            "message": "Candidate already promoted",
        }

    title = payload.title or candidate.title
    content = payload.content or candidate.content
    knowledge_type = payload.knowledge_type or candidate.knowledge_type
    business_line = payload.business_line or candidate.business_line
    chunk_type = payload.chunk_type or candidate.chunk_type
    doc, chunk, rule = _create_single_document_and_chunk(
        db,
        title=title,
        content=content,
        knowledge_type=knowledge_type,
        business_line=business_line,
        sub_service=payload.sub_service if payload.sub_service is not None else candidate.sub_service,
        chunk_type=chunk_type,
        language_pair=payload.language_pair if payload.language_pair is not None else candidate.language_pair,
        service_scope=payload.service_scope if payload.service_scope is not None else candidate.service_scope,
        region=payload.region if payload.region is not None else candidate.region,
        customer_tier=payload.customer_tier if payload.customer_tier is not None else candidate.customer_tier,
        source_type=f"candidate_{candidate.source_type}",
        source_ref=str(candidate.candidate_id),
        source_meta={"candidate_source_type": candidate.source_type, "candidate_source_ref": candidate.source_ref},
        owner=payload.owner or candidate.owner or "kb_candidate_promote",
        priority=payload.priority or candidate.priority,
        risk_level=payload.risk_level or candidate.risk_level,
        review_required=True,
        tags={"candidate_id": str(candidate.candidate_id), "candidate_source_type": candidate.source_type},
        effective_from=payload.effective_from if payload.effective_from is not None else candidate.effective_from,
        effective_to=payload.effective_to if payload.effective_to is not None else candidate.effective_to,
        pricing_rule=payload.pricing_rule if payload.pricing_rule is not None else candidate.pricing_rule,
    )
    candidate.status = "promoted"
    candidate.promoted_document_id = doc.document_id
    if payload.operator is not None:
        candidate.operator = payload.operator
    if payload.review_notes is not None:
        candidate.review_notes = payload.review_notes
    db.commit()
    db.refresh(candidate)
    db.refresh(doc)
    db.refresh(chunk)
    if rule:
        db.refresh(rule)
    return {
        "status": "success",
        "candidate": _candidate_to_dict(candidate),
        "document": _doc_to_dict(doc),
        "chunk": _chunk_to_dict(chunk),
        "pricing_rule": _pricing_rule_to_dict(rule) if rule else None,
    }

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
    snapshots = db.query(KnowledgeVersionSnapshot).filter(
        KnowledgeVersionSnapshot.document_id == document_id
    ).order_by(KnowledgeVersionSnapshot.version_no.desc(), KnowledgeVersionSnapshot.created_at.desc()).all()
    return {
        "document": _doc_to_dict(doc),
        "chunks": [_chunk_to_dict(chunk) for chunk in chunks],
        "pricing_rules": [_pricing_rule_to_dict(rule) for rule in pricing_rules],
        "version_snapshots": [_version_snapshot_to_dict(item) for item in snapshots],
    }

@app.get("/api/kb/chunks/{chunk_id}")
async def get_kb_chunk(chunk_id: str, db: Session = Depends(get_db)):
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found")
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == chunk.document_id).first()
    pricing_rules = db.query(PricingRule).filter(
        PricingRule.document_id == chunk.document_id,
        or_(PricingRule.chunk_id == chunk.chunk_id, PricingRule.chunk_id.is_(None)),
    ).order_by(PricingRule.created_at.asc()).all()
    return {
        "chunk": _chunk_to_dict(chunk),
        "document": _doc_to_dict(doc) if doc else None,
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
    document_id: str | None = None,
    rule_ids: str | None = None,
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
    if document_id:
        query = query.filter(PricingRule.document_id == document_id)
    if rule_ids:
        parsed_rule_ids = [item.strip() for item in rule_ids.split(",") if item.strip()]
        if parsed_rule_ids:
            query = query.filter(PricingRule.rule_id.in_(parsed_rule_ids))
    rules = query.order_by(PricingRule.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_pricing_rule_to_dict(rule) for rule in rules]

@app.patch("/api/kb/pricing_rules/{rule_id}")
async def update_kb_pricing_rule(rule_id: str, payload: PricingRulePayload, db: Session = Depends(get_db)):
    rule = db.query(PricingRule).filter(PricingRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    for field in [
        "business_line", "sub_service", "language_pair", "service_scope", "unit", "currency",
        "tax_policy", "customer_tier", "region", "source_ref"
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(rule, field, value)
    for field in ["price_min", "price_max", "urgent_multiplier", "min_charge"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(rule, field, _decimal_or_none(value))
    db.commit()
    db.refresh(rule)
    return {"status": "success", "pricing_rule": _pricing_rule_to_dict(rule)}

@app.post("/api/kb/pricing_rules/{rule_id}/archive")
async def archive_kb_pricing_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.query(PricingRule).filter(PricingRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    rule.status = "archived"
    db.commit()
    db.refresh(rule)
    return {"status": "success", "pricing_rule": _pricing_rule_to_dict(rule)}

@app.get("/api/kb/hit_logs")
async def list_kb_hit_logs(
    status: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    redact: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeHitLog)
    if status:
        query = query.filter(KnowledgeHitLog.status == status)
    if session_id:
        query = query.filter(KnowledgeHitLog.session_id == session_id)
    if request_id:
        query = query.filter(KnowledgeHitLog.request_id == request_id)
    logs = query.order_by(KnowledgeHitLog.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [_hit_log_to_dict(log, redact=redact) for log in logs]

@app.get("/api/kb/hit_logs/stats")
async def get_kb_hit_log_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total = db.query(func.count(KnowledgeHitLog.log_id)).scalar() or 0
    by_status = {
        row.status: row.count
        for row in db.query(KnowledgeHitLog.status, func.count(KnowledgeHitLog.log_id).label("count"))
        .group_by(KnowledgeHitLog.status)
        .all()
    }
    by_quality = {
        row.retrieval_quality or "unknown": row.count
        for row in db.query(KnowledgeHitLog.retrieval_quality, func.count(KnowledgeHitLog.log_id).label("count"))
        .group_by(KnowledgeHitLog.retrieval_quality)
        .all()
    }
    manual_review_count = db.query(func.count(KnowledgeHitLog.log_id)).filter(KnowledgeHitLog.manual_review_required == True).scalar() or 0
    insufficient_count = db.query(func.count(KnowledgeHitLog.log_id)).filter(KnowledgeHitLog.insufficient_info == True).scalar() or 0
    avg_latency = db.query(func.avg(KnowledgeHitLog.latency_ms)).scalar()
    return {
        "total": total,
        "by_status": by_status,
        "by_retrieval_quality": by_quality,
        "manual_review_count": manual_review_count,
        "insufficient_count": insufficient_count,
        "avg_latency_ms": round(float(avg_latency), 2) if avg_latency is not None else None,
    }

@app.post("/api/kb/hit_logs/{log_id}/feedback")
async def update_kb_hit_log_feedback(log_id: str, payload: KnowledgeHitFeedback, db: Session = Depends(get_db)):
    log = db.query(KnowledgeHitLog).filter(KnowledgeHitLog.log_id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Knowledge hit log not found")
    log.feedback_status = payload.feedback_status
    log.manual_feedback = payload.manual_feedback
    candidate = None
    if payload.feedback_status == "needs_fix":
        candidate = _create_candidate_from_feedback_log(
            db,
            log,
            owner="sales_feedback",
            operator="kb_hit_log_feedback",
            note=(payload.manual_feedback or {}).get("note") if isinstance(payload.manual_feedback, dict) else None,
        )
    db.commit()
    db.refresh(log)
    if candidate:
        db.refresh(candidate)
    return {"status": "success", "log": _hit_log_to_dict(log), "candidate": _candidate_to_dict(candidate) if candidate else None}

@app.post("/api/assist/feedback")
async def submit_assist_feedback(payload: AssistFeedback, db: Session = Depends(get_db)):
    log = db.query(KnowledgeHitLog).filter(
        KnowledgeHitLog.session_id == payload.session_id
    ).order_by(KnowledgeHitLog.created_at.desc()).first()
    if not log:
        raise HTTPException(status_code=404, detail="No knowledge hit log found for session")
    log.feedback_status = payload.feedback_status
    log.manual_feedback = payload.manual_feedback
    if payload.final_response:
        log.final_response = payload.final_response
    candidate = None
    if payload.feedback_status == "needs_fix":
        candidate = _create_candidate_from_feedback_log(
            db,
            log,
            owner="sales_feedback",
            operator="frontend_sidebar",
            note=(payload.manual_feedback or {}).get("note") if isinstance(payload.manual_feedback, dict) else None,
        )
    db.commit()
    db.refresh(log)
    if candidate:
        db.refresh(candidate)
    return {
        "status": "success",
        "log": _hit_log_to_dict(log, redact=True),
        "candidate": _candidate_to_dict(candidate) if candidate else None,
    }

def _execute_regression_cases(payload: KnowledgeRegressionRunRequest, report: Any = None) -> dict:
    cases = _filter_regression_cases(
        _load_regression_cases(),
        case_ids=payload.case_ids,
        groups=payload.groups,
        category=payload.category,
        risk_level=payload.risk_level,
        business_line=payload.business_line,
    )
    if not cases:
        raise HTTPException(status_code=404, detail="No regression cases matched")

    run_id = payload.run_id or f"kb_reg_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    results = []
    request_ids = []
    total_cases = len(cases)
    for index, case in enumerate(cases, start=1):
        if report:
            report(
                progress=min(95, round(index * 100 / max(total_cases, 1))),
                summary=f"running {case.get('case_id')}",
                result_patch={"current_case_id": case.get("case_id"), "total_cases": total_cases},
            )
        case_id = case["case_id"]
        request_id = f"{run_id}_{case_id}"
        request_ids.append(request_id)
        query_features = dict(case.get("query_features") or {})
        if payload.min_score is not None:
            query_features["min_score"] = payload.min_score
        result = IntentEngine.retrieve_knowledge_v2(
            query_text=case.get("query_text") or "",
            query_features=query_features,
            top_k=max(1, min(payload.top_k, 20)),
            request_id=request_id,
            session_id=run_id,
        )
        evaluation = _evaluate_regression_case(case, result)
        hit_summary = [
            {
                "chunk_id": hit.get("chunk_id"),
                "document_id": hit.get("document_id"),
                "knowledge_type": hit.get("knowledge_type"),
                "business_line": hit.get("business_line"),
                "language_pair": hit.get("language_pair"),
                "service_scope": hit.get("service_scope"),
                "score": hit.get("score"),
                "pricing_rule_count": len(hit.get("pricing_rules") or []),
            }
            for hit in result.get("hits", [])
        ]
        item = {
            "case_id": case_id,
            "group": case.get("group"),
            "risk_level": case.get("risk_level"),
            "category": case.get("category"),
            "passed": evaluation["passed"],
            "status": result.get("status"),
            "retrieval_quality": result.get("retrieval_quality"),
            "confidence_score": result.get("confidence_score"),
            "manual_review_required": result.get("manual_review_required"),
            "failures": evaluation["failures"],
            "warnings": evaluation["warnings"],
            "log_id": result.get("log_id"),
            "hit_count": len(result.get("hits", [])),
            "hits": hit_summary if payload.include_hits else [],
        }
        results.append(item)

    passed_count = sum(1 for item in results if item["passed"])
    failed_count = len(results) - passed_count
    cleanup = {"enabled": payload.cleanup_logs, "deleted_hit_logs": 0}
    if payload.cleanup_logs:
        db = SessionLocal()
        try:
            cleanup["deleted_hit_logs"] = db.query(KnowledgeHitLog).filter(KnowledgeHitLog.request_id.in_(request_ids)).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

    summary_by_group = {}
    for item in results:
        key = item.get("group") or "default"
        bucket = summary_by_group.setdefault(key, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if item["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    return {
        "status": "success" if failed_count == 0 else "failed",
        "run_id": run_id,
        "total": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": round((passed_count / len(results)) * 100, 2) if results else 0,
        "cleanup": cleanup,
        "summary_by_group": summary_by_group,
        "results": results,
    }

def _run_regression_job(report: Any, payload_data: dict) -> dict:
    payload = KnowledgeRegressionRunRequest(**payload_data)
    return _execute_regression_cases(payload, report=report)

@app.get("/api/kb/regression_cases")
async def list_kb_regression_cases(
    group: str | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    business_line: str | None = None,
):
    cases = _filter_regression_cases(
        _load_regression_cases(),
        groups=[group] if group else None,
        category=category,
        risk_level=risk_level,
        business_line=business_line,
    )
    meta = {
        "groups": sorted({case.get("group") for case in _load_regression_cases() if case.get("group")}),
        "categories": sorted({case.get("category") for case in _load_regression_cases() if case.get("category")}),
        "risk_levels": sorted({case.get("risk_level") for case in _load_regression_cases() if case.get("risk_level")}),
        "business_lines": sorted({
            ((case.get("query_features") or {}).get("business_line") or case.get("business_line"))
            for case in _load_regression_cases()
            if ((case.get("query_features") or {}).get("business_line") or case.get("business_line"))
        }),
    }
    return {
        "status": "success",
        "count": len(cases),
        "meta": meta,
        "cases": cases,
    }

@app.post("/api/kb/regression_cases/run")
async def run_kb_regression_cases(payload: KnowledgeRegressionRunRequest):
    return _execute_regression_cases(payload)

@app.post("/api/kb/regression_cases/run_async")
async def run_kb_regression_cases_async(payload: KnowledgeRegressionRunRequest, db: Session = Depends(get_db)):
    job = _create_job_task(
        db,
        job_type="kb_regression",
        task_payload=payload.model_dump(),
        summary="queued regression run",
    )
    db.commit()
    db.refresh(job)
    start_job(str(job.job_id), _run_regression_job, payload.model_dump())
    return {"status": "queued", "job": _job_to_dict(job)}

@app.get("/api/jobs")
async def list_jobs(job_type: str | None = None, status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(JobTask)
    if job_type:
        query = query.filter(JobTask.job_type == job_type)
    if status:
        query = query.filter(JobTask.status == status)
    jobs = query.order_by(JobTask.created_at.desc()).limit(max(1, min(limit, 300))).all()
    return {
        "status": "success",
        "count": len(jobs),
        "jobs": [_job_to_dict(job) for job in jobs],
    }

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobTask).filter(JobTask.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "success", "job": _job_to_dict(job)}

@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, payload: JobRetryRequest | None = None, db: Session = Depends(get_db)):
    job = db.query(JobTask).filter(JobTask.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    retry_payload = dict(job.task_payload or {})
    if payload and payload.operator:
        retry_payload["operator"] = payload.operator
    retry_job_record = _create_job_task(
        db,
        job_type=job.job_type,
        task_payload=retry_payload,
        summary=f"retry {job.job_type}",
        retry_of=str(job.job_id),
    )
    db.commit()
    db.refresh(retry_job_record)
    if job.job_type == "kb_regression":
        start_job(str(retry_job_record.job_id), _run_regression_job, retry_payload)
    elif job.job_type == "kb_excel_import":
        start_job(str(retry_job_record.job_id), _run_excel_import_job, retry_payload)
    else:
        raise HTTPException(status_code=422, detail=f"Retry not supported for job_type={job.job_type}")
    return {"status": "queued", "job": _job_to_dict(retry_job_record)}

@app.get("/api/kb/quality/report")
async def get_kb_quality_report(days: int = 30, limit: int = 300, db: Session = Depends(get_db)):
    return build_kb_quality_report(db, days=days, limit=limit)

@app.get("/api/kb/quality/conflicts")
async def get_kb_quality_conflicts(limit: int = 300, db: Session = Depends(get_db)):
    report = build_kb_quality_report(db, days=30, limit=limit)
    report["issues"] = [
        issue for issue in report["issues"]
        if issue["type"] in {"pricing_conflict", "duplicate_pricing_rule", "missing_pricing_rule"}
    ]
    report["total_issues"] = len(report["issues"])
    return report

@app.get("/api/kb/quality/expiring")
async def get_kb_quality_expiring(days: int = 30, limit: int = 300, db: Session = Depends(get_db)):
    report = build_kb_quality_report(db, days=days, limit=limit)
    report["issues"] = [
        issue for issue in report["issues"]
        if issue["type"] in {"expired_document", "expiring_document", "expired_pricing_rule", "expiring_pricing_rule"}
    ]
    report["total_issues"] = len(report["issues"])
    return report

@app.get("/api/kb/performance/status")
async def get_kb_performance_status(db: Session = Depends(get_db)):
    index_rows = db.execute(text(
        "SELECT tablename, indexname FROM pg_indexes "
        "WHERE tablename IN ('knowledge_chunk','knowledge_document','pricing_rule','knowledge_hit_logs') "
        "ORDER BY tablename, indexname"
    )).mappings().all()
    extensions = {
        row["extname"]: True
        for row in db.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm')")).mappings().all()
    }
    chunk_count = db.query(func.count(KnowledgeChunk.chunk_id)).scalar() or 0
    active_chunk_count = db.query(func.count(KnowledgeChunk.chunk_id)).filter(KnowledgeChunk.status == "active").scalar() or 0
    active_pricing_rule_count = db.query(func.count(PricingRule.rule_id)).filter(PricingRule.status == "active").scalar() or 0
    return {
        "status": "success",
        "retrieval_strategy": {
            "pgvector_enabled": settings.PGVECTOR_ENABLED,
            "pgvector_required": settings.PGVECTOR_REQUIRED,
            "pgvector_extension_available": bool(extensions.get("vector")),
            "embedding_storage": "json",
            "fulltext_index_enabled": settings.KB_FULLTEXT_INDEX_ENABLED,
            "keyword_prefilter_enabled": settings.KB_KEYWORD_PREFILTER_ENABLED,
            "candidate_limit": settings.KB_CANDIDATE_LIMIT,
        },
        "counts": {
            "knowledge_chunks": chunk_count,
            "active_knowledge_chunks": active_chunk_count,
            "active_pricing_rules": active_pricing_rule_count,
        },
        "indexes": [dict(row) for row in index_rows],
    }

def _is_placeholder_value(value: str | None) -> bool:
    text_value = str(value or "").strip()
    if not text_value:
        return True
    placeholders = {"your-corp-id", "your-corp-secret", "your-agent-id", "your-token", "your-token",
                    "your-encoding-aes-key", "your-chatdata-secret", "your-db-name", "your-db-user",
                    "your-db-password", "your-llm1-api-key", "your-llm2-api-key"}
    return text_value in placeholders or text_value.startswith("your-")

def _mask_config_value(value: str | None, keep: int = 4) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    if len(text_value) <= keep:
        return "*" * len(text_value)
    return f"{text_value[:keep]}***"

def _probe_http_status(url: str, headers: dict | None = None) -> dict:
    try:
        session = requests.Session()
        session.trust_env = settings.HTTP_TRUST_ENV
        response = session.get(url, headers=headers or {}, timeout=settings.KB_HEALTHCHECK_TIMEOUT_SECONDS)
        reachable = response.status_code < 500
        return {
            "status": "ok" if reachable else "error",
            "reachable": reachable,
            "http_status": response.status_code,
        }
    except Exception as exc:
        return {
            "status": "error",
            "reachable": False,
            "error": sanitize_text(str(exc)),
        }

def _system_config_check() -> dict:
    checks = {}

    db_configured = not any(
        _is_placeholder_value(value)
        for value in [settings.DB_HOST, settings.DB_NAME, settings.DB_USER, settings.DB_PASSWORD]
    )
    db_check = {
        "configured": db_configured,
        "host": settings.DB_HOST,
        "database": settings.DB_NAME,
        "user": settings.DB_USER,
        "suggestions": [],
    }
    if db_configured:
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db_check["status"] = "ok"
        except Exception as exc:
            db_check["status"] = "error"
            db_check["error"] = sanitize_text(str(exc))
            db_check["suggestions"].append("检查 PostgreSQL 地址、库名、账号密码，以及数据库是否允许当前主机连接。")
        finally:
            try:
                db.close()
            except Exception:
                pass
    else:
        db_check["status"] = "error"
        db_check["suggestions"].append("补齐 DB_HOST / DB_NAME / DB_USER / DB_PASSWORD。")
    checks["postgres"] = db_check

    embedding_headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"} if settings.EMBEDDING_API_KEY else {}
    embedding_probe = _probe_http_status(settings.EMBEDDING_API_URL.rstrip("/") + "/api/tags", embedding_headers)
    checks["embedding"] = {
        "status": embedding_probe["status"] if not _is_placeholder_value(settings.EMBEDDING_API_URL) else "error",
        "configured": not _is_placeholder_value(settings.EMBEDDING_API_URL),
        "provider": settings.EMBEDDING_PROVIDER,
        "url": settings.EMBEDDING_API_URL,
        "model": settings.EMBEDDING_MODEL,
        "probe": embedding_probe,
        "suggestions": [] if embedding_probe.get("reachable") else ["检查 Ollama 服务是否启动、URL 是否正确、模型是否已拉取。"],
    }

    def build_llm_check(name: str, api_url: str, api_key: str, model: str):
        configured = not _is_placeholder_value(api_url) and not _is_placeholder_value(api_key)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key and not api_key.startswith("app-") else {}
        probe_url = api_url.rstrip("/")
        if api_key.startswith("app-"):
            probe_url = probe_url + "/info"
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            probe_url = probe_url + "/models"
        probe = _probe_http_status(probe_url, headers)
        suggestions = []
        if not configured:
            suggestions.append(f"补齐 {name.upper()} 的 API URL / API KEY / MODEL。")
        elif not probe.get("reachable"):
            suggestions.append(f"检查 {name.upper()} 的网关地址、代理和 API KEY。")
        return {
            "status": "ok" if configured and probe.get("reachable") else "error",
            "configured": configured,
            "url": api_url,
            "api_key_masked": _mask_config_value(api_key),
            "model": model,
            "probe": probe,
            "suggestions": suggestions,
        }

    checks["llm1"] = build_llm_check("llm1", settings.LLM1_API_URL, settings.LLM1_API_KEY, settings.LLM1_MODEL)
    checks["llm2"] = build_llm_check("llm2", settings.LLM2_API_URL, settings.LLM2_API_KEY, settings.LLM2_MODEL)

    crm_configured = not any(
        _is_placeholder_value(value)
        for value in [settings.CRM_DBHost, settings.CRM_DBName, settings.CRM_DBUserId, settings.CRM_DBPassword]
    )
    crm_check = {
        "configured": crm_configured,
        "host": settings.CRM_DBHost,
        "database": settings.CRM_DBName,
        "user": settings.CRM_DBUserId,
        "suggestions": [],
    }
    if crm_configured:
        try:
            from crm_database import CRMSessionLocal
            crm_db = CRMSessionLocal()
            crm_db.execute(text("SELECT 1"))
            crm_check["status"] = "ok"
        except Exception as exc:
            crm_check["status"] = "error"
            crm_check["error"] = sanitize_text(str(exc))
            crm_check["suggestions"].append("检查 SQL Server 地址、ODBC Driver、账号密码和网络连通性。")
        finally:
            try:
                crm_db.close()
            except Exception:
                pass
    else:
        crm_check["status"] = "error"
        crm_check["suggestions"].append("补齐 CRM_DBHost / CRM_DBName / CRM_DBUserId / CRM_DBPassword。")
    checks["crm"] = crm_check

    qywx_credentials_ready = not any(
        _is_placeholder_value(value)
        for value in [settings.CORP_ID, settings.CORP_SECRET, settings.AGENT_ID, settings.TOKEN, settings.ENCODING_AES_KEY]
    )
    checks["qywx"] = {
        "status": "ok" if qywx_credentials_ready else "error",
        "configured": qywx_credentials_ready,
        "corp_id_masked": _mask_config_value(settings.CORP_ID),
        "agent_id_masked": _mask_config_value(settings.AGENT_ID),
        "suggestions": [] if qywx_credentials_ready else ["补齐企微应用 CorpID / Secret / AgentID / Token / EncodingAESKey。"],
    }

    sdk_path = os.path.join(os.path.dirname(__file__), "WeWorkFinanceSdk.dll")
    checks["archive_sdk"] = {
        "status": "ok" if os.path.exists(sdk_path) and os.path.exists(settings.PRIVATE_KEY_PATH) and not _is_placeholder_value(settings.CHATDATA_SECRET) else "error",
        "sdk_present": os.path.exists(sdk_path),
        "private_key_present": os.path.exists(settings.PRIVATE_KEY_PATH),
        "chatdata_secret_configured": not _is_placeholder_value(settings.CHATDATA_SECRET),
        "private_key_path": settings.PRIVATE_KEY_PATH,
        "suggestions": [] if os.path.exists(sdk_path) and os.path.exists(settings.PRIVATE_KEY_PATH) else ["检查 WeWorkFinanceSdk.dll 和企微会话存档私钥文件是否存在。"],
    }

    overall = "ok" if all(item.get("status") == "ok" for item in checks.values()) else "degraded"
    return {
        "status": overall,
        "generated_at": datetime.utcnow().isoformat(),
        "checks": checks,
        "deployment_doc": "docs/生产部署与配置清单.md",
    }

def _runtime_health() -> dict:
    checks = {}
    overall = "ok"

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as e:
        checks["postgres"] = {"status": "error", "error": sanitize_text(str(e))}
        overall = "degraded"
    finally:
        db.close()

    if (settings.EMBEDDING_PROVIDER or "").lower() == "ollama":
        try:
            session = requests.Session()
            session.trust_env = settings.HTTP_TRUST_ENV
            response = session.get(
                settings.EMBEDDING_API_URL.rstrip("/") + "/api/tags",
                timeout=settings.KB_HEALTHCHECK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            models = [item.get("name") for item in response.json().get("models", [])]
            checks["embedding"] = {
                "status": "ok" if settings.EMBEDDING_MODEL in models else "warning",
                "provider": settings.EMBEDDING_PROVIDER,
                "url": settings.EMBEDDING_API_URL,
                "model": settings.EMBEDDING_MODEL,
                "model_available": settings.EMBEDDING_MODEL in models,
            }
            if settings.EMBEDDING_MODEL not in models and overall == "ok":
                overall = "degraded"
        except Exception as e:
            checks["embedding"] = {
                "status": "error",
                "provider": settings.EMBEDDING_PROVIDER,
                "url": settings.EMBEDDING_API_URL,
                "model": settings.EMBEDDING_MODEL,
                "error": sanitize_text(str(e)),
            }
            overall = "degraded"
    else:
        checks["embedding"] = {
            "status": "configured",
            "provider": settings.EMBEDDING_PROVIDER,
            "model": settings.EMBEDDING_MODEL,
        }

    checks["runtime"] = {
        "status": "ok",
        "http_trust_env": settings.HTTP_TRUST_ENV,
        "llm1_timeout_seconds": settings.LLM1_TIMEOUT_SECONDS,
        "llm2_timeout_seconds": settings.LLM2_TIMEOUT_SECONDS,
        "embedding_timeout_seconds": settings.EMBEDDING_TIMEOUT_SECONDS,
        "slow_request_ms": settings.SLOW_REQUEST_MS,
        "log_desensitize_enabled": settings.LOG_DESENSITIZE_ENABLED,
    }
    return {
        "status": overall,
        "service": "qw-ai-sales-assist",
        "generated_at": datetime.utcnow().isoformat(),
        "checks": checks,
    }

@app.get("/health")
async def health_check():
    return _runtime_health()

@app.get("/api/health/ready")
async def readiness_check():
    return _runtime_health()

@app.get("/api/system/config_check")
async def get_system_config_check():
    return _system_config_check()

@app.post("/api/kb/documents/{document_id}/publish")
async def publish_kb_document(
    document_id: str,
    payload: KnowledgePublishRequest | None = None,
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    _validate_documents_publishable(db, [doc])
    publish_payload = payload or KnowledgePublishRequest()
    gate_report = await _ensure_publish_gate(
        [doc],
        db,
        force=publish_payload.force,
        force_reason=publish_payload.force_reason,
        operator=publish_payload.operator,
    )
    doc.version_no = _next_publish_version_no(db, str(doc.document_id), doc.version_no)
    _create_version_snapshot(
        db,
        doc,
        action="publish",
        operator=publish_payload.operator,
        note=publish_payload.force_reason if publish_payload.force else None,
        version_no=doc.version_no,
    )
    updated_chunks, updated_pricing_rules = _sync_related_status(db, doc, "active", "approved")
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
        "gate_report": gate_report,
        "force_published": publish_payload.force,
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

@app.post("/api/kb/documents/{document_id}/restore/{version_no}")
async def restore_kb_document_version(document_id: str, version_no: int, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    snapshot = db.query(KnowledgeVersionSnapshot).filter(
        KnowledgeVersionSnapshot.document_id == document_id,
        KnowledgeVersionSnapshot.version_no == version_no,
    ).order_by(KnowledgeVersionSnapshot.created_at.desc()).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Knowledge version snapshot not found")
    restore_report = _restore_document_from_snapshot(db, doc, snapshot)
    db.commit()
    db.refresh(doc)
    return {
        "status": "success",
        "document": _doc_to_dict(doc),
        "restore_report": restore_report,
        "version_snapshot": _version_snapshot_to_dict(snapshot),
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
    if status == "active":
        _validate_documents_publishable(db, docs)
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
    _validate_documents_publishable(db, docs)
    gate_report = await _ensure_publish_gate(
        docs,
        db,
        force=payload.force,
        force_reason=payload.force_reason,
        operator=payload.operator,
    )
    for doc in docs:
        doc.version_no = _next_publish_version_no(db, str(doc.document_id), doc.version_no)
        _create_version_snapshot(
            db,
            doc,
            action="publish",
            operator=payload.operator,
            note=payload.force_reason if payload.force else None,
            version_no=doc.version_no,
        )
    result = _bulk_set_documents_status(db, docs, "active", "approved")
    return {"status": "success", **result, "gate_report": gate_report, "force_published": payload.force}

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
    _validate_documents_publishable(db, docs)
    gate_report = await _ensure_publish_gate(docs, db, force=False, operator="import_batch_publish")
    for doc in docs:
        doc.version_no = _next_publish_version_no(db, str(doc.document_id), doc.version_no)
        _create_version_snapshot(
            db,
            doc,
            action="publish",
            operator="import_batch_publish",
            version_no=doc.version_no,
        )
    updated_chunks, updated_pricing_rules = set_documents_status(db, docs, "active", "approved")
    return {
        "status": "success",
        "import_batch": import_batch,
        "updated_documents": len(docs),
        "updated_chunks": updated_chunks,
        "updated_pricing_rules": updated_pricing_rules,
        "gate_report": gate_report,
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

@app.post("/api/kb/import/excel/preview")
async def preview_kb_excel_import(
    file: UploadFile = File(...),
    import_type: str = Form("faq"),
):
    """统一知识 Excel 预览：只解析和校验，不写入数据库。"""
    filename = file.filename or "kb_import.xlsx"
    raw = await file.read()
    parsed = parse_kb_excel_import(raw, filename, import_type)
    return {
        "status": "success",
        "filename": parsed["filename"],
        "sheet": parsed["sheet"],
        "import_type": parsed["import_type"],
        "import_type_label": parsed["import_type_label"],
        "header_row": parsed["header_row"],
        "valid_count": len(parsed["valid_rows"]),
        "skipped_count": len(parsed["skipped"]),
        "failed_count": len(parsed["failed"]),
        "rows": [_excel_item_preview(item) for item in parsed["valid_rows"][:200]],
        "skipped": parsed["skipped"],
        "failed": parsed["failed"],
    }

def _commit_kb_excel_import_raw(
    db: Session,
    *,
    raw: bytes,
    filename: str,
    import_type: str,
    owner: str,
    report: Any = None,
) -> dict:
    parsed = parse_kb_excel_import(raw, filename, import_type)
    import_batch = f"{import_type}_excel_{uuid.uuid4().hex[:12]}"
    created = []
    failed = list(parsed["failed"])
    valid_rows = parsed["valid_rows"]
    total_rows = max(len(valid_rows), 1)

    for index, item in enumerate(valid_rows, start=1):
        if report:
            report(
                progress=min(95, round(index * 100 / total_rows)),
                summary=f"importing row {item['row']}",
                result_patch={"current_row": item["row"], "total_rows": len(valid_rows)},
            )
        title = item["title"]
        content = item["content"]
        embedding = EmbeddingService.embed(f"{title}\n{content}")
        if not embedding:
            failed.append({"row": item["row"], "title": title, "errors": ["embedding_failed"]})
            continue

        document = KnowledgeDocument(
            title=title,
            knowledge_type=item["knowledge_type"],
            business_line=item["business_line"],
            sub_service=item.get("sub_service"),
            source_type=f"excel_{import_type}",
            source_ref=f"{filename} / {parsed['sheet']} / row {item['row']}",
            source_meta={
                "filename": filename,
                "sheet": parsed["sheet"],
                "row": item["row"],
                "import_type": import_type,
            },
            status="draft",
            owner=owner,
            import_batch=import_batch,
            effective_from=item.get("effective_from"),
            effective_to=item.get("effective_to"),
            risk_level=item["risk_level"],
            review_required=True,
            review_status="pending",
            tags=item["tags"],
        )
        db.add(document)
        db.flush()

        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=1,
            chunk_type=item["chunk_type"],
            title=title,
            content=content,
            keyword_text=f"{title}\n{content}",
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            priority=item["priority"],
            business_line=item["business_line"],
            sub_service=item.get("sub_service"),
            knowledge_type=item["knowledge_type"],
            language_pair=item.get("language_pair"),
            service_scope=item.get("service_scope"),
            region=item.get("region"),
            customer_tier=item.get("customer_tier"),
            structured_tags=item["tags"],
            status="draft",
            effective_from=item.get("effective_from"),
            effective_to=item.get("effective_to"),
        )
        db.add(chunk)
        db.flush()

        pricing_rule = None
        if item.get("pricing_rule"):
            pricing_rule_payload = dict(item["pricing_rule"])
            pricing_rule_payload["source_ref"] = pricing_rule_payload.get("source_ref") or document.source_ref
            pricing_rule = _create_pricing_rule(db, document, chunk, pricing_rule_payload)

        created.append({
            "row": item["row"],
            "document_id": str(document.document_id),
            "chunk_id": str(chunk.chunk_id),
            "pricing_rule_created": bool(pricing_rule),
            "title": title,
            "knowledge_type": item["knowledge_type"],
            "business_line": item["business_line"],
            "risk_level": item["risk_level"],
        })

    db.commit()
    logger.info("KB_EXCEL_IMPORT %s", json.dumps({
        "filename": filename,
        "import_type": import_type,
        "import_batch": import_batch,
        "created": len(created),
        "skipped": len(parsed["skipped"]),
        "failed": len(failed),
    }, ensure_ascii=False))

    return {
        "status": "success",
        "filename": filename,
        "sheet": parsed["sheet"],
        "import_type": import_type,
        "import_batch": import_batch,
        "created_count": len(created),
        "skipped_count": len(parsed["skipped"]),
        "failed_count": len(failed),
        "created": created,
        "skipped": parsed["skipped"],
        "failed": failed,
    }

def _run_excel_import_job(report: Any, payload_data: dict) -> dict:
    temp_path = payload_data["temp_path"]
    filename = payload_data["filename"]
    import_type = payload_data["import_type"]
    owner = payload_data.get("owner") or "kb_excel_import"
    with open(temp_path, "rb") as f:
        raw = f.read()
    db = SessionLocal()
    try:
        result = _commit_kb_excel_import_raw(
            db,
            raw=raw,
            filename=filename,
            import_type=import_type,
            owner=owner,
            report=report,
        )
    finally:
        db.close()
        try:
            os.remove(temp_path)
        except OSError:
            pass
    return result

@app.post("/api/kb/import/excel/commit")
async def commit_kb_excel_import(
    file: UploadFile = File(...),
    import_type: str = Form("faq"),
    owner: str = Form("kb_excel_import"),
    db: Session = Depends(get_db),
):
    """统一知识 Excel 确认导入：合法行写入 draft，等待审核发布。"""
    filename = file.filename or "kb_import.xlsx"
    raw = await file.read()
    return _commit_kb_excel_import_raw(db, raw=raw, filename=filename, import_type=import_type, owner=owner)

@app.post("/api/kb/import/excel/commit_async")
async def commit_kb_excel_import_async(
    file: UploadFile = File(...),
    import_type: str = Form("faq"),
    owner: str = Form("kb_excel_import"),
    db: Session = Depends(get_db),
):
    filename = file.filename or "kb_import.xlsx"
    raw = await file.read()
    temp_filename = f"{uuid.uuid4().hex}_{filename}"
    temp_path = os.path.join(_job_payload_dir(), temp_filename)
    with open(temp_path, "wb") as f:
        f.write(raw)
    payload = {
        "temp_path": temp_path,
        "filename": filename,
        "import_type": import_type,
        "owner": owner,
    }
    job = _create_job_task(
        db,
        job_type="kb_excel_import",
        task_payload=payload,
        summary=f"queued excel import {filename}",
    )
    db.commit()
    db.refresh(job)
    start_job(str(job.job_id), _run_excel_import_job, payload)
    return {"status": "queued", "job": _job_to_dict(job)}

@app.post("/api/kb/extract/from_messages")
async def extract_kb_candidates_from_messages(payload: KnowledgeExtractFromMessagesRequest, db: Session = Depends(get_db)):
    records = []
    if payload.session_id:
        logs = (
            db.query(MessageLog)
            .filter(MessageLog.user_id == payload.session_id)
            .order_by(MessageLog.timestamp.asc(), MessageLog.id.asc())
            .limit(max(1, min(payload.max_messages, 200)))
            .all()
        )
        if not logs:
            raise HTTPException(status_code=404, detail="No messages found for session")
        transcript = "\n".join(
            f"{'客户' if log.sender_type == 'customer' else '我方'}：{sanitize_text(log.content or '')}"
            for log in logs
        )
        records.append({
            "title": payload.title or f"会话抽取 {payload.session_id}",
            "content": transcript,
            "session_id": payload.session_id,
            "message_count": len(logs),
        })
    elif payload.messages:
        for index, message in enumerate(payload.messages, start=1):
            text_value = sanitize_text((message or "").strip())
            if not text_value:
                continue
            records.append({
                "title": f"{payload.title or '历史资料抽取'} #{index}",
                "content": text_value,
            })
    else:
        raise HTTPException(status_code=400, detail="session_id 或 messages 至少提供一个")

    created = _extract_candidates_from_records(
        db,
        records,
        source_type=payload.source_type if payload.source_type in KB_LABELS["candidate_source_type"] else "message_extract",
        owner=payload.owner or "kb_extract",
        operator=payload.operator or "frontend_extract",
        source_ref_prefix=payload.session_id or payload.source_type,
        max_candidates=max(1, min(payload.max_candidates, 100)),
    )
    db.commit()
    for item in created:
        db.refresh(item)
    return {
        "status": "success",
        "source_type": payload.source_type,
        "created_count": len(created),
        "candidates": [_candidate_to_dict(item) for item in created],
    }

@app.post("/api/kb/extract/from_email_excel")
async def extract_kb_candidates_from_email_excel(
    file: UploadFile = File(...),
    owner: str = Form("kb_extract"),
    operator: str = Form("frontend_extract"),
    max_candidates: int = Form(20),
    db: Session = Depends(get_db),
):
    filename = file.filename or "email_extract.xlsx"
    raw = await file.read()
    try:
        records = EmailImportService.parse_file(raw, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not records:
        raise HTTPException(status_code=400, detail="未解析到可抽取邮件记录")
    created = _extract_candidates_from_records(
        db,
        records,
        source_type="email_excel",
        owner=owner,
        operator=operator,
        source_ref_prefix=filename,
        max_candidates=max(1, min(int(max_candidates or 20), 100)),
    )
    db.commit()
    for item in created:
        db.refresh(item)
    return {
        "status": "success",
        "filename": filename,
        "source_rows": len(records),
        "created_count": len(created),
        "candidates": [_candidate_to_dict(item) for item in created],
    }

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
      "pricing_rule": {
        "unit": "per_1000_chars|per_project|per_hour|per_day",
        "currency": "CNY",
        "price_min": null,
        "price_max": null,
        "min_charge": null,
        "urgent_multiplier": null,
        "tax_policy": null
      },
      "tags": {{}}
    }}
  ]
}}

字段约束：
- knowledge_type 只能使用 capability、pricing、process、faq。
- business_line 只能使用 general、translation、printing、exhibition。
- 价格、费用、折扣、税费、合同、承诺、赔付类内容 risk_level 必须为 high 且 review_required=true。
- 一条 chunk 只能表达一个知识点；如果一句话里有报价、最低收费、加急规则，必须拆成多条。
- knowledge_type=pricing 时必须尽量输出 pricing_rule；无法确定价格数字时保留 null，但不能编造数字。
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
        pricing_rule = infer_pricing_rule_candidate(
            title=title,
            content=content,
            business_line=business_line or payload.business_line,
            language_pair=language_pair,
            service_scope=service_scope,
            raw_pricing_rule=raw_chunk.get("pricing_rule"),
        )
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
            pricing_rule=pricing_rule,
        ))

    if not chunks_payload:
        raise HTTPException(status_code=422, detail="LLM 未返回可入库的有效切片")

    import_batch = f"assist_text_{uuid.uuid4().hex[:12]}"
    document_knowledge_type = "pricing" if all(item.knowledge_type == "pricing" for item in chunks_payload) else "faq"
    document_risk_level = "high" if any(item.knowledge_type == "pricing" or is_pricing_text(item.title, item.content, item.knowledge_type) for item in chunks_payload) else "medium"
    document = KnowledgeDocument(
        title=payload.title,
        knowledge_type=document_knowledge_type,
        business_line=payload.business_line,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        source_meta={"assist_provider": settings.KB_LLM_ASSIST_PROVIDER, "raw_content_chars": len(payload.content)},
        status="draft",
        owner=payload.owner or "kb_assisted_text",
        import_batch=import_batch,
        risk_level=document_risk_level,
        review_required=True,
        review_status="pending",
        tags={"assist_import": True},
    )
    db.add(document)
    db.flush()

    created_chunks = []
    created_pricing_rules = []
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
        db.flush()
        pricing_rule_payload = item.pricing_rule or infer_pricing_rule_candidate(
            item.title,
            item.content,
            item.business_line,
            item.language_pair,
            item.service_scope,
            item.customer_tier,
        )
        pricing_rule = _create_pricing_rule(db, document, chunk, pricing_rule_payload)
        if pricing_rule:
            created_pricing_rules.append(pricing_rule)
        created_chunks.append(chunk)

    db.commit()
    db.refresh(document)
    for chunk in created_chunks:
        db.refresh(chunk)
    for rule in created_pricing_rules:
        db.refresh(rule)
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
        "pricing_rules": [_pricing_rule_to_dict(rule) for rule in created_pricing_rules],
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
                # CRM Context
                crm_context = IntentEngine.get_crm_context(user_id)
                # RAG V2
                knowledge = {"status": "skipped_no_core_demand", "hits": [], "evidence_context": {"rules": [], "faqs": [], "cases": []}}
                if summary.core_demand and summary.core_demand != "未明确":
                    query_features = IntentEngine.infer_query_features(summary_json, crm_context)
                    knowledge = IntentEngine.retrieve_knowledge_v2(
                        summary.core_demand,
                        query_features=query_features,
                        top_k=5,
                        request_id=f"manual_llm2_{uuid.uuid4().hex[:12]}",
                        session_id=user_id,
                    )
                # LLM2
                assist_bundle = IntentEngine.generate_sales_assist_bundle(summary_json, knowledge, crm_context)
                assist_content = assist_bundle.get("content")
                if assist_content:
                    IntentEngine.update_knowledge_hit_log_outcome(knowledge.get("log_id"), final_response=assist_content)
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
        crm_context = IntentEngine.get_crm_context(user_id)
        result["crm_info"] = crm_context
        result["crm_status"] = crm_context.get("crm_profile_status")
        
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
                if summary.core_demand and summary.core_demand != "未明确":
                    summary_json = {
                        "topic": summary.topic,
                        "core_demand": summary.core_demand,
                        "key_facts": summary.key_facts,
                        "risks": summary.risks,
                        "fast_track_signals": fast_track_signals,
                    }
                    query_features = IntentEngine.infer_query_features(summary_json, crm_context)
                    knowledge_v2 = IntentEngine.retrieve_knowledge_v2(
                        summary.core_demand,
                        query_features=query_features,
                        top_k=5,
                        request_id=f"analysis_{uuid.uuid4().hex[:12]}",
                        session_id=user_id,
                    )
                    result["knowledge_v2"] = knowledge_v2
                    result["knowledge_status"] = knowledge_v2.get("status")
                    result["knowledge_confidence_score"] = knowledge_v2.get("confidence_score")
                    result["knowledge_manual_review_required"] = knowledge_v2.get("manual_review_required")
                    result["knowledge_evidence_context"] = knowledge_v2.get("evidence_context")
                    result["evidence_refs"] = knowledge_v2.get("evidence_refs") or []
                    result["assist_validation"] = IntentEngine.validate_sales_assist_output(summary.sales_advice_v2, knowledge_v2, crm_context=crm_context)
                 
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
    knowledge_v2 = None
    assist_bundle = None

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
                query_features = IntentEngine.infer_query_features(summary_json, crm_context)
                knowledge_v2 = IntentEngine.retrieve_knowledge_v2(
                    summary.core_demand,
                    query_features=query_features,
                    top_k=5,
                    request_id=f"sidebar_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                )
                knowledge_base = knowledge_v2
                mark_timing("knowledge_retrieve_ms", stage_started)
                knowledge_status = knowledge_v2.get("status", "error")
                stage_status["knowledge_v2"] = knowledge_status
            else:
                knowledge_v2 = {"status": "skipped_no_core_demand", "hits": [], "evidence_context": {"rules": [], "faqs": [], "cases": []}, "evidence_refs": []}
                knowledge_base = knowledge_v2
                knowledge_status = "skipped_no_core_demand"

            stage_started = perf_counter()
            assist_bundle = IntentEngine.generate_sales_assist_bundle(summary_json, knowledge_v2, crm_context)
            assist_content = assist_bundle.get("content")
            mark_timing("llm2_generate_ms", stage_started)
            if assist_content:
                IntentEngine.update_knowledge_hit_log_outcome(knowledge_v2.get("log_id"), final_response=assist_content)
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
                if assist_bundle:
                    result["assist_validation"] = assist_bundle.get("validation")
                    result["evidence_refs"] = assist_bundle.get("evidence_refs") or []
                # 回传检索到的原始知识块参考文档
                if knowledge_base is not None:
                    result["knowledge_v2"] = knowledge_base
                    result["knowledge_base"] = [hit.get("content") for hit in knowledge_base.get("hits", [])] if isinstance(knowledge_base, dict) else knowledge_base
                    if isinstance(knowledge_base, dict):
                        result["knowledge_evidence_context"] = knowledge_base.get("evidence_context")
                        result["evidence_refs"] = result.get("evidence_refs") or knowledge_base.get("evidence_refs") or []
                        result["knowledge_confidence_score"] = knowledge_base.get("confidence_score")
                        result["knowledge_manual_review_required"] = knowledge_base.get("manual_review_required")
                elif summary.core_demand and summary.core_demand != "未明确":
                    stage_started = perf_counter()
                    query_features = IntentEngine.infer_query_features({
                        "topic": summary.topic,
                        "core_demand": summary.core_demand,
                        "key_facts": summary.key_facts,
                        "risks": summary.risks,
                    }, crm_context)
                    knowledge_v2 = IntentEngine.retrieve_knowledge_v2(
                        summary.core_demand,
                        query_features=query_features,
                        top_k=5,
                        request_id=f"sidebar_cache_{uuid.uuid4().hex[:12]}",
                        session_id=session_id,
                    )
                    result["knowledge_v2"] = knowledge_v2
                    result["knowledge_base"] = [hit.get("content") for hit in knowledge_v2.get("hits", [])]
                    result["knowledge_evidence_context"] = knowledge_v2.get("evidence_context")
                    result["evidence_refs"] = knowledge_v2.get("evidence_refs") or []
                    validation = IntentEngine.validate_sales_assist_output(summary.sales_advice_v2, knowledge_v2, crm_context=crm_context)
                    result["assist_validation"] = validation
                    result["knowledge_confidence_score"] = knowledge_v2.get("confidence_score")
                    result["knowledge_manual_review_required"] = knowledge_v2.get("manual_review_required")
                    mark_timing("knowledge_retrieve_ms", stage_started)
                    knowledge_status = knowledge_v2.get("status", "error")
                else:
                    result["knowledge_base"] = []
                    result["knowledge_v2"] = {"status": "skipped_no_core_demand", "hits": [], "evidence_refs": []}
                    result["evidence_refs"] = []
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

def archive_sdk_status():
    from archive_service import ArchiveService
    return {
        "status": "running", 
        "archive_sdk": ArchiveService.get_token_status()
    }
