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
    user_id = Column(String(120), index=True)    # 会话ID，需容纳销售ID + external_userid
    sender_type = Column(String(20))              # customer / sales
    content = Column(Text)                         # 消息原文
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    is_mock = Column(Boolean, default=False)       # 是否为模拟数据

class IntentSummary(Base):
    """Schema V1 结构化摘要表"""
    __tablename__ = "intent_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(120), index=True)
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
    sales_advice_compare_v2 = Column(Text)  # LLM2 对比模型话术持久化

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
    library_type = Column(String(20), nullable=False, default="reference")
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
    library_type = Column(String(20), nullable=False, default="reference")
    allowed_for_generation = Column(Boolean, nullable=False, default=False)
    usable_for_reply = Column(Boolean, nullable=False, default=False)
    publishable = Column(Boolean, nullable=False, default=False)
    topic_clarity_score = Column(Numeric(6, 4), nullable=True)
    completeness_score = Column(Numeric(6, 4), nullable=True)
    reusability_score = Column(Numeric(6, 4), nullable=True)
    evidence_reliability_score = Column(Numeric(6, 4), nullable=True)
    useful_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    feedback_count = Column(Integer, nullable=False, default=0)
    positive_feedback_count = Column(Integer, nullable=False, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    quality_notes = Column(JSON, nullable=True)
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
    library_type = Column(String(20), nullable=False, default="reference")
    allowed_for_generation = Column(Boolean, nullable=False, default=False)
    usable_for_reply = Column(Boolean, nullable=False, default=False)
    publishable = Column(Boolean, nullable=False, default=False)
    topic_clarity_score = Column(Numeric(6, 4), nullable=True)
    completeness_score = Column(Numeric(6, 4), nullable=True)
    reusability_score = Column(Numeric(6, 4), nullable=True)
    evidence_reliability_score = Column(Numeric(6, 4), nullable=True)
    useful_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    feedback_count = Column(Integer, nullable=False, default=0)
    positive_feedback_count = Column(Integer, nullable=False, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    quality_notes = Column(JSON, nullable=True)
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

class ThreadBusinessFact(Base):
    """线程业务事实层：沉淀业务状态、关键事实、附件汇总与自动回复门禁。"""
    __tablename__ = "thread_business_fact"

    fact_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(String(120), nullable=False, unique=True)
    thread_id = Column(String(120), nullable=False)
    external_userid = Column(String(120), nullable=True)
    sales_userid = Column(String(120), nullable=True)
    topic = Column(String(255), nullable=True)
    core_demand = Column(Text, nullable=True)
    scenario_label = Column(String(80), nullable=True)
    intent_label = Column(String(80), nullable=True)
    language_style = Column(String(80), nullable=True)
    business_state = Column(String(50), nullable=True)
    stage_signals = Column(JSON, nullable=True)
    merged_facts = Column(JSON, nullable=True)
    attachment_summary = Column(JSON, nullable=True)
    fact_source = Column(JSON, nullable=True)
    quality_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    outcome_feedback = Column(JSON, nullable=True)
    usable_for_reply = Column(Boolean, nullable=False, default=False)
    allowed_for_generation = Column(Boolean, nullable=False, default=False)
    reply_guard_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_tbf_session", "session_id"),
        Index("idx_tbf_state_updated", "business_state", "updated_at"),
    )

class EmailThreadAsset(Base):
    """邮件兼容主表：承接邮件原始资产并与线程事实层打通。"""
    __tablename__ = "email_thread_asset"

    email_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    source_type = Column(String(50), nullable=False, default="email_excel")
    source_ref = Column(String(255), nullable=False, unique=True)
    import_batch = Column(String(120), nullable=True)
    session_id = Column(String(120), nullable=True)
    thread_id = Column(String(120), nullable=False)
    external_userid = Column(String(120), nullable=True)
    sales_userid = Column(String(120), nullable=True)
    fact_id = Column(UUID(as_uuid=False), ForeignKey("thread_business_fact.fact_id"), nullable=True)
    subject = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    sender = Column(String(255), nullable=True)
    receiver = Column(String(255), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    sent_at_raw = Column(String(80), nullable=True)
    scenario_label = Column(String(80), nullable=True)
    intent_label = Column(String(80), nullable=True)
    language_style = Column(String(80), nullable=True)
    business_state = Column(String(50), nullable=True)
    library_type = Column(String(20), nullable=False, default="reference")
    quality_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    feedback_count = Column(Integer, nullable=False, default=0)
    positive_feedback_count = Column(Integer, nullable=False, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    usable_for_reply = Column(Boolean, nullable=False, default=False)
    allowed_for_generation = Column(Boolean, nullable=False, default=False)
    publishable = Column(Boolean, nullable=False, default=False)
    source_snapshot = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="ingested")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_eta_session", "session_id"),
        Index("idx_eta_thread", "thread_id"),
        Index("idx_eta_status_created", "status", "created_at"),
    )

class EmailFragmentAsset(Base):
    """邮件兼容切片表：承接邮件功能片段与优秀回复片段。"""
    __tablename__ = "email_fragment_asset"

    fragment_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    email_id = Column(UUID(as_uuid=False), ForeignKey("email_thread_asset.email_id"), nullable=True)
    candidate_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_candidate.candidate_id"), nullable=True)
    log_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_hit_logs.log_id"), nullable=True)
    session_id = Column(String(120), nullable=True)
    thread_id = Column(String(120), nullable=False)
    source_type = Column(String(50), nullable=False, default="email_excel")
    source_ref = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    function_fragment = Column(String(50), nullable=True)
    scenario_label = Column(String(80), nullable=True)
    intent_label = Column(String(80), nullable=True)
    language_style = Column(String(80), nullable=True)
    library_type = Column(String(20), nullable=False, default="reference")
    allowed_for_generation = Column(Boolean, nullable=False, default=False)
    usable_for_reply = Column(Boolean, nullable=False, default=False)
    publishable = Column(Boolean, nullable=False, default=False)
    topic_clarity_score = Column(Numeric(6, 4), nullable=True)
    completeness_score = Column(Numeric(6, 4), nullable=True)
    reusability_score = Column(Numeric(6, 4), nullable=True)
    evidence_reliability_score = Column(Numeric(6, 4), nullable=True)
    useful_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    feedback_count = Column(Integer, nullable=False, default=0)
    positive_feedback_count = Column(Integer, nullable=False, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    quality_notes = Column(JSON, nullable=True)
    source_snapshot = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="ready")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_efa_email", "email_id"),
        Index("idx_efa_session", "session_id"),
        Index("idx_efa_source_ref", "source_type", "source_ref"),
        Index("idx_efa_status_quality", "status", "usable_for_reply", "useful_score"),
    )

