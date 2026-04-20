from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, JSON, text, Boolean,
    ForeignKey, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
from config import settings

Base = declarative_base()

class MessageLog(Base):
    """对话日志表"""
    __tablename__ = "message_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), index=True)     # 外部联系人ID或员工ID
    sender_type = Column(String(20))              # customer / sales
    content = Column(Text)                         # 消息原文
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    is_mock = Column(Boolean, default=False)       # 是否为模拟数据

class IntentSummary(Base):
    """Schema V1 结构化摘要表"""
    __tablename__ = "intent_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), index=True)
    summarized_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 按照 Schema V1 分字段存储
    topic = Column(String(200))          # 当前主线话题
    core_demand = Column(Text)           # 客户核心诉求
    key_facts = Column(JSON)             # 关键事实 (JSON)
    todo_items = Column(JSON)            # 待跟进事项 (JSON)
    risks = Column(Text)                 # 风险/顾虑
    to_be_confirmed = Column(Text)       # 待确认信息
    status = Column(String(50))          # 对话状态 (枚举)
    sales_advice_v2 = Column(Text)       # LLM2 的金牌销售话术持久化

class KnowledgeBase(Base):
    """销售知识库/回复模板"""
    __tablename__ = "knowledge_base"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))          # 标题/主题
    content = Column(Text)               # 知识内容/回复模板原文
    category = Column(String(50))        # 类别 (如报价, 售后)
    # embedding = Column(Vector(1024))     # 原 Vector 类型由于环境缺少 pgvector 扩展暂不可用
    embedding = Column(JSON, nullable=True) # 降级为 JSON 或 Text 存储向量数组，以保证 Windows 下 DDL 成功

class KnowledgeDocument(Base):
    """知识文档主表：记录来源、版本、发布状态和生效范围"""
    __tablename__ = "knowledge_document"

    document_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    title = Column(String(255), nullable=False)
    knowledge_type = Column(String(50), nullable=False)  # capability/pricing/process/faq
    business_line = Column(String(50), nullable=False)   # translation/printing/exhibition/general
    sub_service = Column(String(80), nullable=True)
    source_type = Column(String(50), nullable=False)     # excel/word/pdf/markdown/manual/faq_doc/sop_doc
    source_ref = Column(String(500), nullable=True)
    source_meta = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft/active/archived/rejected
    version_no = Column(Integer, nullable=False, default=1)
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    owner = Column(String(100), nullable=True)
    import_batch = Column(String(100), nullable=True)
    risk_level = Column(String(20), nullable=False, default="medium")
    review_required = Column(Boolean, nullable=False, default=True)
    review_status = Column(String(20), nullable=False, default="pending")
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_kd_status_business_type", "status", "business_line", "knowledge_type"),
        Index("idx_kd_import_batch", "import_batch"),
    )

class KnowledgeChunk(Base):
    """知识切片表：实际参与检索的业务可调用知识单元"""
    __tablename__ = "knowledge_chunk"

    chunk_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_document.document_id"), nullable=False)
    chunk_no = Column(Integer, nullable=False, default=1)
    chunk_type = Column(String(50), nullable=False)      # rule/faq/example/constraint/definition
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    keyword_text = Column(Text, nullable=True)
    embedding = Column(JSON, nullable=True)
    embedding_provider = Column(String(50), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=False, default=50)
    retrieval_weight = Column(Numeric(6, 3), nullable=False, default=1.000)
    business_line = Column(String(50), nullable=False)
    sub_service = Column(String(80), nullable=True)
    knowledge_type = Column(String(50), nullable=False)
    language_pair = Column(String(50), nullable=True)
    service_scope = Column(String(80), nullable=True)
    region = Column(String(80), nullable=True)
    customer_tier = Column(String(80), nullable=True)
    structured_tags = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_kc_status_business_type", "status", "business_line", "knowledge_type"),
        Index("idx_kc_scope", "language_pair", "service_scope", "customer_tier"),
        Index("idx_kc_document", "document_id"),
    )

