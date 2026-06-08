import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Numeric, Boolean, text, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from database import Base

class BuilderAgent(Base):
    __tablename__ = "builder_agents"

    agent_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String(100), nullable=False)
    industry = Column(String(100), nullable=False)
    role = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    constraints = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

class BuilderSkill(Base):
    __tablename__ = "builder_skills"

    skill_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("builder_agents.agent_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="测试中")
    activation_rules = Column(JSON, nullable=True)
    execution_strategy = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

class BuilderTestCase(Base):
    __tablename__ = "builder_test_cases"

    case_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("builder_agents.agent_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    target_skills = Column(String(200), nullable=True)
    persona = Column(JSON, nullable=False)  # {"name", "budget", "usage", "personality", "eligibility": {"age", "job", "ktp"}}
    criteria = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class BuilderSandboxSession(Base):
    __tablename__ = "builder_sandbox_sessions"

    session_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("builder_agents.agent_id", ondelete="CASCADE"), nullable=False)
    case_id = Column(UUID(as_uuid=False), ForeignKey("builder_test_cases.case_id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="active")  # active, completed, failed
    variables = Column(JSON, nullable=True)  # {"budget", "phone_usage", "battery_health", "age", "job", "ktp"}
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class BuilderSandboxMessage(Base):
    __tablename__ = "builder_sandbox_messages"

    message_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(UUID(as_uuid=False), ForeignKey("builder_sandbox_sessions.session_id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(50), nullable=False)  # customer, agent, system
    content = Column(Text, nullable=False)
    execution_trace = Column(JSON, nullable=True)  # {"current_node", "slots_filled", "action_triggered", "reason"}
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class BuilderTestRun(Base):
    __tablename__ = "builder_test_runs"

    run_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("builder_agents.agent_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False, default="running")  # running, completed, failed
    pass_rate = Column(Numeric(5, 2), nullable=True)
    total_cases = Column(Integer, nullable=False, default=0)
    pass_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    warn_count = Column(Integer, nullable=False, default=0)
    details = Column(JSON, nullable=True)  # list of case results
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class BuilderKnowledge(Base):
    __tablename__ = "builder_knowledge"

    knowledge_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("builder_agents.agent_id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class BuilderKnowledgeChunk(Base):
    __tablename__ = "builder_knowledge_chunks"

    chunk_id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    knowledge_id = Column(UUID(as_uuid=False), ForeignKey("builder_knowledge.knowledge_id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)  # List[float] stored as JSON for universal database portability