class EmailEffectFeedback(Base):
    """邮件效果表：记录片段与线程级反馈回流。"""
    __tablename__ = "email_effect_feedback"

    feedback_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    email_id = Column(UUID(as_uuid=False), ForeignKey("email_thread_asset.email_id"), nullable=True)
    fragment_id = Column(UUID(as_uuid=False), ForeignKey("email_fragment_asset.fragment_id"), nullable=True)
    candidate_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_candidate.candidate_id"), nullable=True)
    log_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_hit_logs.log_id"), nullable=True)
    session_id = Column(String(120), nullable=True)
    thread_id = Column(String(120), nullable=True)
    feedback_status = Column(String(50), nullable=False)
    feedback_note = Column(Text, nullable=True)
    feedback_payload = Column(JSON, nullable=True)
    delta_score = Column(Numeric(6, 4), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_eef_session_created", "session_id", "created_at"),
        Index("idx_eef_fragment_created", "fragment_id", "created_at"),
    )

class ModelTrainingSample(Base):
    """训练样本准备表：为 embedding 与小模型微调积累高质量导出样本。"""
    __tablename__ = "model_training_sample"

    sample_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    sample_key = Column(String(64), nullable=False, unique=True)
    sample_type = Column(String(50), nullable=False)
    source_table = Column(String(50), nullable=False)
    source_id = Column(String(64), nullable=True)
    source_type = Column(String(50), nullable=True)
    source_ref = Column(String(255), nullable=True)
    instruction = Column(Text, nullable=True)
    input_text = Column(Text, nullable=False)
    target_text = Column(Text, nullable=True)
    sample_metadata = Column(JSON, nullable=True)
    quality_score = Column(Numeric(6, 4), nullable=True)
    effect_score = Column(Numeric(6, 4), nullable=True)
    exportable = Column(Boolean, nullable=False, default=False)
    review_status = Column(String(20), nullable=False, default="ready")
    export_status = Column(String(20), nullable=False, default="pending")
    last_export_path = Column(String(500), nullable=True)
    exported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_mts_type_review", "sample_type", "review_status"),
        Index("idx_mts_export_status", "export_status", "created_at"),
        Index("idx_mts_source_ref", "source_table", "source_ref"),
    )

class KnowledgeVersionSnapshot(Base):
    """知识版本快照：发布前保存文档、切片、报价规则的完整恢复包。"""
    __tablename__ = "knowledge_version_snapshot"

    snapshot_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(UUID(as_uuid=False), ForeignKey("knowledge_document.document_id"), nullable=False)
    version_no = Column(Integer, nullable=False)
    action = Column(String(30), nullable=False, default="publish")  # publish/restore/manual
    operator = Column(String(100), nullable=True)
    note = Column(Text, nullable=True)
    snapshot_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_kvs_doc_version", "document_id", "version_no"),
        Index("idx_kvs_created_at", "created_at"),
    )

class JobTask(Base):
    """异步任务表：承接回归、导入和抽取等耗时任务。"""
    __tablename__ = "job_task"

    job_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="queued")  # queued/running/success/failed
    progress = Column(Integer, nullable=False, default=0)
    summary = Column(String(255), nullable=True)
    task_payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_of = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_job_task_status_created", "status", "created_at"),
        Index("idx_job_task_type_created", "job_type", "created_at"),
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
