from sqlalchemy import (

    create_engine, Column, Integer, String, Text, DateTime, Date, JSON, text, Boolean,

    ForeignKey, Numeric, Index, UniqueConstraint, BigInteger, Float

)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import sessionmaker

import datetime

from config import settings

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import NullType as Vector




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



    __table_args__ = (

        Index("idx_message_logs_timestamp", "timestamp"),

        Index("idx_message_logs_user_timestamp", "user_id", "timestamp"),

    )



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



class WecomRuntimeConfig(Base):

    """企微实时智能运行配置：前台脚本/强扫描/知识库开关的数据库单行配置。"""

    __tablename__ = "wecom_runtime_config"

    id = Column(Integer, primary_key=True, default=1)

    wecom_recent_message_limit = Column(Integer, nullable=False, default=10)

    api_kb2_enabled = Column(Boolean, nullable=False, default=True)

    wecom_kb_primary = Column(String(20), nullable=False, default="kb1")

    wecom_kb_compare = Column(String(20), nullable=False, default="kb2")

    wecom_kb3_confirmed_only = Column(Boolean, nullable=False, default=False)

    wecom_auto_assist_on_customer_message = Column(Boolean, nullable=False, default=False)

    system_prompt_llm1 = Column(Text, nullable=True)

    system_prompt_llm2 = Column(Text, nullable=True)

    reply_style_options = Column(JSON, nullable=True)

    fast_track_rules = Column(JSON, nullable=True)

    mail_generation_model = Column(String(50), nullable=False, default="deepseek-v4-flash")

    mail_deepseek_model_configs = Column(JSON, nullable=True)

    updated_by = Column(String(120), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

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

    hit_chunks_snapshot = Column(JSON, nullable=True)

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



class KnowledgeHitEvent(Base):

    """知识命中事件(扁平化): knowledge_hit_logs 里每条命中拆成一行, 专供命中统计快速 GROUP BY。

    chunk_id 用 String(不是 UUID), 既能存 knowledge_chunk 的 UUID, 也能存 KB3 旧版数字 id,
    彻底避免 UUID 强转崩溃; created_at/score/query_text/status 从所属 log 冗余下来,
    统计时无需回查 knowledge_hit_logs, 也无需解析任何 JSON。"""

    __tablename__ = "knowledge_hit_event"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    log_id = Column(UUID(as_uuid=False), nullable=False)

    chunk_id = Column(String(100), nullable=False)

    hit_rank = Column(Integer, nullable=True)

    score = Column(Float, nullable=True)

    query_text = Column(Text, nullable=True)

    status = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False)

    __table_args__ = (

        Index("idx_khe_created_at", "created_at"),

        Index("idx_khe_chunk_created", "chunk_id", "created_at"),

        Index("idx_khe_log", "log_id"),

    )


def record_knowledge_hit_events(db, log, hits):
    """把一条命中日志的命中明细写入 knowledge_hit_event。失败只告警不影响主流程(事件可后续回填)。"""
    try:
        rows = []
        for index, hit in enumerate(hits or []):
            if not isinstance(hit, dict):
                continue
            chunk_id = hit.get("chunk_id") or hit.get("id")
            if not chunk_id:
                continue
            score = hit.get("score")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            rows.append(KnowledgeHitEvent(
                log_id=str(log.log_id),
                chunk_id=str(chunk_id),
                hit_rank=index + 1,
                score=score,
                query_text=log.query_text,
                status=log.status,
                created_at=log.created_at,
            ))
        if rows:
            db.add_all(rows)
            db.commit()
        return len(rows)
    except Exception as exc:
        db.rollback()
        try:
            import logging
            logging.getLogger("database").warning("record_knowledge_hit_events 写入失败(可后续回填): %s", exc)
        except Exception:
            pass
        return 0



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
        Index("idx_efa_mail_gold_seed_lookup", "source_type", "scenario_label", "function_fragment", "status", "useful_score", "effect_score", "updated_at"),

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



