from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, JSON, text, Boolean,
    ForeignKey, Numeric, Index, UniqueConstraint
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
    archive_msg_id = Column(String(120), index=True, nullable=True)  # 企微存档原始消息唯一键
    archive_seq = Column(String(40), index=True, nullable=True)      # 企微存档增量游标 seq

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
    llm1_compare_summary = Column(JSON, nullable=True)  # LLM1 对比模型结构化摘要
    llm1_compare_prompt_trace = Column(JSON, nullable=True)  # LLM1 对比模型 prompt 存证
    crm_info = Column(JSON, nullable=True)
    crm_status = Column(String(50), nullable=True)
    thread_business_fact = Column(JSON, nullable=True)
    knowledge_log_id = Column(String(120), nullable=True)
    knowledge_v2 = Column(JSON, nullable=True)
    knowledge_external_api = Column(JSON, nullable=True)
    knowledge_status = Column(String(50), nullable=True)
    knowledge_confidence_score = Column(Numeric(8, 6), nullable=True)
    knowledge_manual_review_required = Column(Boolean, nullable=False, default=False)
    sales_advice_v2 = Column(Text)       # LLM2 的金牌销售话术持久化
    sales_advice_compare_v2 = Column(Text)  # LLM2 对比模型话术持久化
    sales_advice_compare_prompt_trace_v2 = Column(JSON)  # LLM2 对比模型最终 prompt 存证
    reply_style_results_v2 = Column(JSON, nullable=True)  # 多风格 x 多模型候选结果
    reply_scores_v2 = Column(JSON, nullable=True)  # 候选与实际销售回复评分结果
    training_ai = Column(JSON, nullable=True)  # 训练AI(另一条 model-chat 途径)并行回复结果
    assist_validation = Column(JSON, nullable=True)
    assist_compare_validation = Column(JSON, nullable=True)
    stage_status = Column(JSON, nullable=True)

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
    business_stage = Column(String(80), nullable=True)
    business_scenario_code = Column(String(80), nullable=True)
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
        Index("idx_kc_business_scenario", "business_stage", "business_scenario_code"),
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

class ReplyChainSnapshot(Base):
    """企微回复链路节点快照：按客户气泡保留最后一版 7 步结果。"""
    __tablename__ = "reply_chain_snapshot"

    snapshot_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(String(120), nullable=False)
    anchor_message_id = Column(Integer, nullable=False)
    anchor_sender_type = Column(String(20), nullable=False, default="customer")
    anchor_message_time = Column(DateTime, nullable=True)
    anchor_message_text = Column(Text, nullable=True)
    visible_message_ids = Column(JSON, nullable=True)
    latest_dialog_count = Column(Integer, nullable=False, default=0)
    fast_track = Column(JSON, nullable=True)

    topic = Column(String(200), nullable=True)
    core_demand = Column(Text, nullable=True)
    key_facts = Column(JSON, nullable=True)
    todo_items = Column(JSON, nullable=True)
    risks = Column(Text, nullable=True)
    to_be_confirmed = Column(Text, nullable=True)
    status = Column(String(50), nullable=True)
    summarized_at = Column(DateTime, nullable=True)

    crm_info = Column(JSON, nullable=True)
    crm_status = Column(String(50), nullable=True)
    thread_business_fact = Column(JSON, nullable=True)

    knowledge_log_id = Column(String(120), nullable=True)
    knowledge_v2 = Column(JSON, nullable=True)
    knowledge_external_api = Column(JSON, nullable=True)
    knowledge_status = Column(String(50), nullable=True)
    knowledge_confidence_score = Column(Numeric(8, 6), nullable=True)
    knowledge_manual_review_required = Column(Boolean, nullable=False, default=False)

    llm1_compare_summary = Column(JSON, nullable=True)
    llm1_compare_prompt_trace = Column(JSON, nullable=True)
    sales_advice_v2 = Column(Text, nullable=True)
    sales_advice_compare_v2 = Column(Text, nullable=True)
    sales_advice_compare_prompt_trace_v2 = Column(JSON, nullable=True)
    reply_style_results_v2 = Column(JSON, nullable=True)
    reply_scores_v2 = Column(JSON, nullable=True)
    assist_validation = Column(JSON, nullable=True)
    assist_compare_validation = Column(JSON, nullable=True)
    actual_sales_replies = Column(JSON, nullable=True)
    stage_status = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "anchor_message_id", name="uq_reply_chain_snapshot_anchor"),
        Index("idx_reply_chain_snapshot_session_updated", "session_id", "updated_at"),
    )