class PricingRule(Base):
    """结构化报价规则表：防止价格、单位、币种等关键字段只存在文本中"""
    __tablename__ = "pricing_rule"

    rule_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_document.document_id"), nullable=False)
    chunk_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_chunk.chunk_id"), nullable=True)
    business_line = Column(String(50), nullable=False)
    sub_service = Column(String(80), nullable=True)
    language_pair = Column(String(50), nullable=True)
    service_scope = Column(String(80), nullable=True)
    unit = Column(String(50), nullable=False)       # per_1000_chars/per_hour/per_day/per_project
    currency = Column(String(10), nullable=False, default="CNY")
    price_min = Column(Numeric(12, 2), nullable=True)
    price_max = Column(Numeric(12, 2), nullable=True)
    urgent_multiplier = Column(Numeric(6, 3), nullable=True)
    tax_policy = Column(String(50), nullable=True)
    min_charge = Column(Numeric(12, 2), nullable=True)
    customer_tier = Column(String(80), nullable=True)
    region = Column(String(80), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    version_no = Column(Integer, nullable=False, default=1)
    source_ref = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_pr_status_business", "status", "business_line"),
        Index("idx_pr_scope", "language_pair", "service_scope", "customer_tier"),
    )

class KnowledgeCandidate(Base):
    """知识候选池：承接销售反馈与历史资料抽取结果，编辑后再转为 draft 知识。"""
    __tablename__ = "knowledge_candidate"

    candidate_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    knowledge_type = Column(String(50), nullable=False, default="faq")
    chunk_type = Column(String(50), nullable=False, default="faq")
    business_line = Column(String(50), nullable=False, default="general")
    sub_service = Column(String(80), nullable=True)
    language_pair = Column(String(50), nullable=True)
    service_scope = Column(String(80), nullable=True)
    region = Column(String(80), nullable=True)
    customer_tier = Column(String(80), nullable=True)
    priority = Column(Integer, nullable=False, default=50)
    risk_level = Column(String(20), nullable=False, default="medium")
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    pricing_rule = Column(JSON, nullable=True)
    source_type = Column(String(50), nullable=False, default="feedback")
    source_ref = Column(String(255), nullable=True)
    source_snapshot = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="candidate")
    owner = Column(String(100), nullable=True)
    operator = Column(String(100), nullable=True)
    review_notes = Column(Text, nullable=True)
    promoted_document_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_document.document_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_kcand_status_created", "status", "created_at"),
        Index("idx_kcand_source", "source_type", "source_ref"),
        Index("idx_kcand_business_type", "business_line", "knowledge_type"),
    )

class KnowledgeHitLog(Base):
    """知识检索命中日志：用于追溯命中、未命中和检索质量"""
    __tablename__ = "knowledge_hit_logs"

    log_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(String(100), nullable=True)
    session_id = Column(String(100), nullable=True)
    query_text = Column(Text, nullable=False)
    query_features = Column(JSON, nullable=True)
    filters_used = Column(JSON, nullable=True)
    hit_chunk_ids = Column(JSON, nullable=True)
    scores = Column(JSON, nullable=True)
    no_hit_reason = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="not_started")
    retrieval_quality = Column(String(50), nullable=True)
    confidence_score = Column(Numeric(8, 6), nullable=True)
    insufficient_info = Column(Boolean, nullable=False, default=False)
    manual_review_required = Column(Boolean, nullable=False, default=False)
    final_response = Column(Text, nullable=True)
    manual_feedback = Column(JSON, nullable=True)
    feedback_status = Column(String(50), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_khl_created_at", "created_at"),
        Index("idx_khl_request", "request_id"),
        Index("idx_khl_session", "session_id"),
    )

# 初始化数据库连接
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    try:
        # 彻底移除 vector 扩展激活逻辑，因宿主机环境完全不支持
        # with engine.connect() as conn:
        #     conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        #     conn.commit()
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"数据库初始化基础表结构失败: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