class MailDemoContact(Base):

    """邮件 AI 回复演示用的 5 个测试案例联系人快照表（独立 PG 表）。



    数据来源：从 CRM 接口 fetch_crm_profile() 只读拉取后脱敏存入。

    用途：前端邮件质量诊断面板的真接入演示区做案例切换 + 默认值预填。

    边界：本表只存测试案例，不写回 CRM。CRM 数据库本身只读，绝不改动。

    """

    __tablename__ = "mail_demo_contact"



    demo_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    demo_index = Column(Integer, nullable=False)  # 1-5 案例序号

    demo_label = Column(String(80), nullable=False)  # 中文维度名 如"熟联系人多合同活跃"

    demo_label_detail = Column(Text, nullable=True)  # 维度描述详情
    real_customer_key = Column(String(120), nullable=True)
    display_group = Column(String(40), nullable=False, default="legacy")
    is_current_test_case = Column(Boolean, nullable=False, default=False)



    # CRM 来源（脱敏后存）

    crm_external_userid_masked = Column(String(120), nullable=False)

    crm_contact_id_masked = Column(String(80), nullable=True)

    contact_name_masked = Column(String(120), nullable=True)

    company_name_masked = Column(String(255), nullable=True)

    contact_email_masked = Column(String(255), nullable=False)



    # CRM 画像可分类字段

    company_industry = Column(String(80), nullable=True)

    customer_lifecycle_stage = Column(String(40), nullable=True)

    customer_tier = Column(String(40), nullable=True)

    payment_risk_level = Column(String(40), nullable=True)

    high_risk_flags = Column(JSON, nullable=True)



    # CRM 画像快照（完整 JSON，脱敏后）

    crm_profile_snapshot = Column(JSON, nullable=False)



    # 邮件 Live Demo 默认表单值

    default_scenario = Column(String(80), nullable=False)

    default_suite_step = Column(Integer, nullable=False, default=1)

    default_seller_name = Column(String(120), nullable=False, default="销售测试")

    default_seller_signature = Column(Text, nullable=False, default="销售测试\n事必达翻译与本地化部")



    # 元数据

    source_note = Column(Text, nullable=True)

    refreshed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)



    __table_args__ = (

        Index("idx_mail_demo_contact_index", "demo_index", unique=True),
        Index("idx_mail_demo_contact_current", "is_current_test_case", "display_group", "demo_index"),

    )





class MailSequenceTemplate(Base):

    """邮件三场景四阶段脚本模板表。"""

    __tablename__ = "mail_sequence_template"

    template_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    customer_key = Column(String(120), nullable=False, default="")
    scenario = Column(String(80), nullable=False)
    suite_step = Column(Integer, nullable=False)
    scenario_label_cn = Column(String(80), nullable=False)
    step_label_cn = Column(String(120), nullable=False)
    purpose_cn = Column(Text, nullable=False)
    send_timing_cn = Column(String(120), nullable=False)
    variable_notes = Column(JSON, nullable=False, default=dict)
    script_template = Column(Text, nullable=False)
    ai_instruction_script = Column(Text, nullable=False, default="")
    version_no = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("customer_key", "scenario", "suite_step", name="uq_mail_sequence_template_customer_scenario_step"),
        Index("idx_mst_customer_scenario_step", "customer_key", "scenario", "suite_step"),
    )


class MailIterationRun(Base):

    """邮件 AI 回复迭代记录主表：每次跑 5 案例 × 4 步 = 20 封邮件为一次迭代。"""

    __tablename__ = "mail_iteration_run"



    run_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    version_no = Column(Integer, nullable=False)

    run_label = Column(Text, nullable=True)

    triggered_by = Column(String(120), nullable=True)

    triggered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    started_at = Column(DateTime, nullable=True)

    finished_at = Column(DateTime, nullable=True)

    status = Column(String(20), nullable=False, default="queued")  # queued / running / success / partial / failed



    # 统计

    total_drafts = Column(Integer, nullable=False, default=0)

    succeeded_drafts = Column(Integer, nullable=False, default=0)

    failed_drafts = Column(Integer, nullable=False, default=0)

    avg_quality_score = Column(Numeric(6, 2), nullable=True)

    min_quality_score = Column(Numeric(6, 2), nullable=True)

    max_quality_score = Column(Numeric(6, 2), nullable=True)

    avg_elapsed_ms = Column(Integer, nullable=True)

    llm_success_count = Column(Integer, nullable=False, default=0)

    llm_fallback_count = Column(Integer, nullable=False, default=0)



    # 本次跑的脚本/Prompt/模型快照

    pipeline_snapshot = Column(JSON, nullable=True)

    notes = Column(Text, nullable=True)

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)



    __table_args__ = (

        Index("idx_mir_triggered_at", "triggered_at"),

        Index("idx_mir_version_no", "version_no"),

        Index("idx_mir_status", "status", "triggered_at"),

    )