class ApiAssistInvocation(Base):
    """侧边栏 API 调用快照：按调用时刻固化输出，并在后续补充质量评分。"""
    __tablename__ = "api_assist_invocation"

    invocation_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(String(120), nullable=False)
    requested_session_id = Column(String(120), nullable=True)
    external_userid = Column(String(120), nullable=True)
    sales_userid = Column(String(120), nullable=True)
    anchor_message_id = Column(Integer, nullable=True)
    anchor_message_time = Column(DateTime, nullable=True)
    anchor_message_text = Column(Text, nullable=True)
    visible_message_ids = Column(JSON, nullable=True)
    latest_dialog_count = Column(Integer, nullable=False, default=0)
    trigger_source = Column(String(30), nullable=True, default="api")
    trigger_kind = Column(String(50), nullable=True, default="api_sidebar_assist")
    # 客户端 sidebar 那侧带来的 request_id(中间件 X-Request-ID),用于"客户端 duration_ms 长但服务端 timings 短"时双向对账。
    request_id = Column(String(64), nullable=True, index=True)
    triggered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    stage_status = Column(JSON, nullable=True)
    result_payload = Column(JSON, nullable=False)
    actual_sales_replies = Column(JSON, nullable=True)
    actual_sales_reply_text = Column(Text, nullable=True)
    actual_sales_reply_hash = Column(String(64), nullable=True)
    quality_similarity = Column(JSON, nullable=True)
    quality_score = Column(Numeric(6, 2), nullable=True)
    quality_status = Column(String(50), nullable=True)
    quality_scored_at = Column(DateTime, nullable=True)
    kb1_eval_score = Column(Numeric(6, 2), nullable=True)
    kb1_eval_reason = Column(Text, nullable=True)
    kb2_eval_score = Column(Numeric(6, 2), nullable=True)
    kb2_eval_reason = Column(Text, nullable=True)
    quality_annotations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_api_ai_session_triggered", "session_id", "triggered_at"),
        Index("idx_api_ai_anchor_triggered", "session_id", "anchor_message_id", "triggered_at"),
        Index("idx_api_ai_quality_status", "quality_status", "triggered_at"),
    )

class WecomTriggerRecord(Base):
    """网页人工/Test 触发记录：按每次触发保存一行，用于统计分析。"""
    __tablename__ = "wecom_trigger_record"

    record_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(String(120), nullable=False)
    snapshot_id = Column(String(120), nullable=True)
    run_id = Column(String(40), nullable=True)
    trigger_source = Column(String(30), nullable=False, default="web_manual")
    trigger_kind = Column(String(50), nullable=False)
    requested_step = Column(Integer, nullable=True)
    requested_channel = Column(String(50), nullable=True)
    request_status = Column(String(30), nullable=False, default="queued")
    anchor_message_id = Column(Integer, nullable=True)
    anchor_message_time = Column(DateTime, nullable=True)
    anchor_message_text = Column(Text, nullable=True)
    visible_message_ids = Column(JSON, nullable=True)
    input_messages = Column(JSON, nullable=True)
    recent_customer_messages = Column(JSON, nullable=True)
    latest_dialog_count = Column(Integer, nullable=False, default=0)
    actual_sales_replies = Column(JSON, nullable=True)
    actual_sales_reply_text = Column(Text, nullable=True)
    stage_status = Column(JSON, nullable=True)
    result_payload = Column(JSON, nullable=True)
    request_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    kb1_eval_score = Column(Numeric(6, 2), nullable=True)
    kb1_eval_reason = Column(Text, nullable=True)
    kb2_eval_score = Column(Numeric(6, 2), nullable=True)
    kb2_eval_reason = Column(Text, nullable=True)
    quality_annotations = Column(JSON, nullable=True)
    triggered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_wtr_triggered", "triggered_at"),
        Index("idx_wtr_source_triggered", "trigger_source", "triggered_at"),
        Index("idx_wtr_session_triggered", "session_id", "triggered_at"),
        Index("idx_wtr_run_id", "run_id"),
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
        Index("idx_efa_fewshot_admission", "status", "publishable", "allowed_for_generation", "usable_for_reply", "useful_score"),
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

class CaseLibraryCase(Base):
    """经典案例库：12个场景 x 每场景质量分前5 = 60个案例（独立表，与正式数据不交叉）。"""
    __tablename__ = "case_library_case"

    case_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    scenario_code = Column(String(10), nullable=False)        # S01-S12
    scenario_name = Column(String(80), nullable=False)        # 价格竞争/比价 等
    scenario_rank = Column(Integer, nullable=False)           # 1..5（场景内按质量分排名）
    case_title = Column(String(255), nullable=True)           # 案例标题
    group_key = Column(String(120), nullable=False)
    session_date = Column(DateTime, nullable=False)           # 会话日期
    batch_id = Column(String(120), nullable=True)
    external_userid = Column(String(120), nullable=True)      # 客户真实 external_userid（按 group_key 从原始企微数据找回，用于 CRM 画像）
    slice_ids = Column(JSON, nullable=True)
    row_start = Column(Integer, nullable=True)
    row_end = Column(Integer, nullable=True)
    quality_score_md = Column(Numeric(6, 2), nullable=True)   # 来自 v2.md 的"质量分（最高）"
    core_dialog = Column(JSON, nullable=False)                # 核心对话 [{role, time, content, row_index}]
    context_messages = Column(JSON, nullable=True)            # 核心对话之前15条聊天背景
    md_source_path = Column(String(255), nullable=True)       # 来源 markdown 文件名
    md_section_anchor = Column(String(80), nullable=True)     # 例: S01-03
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("scenario_code", "scenario_rank", name="uq_case_library_scenario_rank"),
        Index("idx_clc_scenario", "scenario_code", "scenario_rank"),
    )


class CaseLibraryDialogueTurn(Base):
    """经典案例库的核心问答轮次，按 case_id 关联回原案例和场景。"""
    __tablename__ = "case_library_dialogue_turn"

    turn_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id = Column(UUID(as_uuid=False), ForeignKey("case_library_case.case_id"), nullable=False)
    scenario_code = Column(String(10), nullable=False)
    scenario_rank = Column(Integer, nullable=False)
    turn_no = Column(Integer, nullable=False)
    group_key = Column(String(120), nullable=False)
    row_start = Column(Integer, nullable=True)
    row_end = Column(Integer, nullable=True)
    customer_text = Column(Text, nullable=True)
    sales_text = Column(Text, nullable=True)
    messages = Column(JSON, nullable=False)
    context_messages = Column(JSON, nullable=True)
    actual_sales_score = Column(Numeric(6, 2), nullable=True)
    actual_sales_scores = Column(JSON, nullable=True)
    score_status = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("case_id", "turn_no", name="uq_case_library_dialogue_turn_no"),
        Index("idx_cldt_case", "case_id", "turn_no"),
        Index("idx_cldt_scenario", "scenario_code", "scenario_rank"),
    )