class MailIterationDraft(Base):

    """邮件 AI 回复迭代逐封草稿明细：1 run × 5 案例 × 4 步 = 20 行。"""

    __tablename__ = "mail_iteration_draft"



    draft_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    run_id = Column(UUID(as_uuid=False), ForeignKey("mail_iteration_run.run_id"), nullable=False)



    # 案例 + 步骤

    demo_index = Column(Integer, nullable=False)

    demo_label = Column(Text, nullable=True)

    scenario = Column(String(80), nullable=False)

    suite_step = Column(Integer, nullable=False)



    # 请求

    customer_key = Column(String(255), nullable=True)

    contact_email = Column(String(255), nullable=True)

    request_payload = Column(JSON, nullable=True)



    # LLM

    llm_prompt = Column(Text, nullable=True)

    llm_status = Column(String(40), nullable=True)

    llm_model_used = Column(String(80), nullable=True)

    llm_error = Column(Text, nullable=True)



    # 响应

    response_payload = Column(JSON, nullable=True)

    final_subject = Column(Text, nullable=True)

    final_body_html = Column(Text, nullable=True)

    retrieved_fewshot_id = Column(UUID(as_uuid=False), nullable=True)

    fewshot_match_score = Column(Numeric(6, 4), nullable=True)



    # 安全门

    overall_outcome = Column(String(40), nullable=True)

    safety_status = Column(String(60), nullable=True)



    # 评分（规则版，0-100）

    quality_score = Column(Numeric(6, 2), nullable=True)

    quality_breakdown = Column(JSON, nullable=True)

    quality_notes = Column(Text, nullable=True)



    # 元数据

    elapsed_ms = Column(Integer, nullable=True)

    status = Column(String(20), nullable=False, default="pending")  # pending / running / success / failed

    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)

    finished_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)



    __table_args__ = (

        Index("idx_mid_run", "run_id"),

        Index("idx_mid_run_demo_step", "run_id", "demo_index", "suite_step", unique=True),

    )





class MailDraftTestRecord(Base):

    """邮件草稿测试案例独立记录表 (v1.7.217)



    用户要求: "案例请单独开表保存，V1,2,3。。。等之后每轮测试也都要记录便于之后核对验证"



    跟 MailIterationDraft 区别:

    - MailIterationDraft 是"一次性跑 5案例×4步=20封压测"的批量记录, 强制 (run_id, demo_index, suite_step) 唯一

    - MailDraftTestRecord 是"每次草稿生成都按版本号 V1/V2/V3 落一笔" 的累积记录, 不强制唯一,

      允许同一案例在同一版本下重复测试, 便于回溯每次实验的 prompt/response/CRM 信号

    """

    __tablename__ = "mail_draft_test_record"



    record_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    # 版本号 - 用户最关键的维度, V1 / V2 / V3 / V3.1 等自由字符串

    test_version = Column(String(40), nullable=False)

    test_label = Column(Text, nullable=True)  # 人工备注 "v1.7.217 第一轮真跑" 等



    # 案例 + 步骤

    demo_index = Column(Integer, nullable=True)

    demo_label = Column(Text, nullable=True)

    scenario = Column(String(80), nullable=True)

    suite_step = Column(Integer, nullable=True)



    # 请求 + 响应 完整快照

    customer_key = Column(String(255), nullable=True)

    contact_email = Column(String(255), nullable=True)

    request_payload = Column(JSON, nullable=True)

    response_payload = Column(JSON, nullable=True)



    # 关键产出

    final_subject = Column(Text, nullable=True)

    final_body_html = Column(Text, nullable=True)

    retrieved_fewshot_id = Column(UUID(as_uuid=False), nullable=True)

    fewshot_match_score = Column(Numeric(6, 4), nullable=True)



    # LLM 信号

    llm_status = Column(String(40), nullable=True)

    llm_model_used = Column(String(80), nullable=True)

    llm_error = Column(Text, nullable=True)

    llm_prompt = Column(Text, nullable=True)



    # CRM + 商业条款解析快照

    crm_profile_signals = Column(JSON, nullable=True)

    commercial_terms_resolved = Column(JSON, nullable=True)



    # 安全门

    overall_outcome = Column(String(40), nullable=True)

    safety_status = Column(String(60), nullable=True)



    # 时间

    started_at = Column(DateTime, nullable=True)

    finished_at = Column(DateTime, nullable=True)

    elapsed_ms = Column(Integer, nullable=True)



    # 人工标注 (核查时填)

    notes = Column(Text, nullable=True)

    reviewed_by = Column(String(120), nullable=True)

    reviewed_at = Column(DateTime, nullable=True)



    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)



    __table_args__ = (

        Index("idx_mdtr_version", "test_version", "created_at"),

        Index("idx_mdtr_version_demo_step", "test_version", "demo_index", "suite_step"),

        Index("idx_mdtr_created", "created_at"),

    )





class MailCustomerSuiteFeedback(Base):

    """独立客户套装邮件页的单封邮件反馈记录。"""

    __tablename__ = "mail_customer_suite_feedback"

    feedback_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    customer_id = Column(String(120), nullable=False)

    contact_email = Column(String(255), nullable=True)

    company_name = Column(String(255), nullable=True)

    scenario = Column(String(80), nullable=False)

    suite_step = Column(Integer, nullable=False)

    mail_uid = Column(String(120), nullable=True)

    final_subject = Column(String(500), nullable=True)

    final_body_html = Column(Text, nullable=True)

    feedback_text = Column(Text, nullable=False)

    feedback_source = Column(String(80), nullable=False, default="mail_suite_page")

    feedback_status = Column(String(50), nullable=False, default="submitted")

    draft_payload = Column(JSON, nullable=True)

    customer_profile = Column(JSON, nullable=True)

    # 质检页人工填写的"结论"和"已处理"标记(leave 保存)
    conclusion = Column(Text, nullable=True)

    handled = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (

        Index("idx_mcsf_customer_created", "customer_id", "created_at"),

        Index("idx_mcsf_scenario_step", "scenario", "suite_step"),

    )


class MailAutosendConfig(Base):
    """自动群发全局配置(单行 config_id=1): 联系人排序规则 + 统一周期 + 每日上限 + 兜底/去重开关。"""

    __tablename__ = "mail_autosend_config"

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    sort_rule = Column(String(40), nullable=False, default="default")          # default/amount_desc/amount_asc/last_far/last_near/random
    only_valid_email = Column(Boolean, nullable=False, default=True)
    interval_days_csv = Column(String(120), nullable=False, default="0")        # 统一周期, 按封天数列表, 逗号分隔, 如 0,5,7,14
    daily_cap = Column(Integer, nullable=False, default=10)                     # 每个销售每日上限
    fallback_enabled = Column(Boolean, nullable=False, default=True)            # 全不命中时兜底最后一个套装
    dedup_by_history = Column(Boolean, nullable=False, default=True)            # 同联系人已发过的套装本次跳过
    default_partial_sent_mode = Column(String(20), nullable=False, default="remaining")  # 已发部分套装全局默认: remaining/resend_all/skip
    email_valid_mode = Column(String(20), nullable=False, default="collect")  # 有效邮箱判定: collect(IsCollect=正确) / manual(人工判断)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class MailAutosendSuiteRule(Base):
    """套装优先级规则: 一行一个套装 + 条件组(JSON) + 且/或; priority 小的优先。"""

    __tablename__ = "mail_autosend_suite_rule"

    rule_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    priority = Column(Integer, nullable=False, default=0)
    scenario = Column(String(80), nullable=False)
    conditions = Column(JSON, nullable=True)        # [{type:amount|last_coop_days|business_line, op:</>|has|not, value:...}]
    match_mode = Column(String(8), nullable=False, default="and")   # and/or
    partial_sent_mode = Column(String(20), nullable=False, default="use_global")  # use_global/remaining/resend_all/skip
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (Index("idx_masr_priority", "priority"),)