class CaseIterationRun(Base):
    """案例迭代运行记录：每点击/触发一次跑60个案例为一行。"""
    __tablename__ = "case_iteration_run"

    run_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    version_no = Column(Integer, nullable=False)                # 自增版本号(每次+1)
    git_commit_sha = Column(String(64), nullable=True)
    git_branch = Column(String(120), nullable=True)
    git_short_sha = Column(String(20), nullable=True)
    git_dirty = Column(Boolean, nullable=False, default=False)  # 是否有未提交改动
    changed_paths = Column(JSON, nullable=True)                 # 本次相对上一版改了哪些文件
    change_summary = Column(Text, nullable=True)                # 本次修改说明
    pipeline_config = Column(JSON, nullable=True)               # 本次跑的脚本/Prompt/参数快照
    status = Column(String(20), nullable=False, default="queued")  # queued/running/success/partial/failed
    total_cases = Column(Integer, nullable=False, default=0)
    completed_cases = Column(Integer, nullable=False, default=0)
    success_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    avg_quality_score = Column(Numeric(6, 2), nullable=True)
    min_quality_score = Column(Numeric(6, 2), nullable=True)
    max_quality_score = Column(Numeric(6, 2), nullable=True)
    avg_latency_ms = Column(Integer, nullable=True)
    improvement_analysis = Column(Text, nullable=True)          # 本次得分分析（机器生成基线）
    ai_next_step_plan = Column(Text, nullable=True)             # AI自我测试迭代步骤及要求（机器生成基线）
    # 三个 AI 编码工具各自填写的"分析与下一步建议"——人工填，便于横向对比
    analysis_codex = Column(Text, nullable=True)                # Codex 给出的分析与下一步
    analysis_antigravity = Column(Text, nullable=True)          # Antigravity 给出的分析与下一步
    analysis_claude_code = Column(Text, nullable=True)          # Claude Code 给出的分析与下一步
    analysis_summary = Column(Text, nullable=True)              # 三者填完后 LLM-1 自动生成的汇总
    backup_commit_sha = Column(String(64), nullable=True)       # 完成后自动提交的commit SHA
    backup_status = Column(String(30), nullable=True)
    triggered_by = Column(String(120), nullable=True)
    triggered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_cir_triggered_at", "triggered_at"),
        Index("idx_cir_version_no", "version_no"),
        Index("idx_cir_status", "status", "triggered_at"),
    )


class CaseIterationResult(Base):
    """案例迭代逐轮结果：1 run x case dialogue turns；记录 7 步链路每步快照。"""
    __tablename__ = "case_iteration_result"

    result_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=False), ForeignKey("case_iteration_run.run_id"), nullable=False)
    case_id = Column(UUID(as_uuid=False), ForeignKey("case_library_case.case_id"), nullable=False)
    turn_id = Column(UUID(as_uuid=False), ForeignKey("case_library_dialogue_turn.turn_id"), nullable=True)
    scenario_code = Column(String(10), nullable=False)
    scenario_rank = Column(Integer, nullable=False)
    turn_no = Column(Integer, nullable=True)
    # 7 步骤结果快照
    step1_summary = Column(JSON, nullable=True)         # topic/core_demand/key_facts/todo/risks/status
    step2_crm_info = Column(JSON, nullable=True)
    step3_thread_business_fact = Column(JSON, nullable=True)
    step4_knowledge = Column(JSON, nullable=True)       # knowledge_v2/external/log_id
    step5_llm1_compare = Column(JSON, nullable=True)
    step6_sales_advice = Column(Text, nullable=True)
    step6_compare_advice = Column(Text, nullable=True)
    step7_reply_styles = Column(JSON, nullable=True)    # reply_style_results_v2
    step7_reply_scores = Column(JSON, nullable=True)
    # 关联现有快照便于追溯
    snapshot_id = Column(String(120), nullable=True)
    trigger_record_id = Column(String(120), nullable=True)
    # 评分
    quality_score = Column(Numeric(6, 2), nullable=True)
    kb1_eval_score = Column(Numeric(6, 2), nullable=True)
    kb2_eval_score = Column(Numeric(6, 2), nullable=True)
    quality_status = Column(String(50), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    stage_status = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="queued")  # queued/running/success/failed
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "turn_no", name="uq_case_iter_result_run_case_turn"),
        Index("idx_cir_run_scenario", "run_id", "scenario_code"),
        Index("idx_cir_run_case_turn", "run_id", "case_id", "turn_no"),
        Index("idx_cir_quality", "run_id", "quality_score"),
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
_engine_kwargs = {
    "pool_pre_ping": True,
}
_db_connect_timeout = max(3, int(getattr(settings, "DATABASE_CONNECT_TIMEOUT_SECONDS", 15) or 15))
if settings.database_url.startswith("postgresql"):
    _engine_kwargs["connect_args"] = {
        "connect_timeout": _db_connect_timeout,
    }

engine = create_engine(settings.database_url, **_engine_kwargs)
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