class MailAutosendRun(Base):
    """一次自动群发(或 dry-run)的运行记录。"""

    __tablename__ = "mail_autosend_run"

    run_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    status = Column(String(30), nullable=False, default="dry_run")   # dry_run/running/done/failed
    start_date = Column(Date, nullable=True)
    sales_staff_ids = Column(String(500), nullable=True)
    daily_cap = Column(Integer, nullable=True)
    sort_rule = Column(String(40), nullable=True)
    interval_days_csv = Column(String(120), nullable=True)
    total_contacts = Column(Integer, default=0)
    total_items = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class MailAutosendPlanItem(Base):
    """自动群发逐(联系人 x 封)排期明细。dry-run 只算不入 CRM; 真发时回填 crm_send_id。"""

    __tablename__ = "mail_autosend_plan_item"

    item_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=False), nullable=False)
    contact_id = Column(String(120), nullable=False)
    owner_staff_id = Column(String(120), nullable=True)
    scenario = Column(String(80), nullable=False)
    suite_step = Column(Integer, nullable=False)
    plan_date = Column(Date, nullable=True)
    plan_time = Column(String(8), nullable=True)
    seq_in_day = Column(Integer, nullable=True)
    recipient_email = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False, default="planned")
    crm_send_id = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (Index("idx_masp_run", "run_id"),)


class MailContactSuiteHistory(Base):
    """联系人用过哪些套装/哪些封, 用于去重和回查。"""

    __tablename__ = "mail_contact_suite_history"

    history_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    contact_id = Column(String(120), nullable=False)
    owner_staff_id = Column(String(120), nullable=True)
    scenario = Column(String(80), nullable=False)
    suite_step = Column(Integer, nullable=True)
    run_id = Column(UUID(as_uuid=False), nullable=True)
    planned_send_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (Index("idx_mcsh_contact", "contact_id"),)


class MailCustomerSuiteDraftEdit(Base):

    """独立客户套装邮件页的逐封草稿人工编辑(主题/正文/发送间隔/发送时间/是否发送)。

    按 客户编号+场景+第N封 唯一,每封一条,leave 保存即 upsert 覆盖。
    """

    __tablename__ = "mail_customer_suite_draft_edit"

    draft_edit_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    customer_id = Column(String(120), nullable=False)

    scenario = Column(String(80), nullable=False)

    suite_step = Column(Integer, nullable=False)

    mail_uid = Column(String(120), nullable=True)

    subject = Column(String(500), nullable=True)

    body_html = Column(Text, nullable=True)

    llm_prompt = Column(Text, nullable=True)

    send_interval_days = Column(Integer, nullable=True)

    send_time = Column(String(10), nullable=True)

    included = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (

        Index("uq_mcsde_customer_scenario_step", "customer_id", "scenario", "suite_step", unique=True),

    )


class MailCustomSuite(Base):
    """用户从界面自建的套装场景元数据（scenario 值、中文名、封数）。"""

    __tablename__ = "mail_custom_suite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scenario = Column(String(120), unique=True, nullable=False)
    label_cn = Column(String(200), nullable=False)
    step_count = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class MailCustomerSuiteRecipient(Base):

    """套装页客户收件邮箱(可人工编辑覆盖,默认取 CRM 有效邮箱),按 客户编号+场景 唯一。"""

    __tablename__ = "mail_customer_suite_recipient"

    recipient_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    customer_id = Column(String(120), nullable=False)

    scenario = Column(String(80), nullable=False)

    emails = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (

        Index("uq_mcsr_customer_scenario", "customer_id", "scenario", unique=True),

    )


class MailCustomerSuiteSendPlan(Base):

    """套装页"发送"动作生成的待发计划(本地暂存)。

    收发件人已按 spQueueSend 格式备好;真正写入 CRM spQueueSend + 上传 .eml 待 FTP 接入后由后续步骤完成。
    """

    __tablename__ = "mail_customer_suite_send_plan"

    plan_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))

    batch_id = Column(String(64), nullable=True)

    customer_id = Column(String(120), nullable=False)

    scenario = Column(String(80), nullable=False)

    suite_step = Column(Integer, nullable=False)

    sender_email = Column(String(255), nullable=True)

    sender_name = Column(String(255), nullable=True)

    to_emails = Column(Text, nullable=True)

    subject = Column(String(500), nullable=True)

    body_html = Column(Text, nullable=True)

    body_text = Column(Text, nullable=True)

    plan_send_time = Column(DateTime, nullable=True)

    send_address_serialized = Column(Text, nullable=True)

    receiver_serialized = Column(Text, nullable=True)

    inputer_staff_id = Column(String(120), nullable=True)

    status = Column(String(40), nullable=False, default="prepared_pending_ftp")

    spqueue_rowid = Column(String(64), nullable=True)

    # CRM spQueueSend 触发器生成的 SendId(如 Mal_S260622-000003)。真发后据此在 spSendInfo{销售}
    # 用 SendId 关联确认 SendSuccess/FactSendTime，是"邮件统计"实发数的稳定关联键。
    crm_send_id = Column(String(80), nullable=True)

    # 邮件统计：从 CRM spSendInfo{销售} 同步回来的真发状态缓存(刷新时更新)
    crm_send_status = Column(String(40), nullable=True)  # SendSuccess/SendFail/WaitSend/Sending/deleted
    crm_fact_send_time = Column(DateTime, nullable=True)  # 真发成功时间(实发数按此日计)
    crm_message_id = Column(String(255), nullable=True)  # 发送 .eml 解析出的 Message-ID(回信匹配键)
    crm_eml_ftp_dir = Column(String(255), nullable=True)
    status_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (

        Index("idx_mcssp_customer_scenario", "customer_id", "scenario"),

        Index("idx_mcssp_batch", "batch_id"),

        Index("idx_mcssp_send_id", "crm_send_id"),

    )


class MailAiReplyAnalysis(Base):
    """邮件统计：AI 套装邮件的客户回信解析缓存(回信识别 + deepseek 价值判定)。

    一封 AI 邮件(plan_id) x 一封匹配上的 CRM 收件行(reply_crm_rowid) 唯一一条。
    回信识别用 FTP 解析收件 .eml 的 In-Reply-To 精确匹配发送 .eml 的 Message-ID。
    """
    __tablename__ = "mail_ai_reply_analysis"

    reply_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    plan_id = Column(UUID(as_uuid=False), nullable=False)
    crm_send_id = Column(String(80), nullable=True)
    customer_id = Column(String(120), nullable=True)
    staff_id = Column(String(120), nullable=True)
    reply_crm_rowid = Column(String(64), nullable=False)
    reply_sender = Column(String(255), nullable=True)
    reply_subject = Column(String(500), nullable=True)
    reply_body = Column(Text, nullable=True)
    reply_received_at = Column(DateTime, nullable=True)
    match_method = Column(String(40), nullable=True)  # eml_in_reply_to / contact_time_fallback
    is_valuable = Column(Boolean, nullable=True)
    value_reason = Column(Text, nullable=True)
    value_model = Column(String(120), nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_mar_plan_reply", "plan_id", "reply_crm_rowid", unique=True),
        Index("idx_mar_received", "reply_received_at"),
        Index("idx_mar_staff", "staff_id"),
    )


class MailAiDailyStats(Base):
    """邮件统计：按天 x 销售 预计算结果。历史日固化(is_final),当天每次查询实时重算覆盖。"""
    __tablename__ = "mail_ai_daily_stats"

    stat_date = Column(Date, primary_key=True)
    staff_id = Column(String(120), primary_key=True, default="")
    generated_count = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    reply_count = Column(Integer, nullable=False, default=0)
    valuable_count = Column(Integer, nullable=False, default=0)
    feedback_count = Column(Integer, nullable=False, default=0)
    is_final = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class MailContractCase(Base):
    """邮件本地合同案例表：缓存/灌库 CRM 中的所有符合标准的合同案例，减少动态查询开销"""
    __tablename__ = "mail_contract_case"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(String(120), unique=True, index=True, nullable=False)
    customer_id = Column(String(120), index=True)
    contact_id = Column(String(120), index=True)
    total_money = Column(Numeric(12, 2))
    amount_bucket = Column(String(80))
    product_name_all = Column(String(500))
    business_type = Column(String(120))
    contract_description = Column(Text)
    company_name = Column(String(500))
    input_time = Column(DateTime)
    contract_time = Column(DateTime)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    business_line_inferred = Column(String(255))
    language_pair_inferred = Column(Text)
    industry_inferred = Column(String(255))
    quality_flags = Column(JSON)
    mail_case_text = Column(Text)
    ingested_to_knowledge = Column(Boolean, default=False)
    desensitized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_mcc_customer_created", "customer_id", "created_at"),
        Index("idx_mcc_business_line", "business_line_inferred"),
    )


class MailGoldSeedReview(Base):
    """黄金范例库人工点评表：记录对每条黄金种子的认可/不认可 + 点评内容。

    每条种子(fragment_id)只保留一行最新评审, 再次操作覆盖。
    """
    __tablename__ = "mail_gold_seed_review"

    id = Column(Integer, primary_key=True, index=True)
    fragment_id = Column(String(64), unique=True, index=True, nullable=False)
    source_ref = Column(String(255), nullable=True)
    review_status = Column(String(20), nullable=False)  # approved / rejected
    review_comment = Column(Text, nullable=True)
    reviewer = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class LlmServiceKnowledgeUnit(Base):
    """新版服务知识库单元表"""
    __tablename__ = "llm_service_knowledge_unit"

    unit_id = Column(BigInteger, primary_key=True)
    service_category = Column(Text, nullable=True)
    service_subcategory = Column(Text, nullable=True)
    knowledge_type = Column(Text, nullable=True)
    unit_type = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)
    status = Column(Text, nullable=False, default="pending")
    confidence = Column(Numeric, nullable=True)
    search_text = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True)
    content_hash = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)
    review_tags = Column(JSON, nullable=True)
    reviewer = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    qc_flags = Column(JSON, nullable=True)
    audience = Column(Text, nullable=True)


class LlmServiceTaxonomy(Base):
    """服务目录分类与别名表"""
    __tablename__ = "llm_service_taxonomy"

    id = Column(Integer, primary_key=True)
    category = Column(Text, nullable=False)
    subcategory = Column(Text, nullable=False)
    cat_order = Column(Integer, nullable=False)
    sub_order = Column(Integer, nullable=False)
    is_cross = Column(Boolean, nullable=False, default=False)
    category_aliases = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("category", "subcategory", name="uq_category_subcategory"),
        Index("idx_taxonomy_category", "category"),
    )


# 初始化数据库连接
_engine_kwargs = {

    "pool_pre_ping": True,

}

_db_connect_timeout = max(3, int(getattr(settings, "DATABASE_CONNECT_TIMEOUT_SECONDS", 15) or 15))

if settings.database_url.startswith("postgresql"):

    _pg_options = " ".join(
        item
        for item in [
            f"-c statement_timeout={max(1000, int(getattr(settings, 'DATABASE_STATEMENT_TIMEOUT_MS', 20000) or 20000))}",
            f"-c idle_in_transaction_session_timeout={max(5000, int(getattr(settings, 'DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS', 60000) or 60000))}",
            f"-c lock_timeout={max(500, int(getattr(settings, 'DATABASE_LOCK_TIMEOUT_MS', 5000) or 5000))}",
        ]
    )

    _engine_kwargs["connect_args"] = {

        "connect_timeout": _db_connect_timeout,
        "options": _pg_options,

    }



engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def init_db():

    try:

        # 彻底移除 vector 扩展激活逻辑，因宿主机环境完全不支持

        # with engine.connect() as conn:

        #     conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        #     conn.commit()

        try:

            import agent_builder.models

        except Exception as err:

            print(f"导入 agent_builder 模型失败: {err}")

        Base.metadata.create_all(bind=engine)

    except Exception as e:

        print(f"数据库初始化基础表结构失败: {e}")



def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()
