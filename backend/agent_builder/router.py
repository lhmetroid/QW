import uuid
import datetime
import re
import json
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, Response, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from database import get_db
from agent_builder.models import (
    BuilderAgent, BuilderSkill, BuilderTestCase,
    BuilderSandboxSession, BuilderSandboxMessage, BuilderTestRun,
    BuilderKnowledge, BuilderKnowledgeChunk
)
from embedding_service import EmbeddingService

router = APIRouter(prefix="/api/v1/builder", tags=["Agent Builder"])

# --- Pydantic Schemas ---
class AgentCreate(BaseModel):
    name: str
    industry: str
    role: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    constraints: Optional[dict] = None

class SkillSave(BaseModel):
    title: str
    type: str
    status: str
    activation_rules: Optional[dict] = None
    execution_strategy: Optional[dict] = None

class SkillsSaveRequest(BaseModel):
    agent_id: str
    skills: List[SkillSave]

class SandboxStartRequest(BaseModel):
    agent_id: str
    case_id: Optional[str] = None

class SandboxChatRequest(BaseModel):
    session_id: str
    content: str

# --- API Endpoints ---

@router.post("/agents")
def create_or_update_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    # Simple strategy: keep a single default agent for this tenant/sandbox to simplify demo
    agent = db.query(BuilderAgent).first()
    if not agent:
        agent = BuilderAgent(
            agent_id=str(uuid.uuid4()),
            name=payload.name,
            industry=payload.industry,
            role=payload.role,
            description=payload.description,
            system_prompt=payload.system_prompt,
            constraints=payload.constraints
        )
        db.add(agent)
    else:
        agent.name = payload.name
        agent.industry = payload.industry
        agent.role = payload.role or agent.role
        agent.description = payload.description or agent.description
        agent.system_prompt = payload.system_prompt or agent.system_prompt
        agent.constraints = payload.constraints or agent.constraints
        agent.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(agent)
    return {"status": "success", "agent": {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "industry": agent.industry,
        "role": agent.role,
        "description": agent.description,
        "constraints": agent.constraints
    }}

@router.get("/agents/default")
def get_default_agent(db: Session = Depends(get_db)):
    agent = db.query(BuilderAgent).first()
    if not agent:
        # Create a default one representing the video scenario (used iPhone retail)
        agent = BuilderAgent(
            agent_id=str(uuid.uuid4()),
            name="SPARK 手机客服",
            industry="电商",
            role="售前咨询与分期资格初步审核",
            description="针对二手iPhone手机零售的AI销冠助手",
            system_prompt="您好！我是 SPARK 手机零售助手。请问有什么我可以帮您的？",
            constraints={
                "strict_rules": [
                    "严禁主动提及分期 (除非客户先提)",
                    "贷款资格三要素: 年满21岁 + 固定工作 + 持有印尼KTP",
                    "低意向客户绝不转交人工客服"
                ]
            }
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
    return {"status": "success", "agent": {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "industry": agent.industry,
        "role": agent.role,
        "description": agent.description,
        "constraints": agent.constraints
    }}

@router.get("/skills")
def get_skills(agent_id: str, db: Session = Depends(get_db)):
    skills = db.query(BuilderSkill).filter(BuilderSkill.agent_id == agent_id).all()
    if not skills:
        # Populate default 6 skills from the video
        default_skills = [
            ("画像收集", "基础画像收集", "测试中", {"trigger": "always"}, {"steps": "自动记录客户预算、用途、意向机型等"}),
            ("需求探询与推荐", "自定义任务技能", "测试中", {"trigger": "budget_missing"}, {"steps": "先问预算，再问用途并匹配推荐"}),
            ("分期方案介绍", "业务答疑", "测试中", {"trigger": "ask_installment"}, {"steps": "仅在客户主动询问时依据知识库解答"}),
            ("高意向转化与资格确认", "自定义任务技能", "测试中", {"trigger": "high_intent"}, {"steps": "确认年龄/工作/KTP资质并转人工"}),
            ("常见问题答疑", "常见 FAQ 库", "已发布", {"trigger": "faq_ask"}, {"steps": "解决成色、电池、价格、售后疑虑"}),
            ("犹豫心理处理", "温和引导", "已发布", {"trigger": "hesitant"}, {"steps": "对轻度犹豫客户提供温和引导"}),
        ]
        for title, type_name, status, act, exec_strat in default_skills:
            skill = BuilderSkill(
                skill_id=str(uuid.uuid4()),
                agent_id=agent_id,
                title=title,
                type=type_name,
                status=status,
                activation_rules=act,
                execution_strategy=exec_strat
            )
            db.add(skill)
        db.commit()
        skills = db.query(BuilderSkill).filter(BuilderSkill.agent_id == agent_id).all()

    return {"status": "success", "skills": [
        {
            "skill_id": s.skill_id,
            "title": s.title,
            "type": s.type,
            "status": s.status,
            "activation_rules": s.activation_rules,
            "execution_strategy": s.execution_strategy
        } for s in skills
    ]}

@router.post("/skills")
def save_skills(payload: SkillsSaveRequest, db: Session = Depends(get_db)):
    # Delete existing skills for the agent first
    db.query(BuilderSkill).filter(BuilderSkill.agent_id == payload.agent_id).delete()
    for s in payload.skills:
        skill = BuilderSkill(
            skill_id=str(uuid.uuid4()),
            agent_id=payload.agent_id,
            title=s.title,
            type=s.type,
            status=s.status,
            activation_rules=s.activation_rules,
            execution_strategy=s.execution_strategy
        )
        db.add(skill)
    db.commit()
    return {"status": "success", "message": "Skills saved successfully."}

@router.get("/test_cases")
def get_test_cases(agent_id: str, db: Session = Depends(get_db)):
    cases = db.query(BuilderTestCase).filter(BuilderTestCase.agent_id == agent_id).all()
    if not cases:
        # Populate the 12 golden test cases
        golden_cases = [
            ("TC-001", "先给预算与用途，顺利拿到机型推荐", "需求探询与推荐 -> 画像收集",
             {"name": "林迪", "budget": "2500-3000", "usage": "拍照与社交", "personality": "配合度高，回答直接", "eligibility": {"age": 25, "job": "有", "ktp": "有"}},
             "首轮识别购机意向，预算给齐后推荐机型及简短理由。不主动引入分期。回复简短专业。"),

            ("TC-002", "已有明确意向机型，继续了解并推进预定 (分期全资质)", "高意向转化与资格确认 -> 转交人工",
             {"name": "哈桑", "budget": "300万印尼盾", "usage": "分期付款购买 iPhone XR", "personality": "意向明确，主动提分期", "eligibility": {"age": 25, "job": "固定工作", "ktp": "持有"}},
             "确认其分期贷款资格，确认合格后自动总结意向并转交客户经理预定。"),

            ("TC-003", "用户只问分期但不透露意向机型与预算", "分期方案介绍 -> 引导话术约束",
             {"name": "苏托", "budget": "未提及", "usage": "只问分期费率", "personality": "对预算避而不谈", "eligibility": {"age": 24, "job": "有", "ktp": "有"}},
             "简要解释分期首付，但必须立即追问其预算与型号，不直接给具体利率。"),

            ("TC-004", "买家年龄不足 21 岁进行分期咨询", "高意向转化与资格确认 -> 拒绝贷款",
             {"name": "阿里", "budget": "400万印尼盾", "usage": "学生购买 iPhone 11", "personality": "年轻买家", "eligibility": {"age": 18, "job": "学生无固定工作", "ktp": "有"}},
             "识别年龄小于21岁，告知分期资格不符，并引导推荐全款购买低端型号（如iPhone 8）。"),

            ("TC-005", "买家无固定工作进行分期咨询", "高意向转化与资格确认 -> 拒绝贷款",
             {"name": "瓦万", "budget": "3500", "usage": "自由职业购买 iPhone XR", "personality": "无固定工作", "eligibility": {"age": 23, "job": "无固定工作", "ktp": "有"}},
             "识别出无固定工作，告知不符合印尼分期准入标准，引导看全款方案。"),

            ("TC-006", "买家无 KTP 身份证进行分期咨询", "高意向转化与资格确认 -> 拒绝贷款",
             {"name": "麦克", "budget": "5000", "usage": "外籍人员购买 iPhone 11 Pro", "personality": "无印尼本地KTP", "eligibility": {"age": 28, "job": "有正式工作", "ktp": "无"}},
             "识别出无 KTP，告知无法办理本地分期贷款，引导推荐全款购买。"),

            ("TC-007", "购机用途为重度游戏，预算 4000 元", "需求探询与推荐",
             {"name": "安迪", "budget": "4000", "usage": "玩大型游戏，注重电池和发热", "personality": "重度手游玩家", "eligibility": {"age": 22, "job": "有", "ktp": "有"}},
             "推荐适合玩游戏的机型（如 iPhone 11 Pro），说明发热控制和电池优势，不主动提及分期。"),

            ("TC-008", "用户反复纠缠价格，要求折上折", "犹豫心理处理 -> 价格底线防守",
             {"name": "布迪", "budget": "300万印尼盾", "usage": "购买 iPhone XR 砍价", "personality": "爱贪便宜，反复砍价", "eligibility": {"age": 30, "job": "有", "ktp": "有"}},
             "温和话术应对，说明已经是渠道底价，但可以提供配件包赠品，牢牢守住价格底线。"),

            ("TC-009", "购机用途为拍照与视频录制，要求电池健康 90%+", "需求探询与推荐 -> 常见问题答疑",
             {"name": "西蒂", "budget": "3500", "usage": "拍照，拍Vlog，指定高寿命电池", "personality": "时尚女性，注重成色", "eligibility": {"age": 24, "job": "有", "ktp": "有"}},
             "推荐成色良好且拍照出色的机型（如 iPhone 11 95新），并说明电池健康符合其 90%+ 要求。"),

            ("TC-010", "用户对电池健康 80% 表示顾虑", "犹豫心理处理 -> 消除顾虑",
             {"name": "德维", "budget": "3000", "usage": "购买 iPhone XR 电池健康82%", "personality": "犹豫不决，担心寿命", "eligibility": {"age": 26, "job": "有", "ktp": "有"}},
             "触发犹豫心理处理技能，温和说明官方 80% 以上均属正常健康状态，且提供3个月质保和电池更换优惠。"),

            ("TC-011", "客户提供超高预算（8000元以上），要求推荐最新款", "需求探询与推荐 -> 引导购买",
             {"name": "普特拉", "budget": "8000以上", "usage": "想要最新旗舰", "personality": "高净值，爽快", "eligibility": {"age": 35, "job": "有", "ktp": "有"}},
             "推荐最新旗舰（如 iPhone 13 Pro），介绍屏幕和芯片优势，直接引导推进预定。"),

            ("TC-012", "用户连续用犹豫语气拖延，测试上下文承接推进", "犹豫心理处理 -> 持续推进",
             {"name": "丽娜", "budget": "3200", "usage": "纠结配件、包装盒、成色", "personality": "极其纠结，拖延表态", "eligibility": {"age": 22, "job": "有", "ktp": "有"}},
             "进行适度的话术承接与温和跟进推进，不强求直接下单，保持对话流畅度和耐心。"),
        ]
        for code, title, skills_linked, persona, criteria in golden_cases:
            tc = BuilderTestCase(
                case_id=str(uuid.uuid4()),
                agent_id=agent_id,
                title=f"{code} | {title}",
                target_skills=skills_linked,
                persona=persona,
                criteria=criteria
            )
            db.add(tc)
        db.commit()
        cases = db.query(BuilderTestCase).filter(BuilderTestCase.agent_id == agent_id).all()

    return {"status": "success", "cases": [
        {
            "case_id": c.case_id,
            "title": c.title,
            "target_skills": c.target_skills,
            "persona": c.persona,
            "criteria": c.criteria
        } for c in cases
    ]}

@router.post("/sandbox/start")
def start_sandbox_session(payload: SandboxStartRequest, db: Session = Depends(get_db)):
    # Start a fresh session, variables default to empty slots
    session = BuilderSandboxSession(
        session_id=str(uuid.uuid4()),
        agent_id=payload.agent_id,
        case_id=payload.case_id,
        status="active",
        variables={
            "budget": "未收集",
            "phone_usage": "未收集",
            "battery_health": "未收集",
            "age": "未收集",
            "job": "未收集",
            "ktp": "未收集",
            "current_node": "需求探询与推荐",
            "installment_triggered": False,
            "details_verified": "未核实"
        }
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"status": "success", "session_id": session.session_id, "variables": session.variables}

@router.post("/sandbox/chat")
def chat_sandbox(payload: SandboxChatRequest, db: Session = Depends(get_db)):
    session = db.query(BuilderSandboxSession).filter(BuilderSandboxSession.session_id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sandbox session not found.")

    agent = db.query(BuilderAgent).filter(BuilderAgent.agent_id == session.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found.")

    # Save customer message
    user_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="customer",
        content=payload.content
    )
    db.add(user_msg)

    # Run our State Machine and Slot Extractor
    # Note: Import engine locally to avoid circular dependencies
    from agent_builder.engine import run_sandbox_agentic_flow

    reply_text, trace = run_sandbox_agentic_flow(db, session, payload.content)

    # Save agent reply
    agent_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="agent",
        content=reply_text,
        execution_trace=trace
    )
    db.add(agent_msg)
    db.commit()

    return {
        "status": "success",
        "reply": reply_text,
        "execution_trace": trace,
        "variables": session.variables
    }

@router.post("/sandbox/run_tests")
def run_tests(agent_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    # Trigger background parallel test execution
    # For commercial-grade simplicity and responsiveness, we trigger it using a thread pools/coroutines
    # and return the run_id immediately.
    import threading
    from agent_builder.runner import execute_sandbox_test_run

    run_id = str(uuid.uuid4())
    run = BuilderTestRun(
        run_id=run_id,
        agent_id=agent_id,
        status="running",
        pass_rate=0.0,
        total_cases=0,
        pass_count=0,
        fail_count=0,
        warn_count=0
    )
    db.add(run)
    db.commit()

    t = threading.Thread(
        target=execute_sandbox_test_run,
        args=(run_id, agent_id),
        daemon=True
    )
    t.start()

    return {"status": "success", "run_id": run_id, "message": "Test execution started in background."}

@router.get("/test_runs/latest")
def get_latest_test_run(agent_id: str, db: Session = Depends(get_db)):
    run = db.query(BuilderTestRun).filter(BuilderTestRun.agent_id == agent_id).order_by(BuilderTestRun.created_at.desc()).first()
    if not run:
        # If no test run exists yet, return empty but success status
        return {"status": "empty", "message": "No test run has been executed yet."}

    return {
        "status": "success",
        "run_id": run.run_id,
        "test_status": run.status,
        "pass_rate": float(run.pass_rate or 0.0),
        "total_cases": run.total_cases,
        "pass_count": run.pass_count,
        "fail_count": run.fail_count,
        "warn_count": run.warn_count,
        "details": run.details,
        "created_at": run.created_at.isoformat() + "Z"
    }

@router.post("/channels")
def save_channels(agent_id: str = Body(...), channels: List[dict] = Body(...), db: Session = Depends(get_db)):
    # For visual purposes, we save mock channels configs into the Agent profile constraints or just success
    agent = db.query(BuilderAgent).filter(BuilderAgent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found.")

    constraints = agent.constraints or {}
    constraints["channel_configs"] = channels
    agent.constraints = constraints
    db.commit()
    return {"status": "success", "message": "Channels configurations saved."}

@router.get("/knowledge")
def list_knowledge(agent_id: str, db: Session = Depends(get_db)):
    files = db.query(BuilderKnowledge).filter(BuilderKnowledge.agent_id == agent_id).order_by(BuilderKnowledge.created_at.desc()).all()
    return {"status": "success", "knowledge": [
        {
            "knowledge_id": f.knowledge_id,
            "filename": f.filename,
            "created_at": f.created_at.isoformat() + "Z"
        } for f in files
    ]}

@router.post("/knowledge/upload")
def upload_knowledge(
    agent_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    agent = db.query(BuilderAgent).filter(BuilderAgent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found.")

    try:
        content_bytes = file.file.read()
        content = content_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    # Save the main knowledge record
    knowledge = BuilderKnowledge(
        knowledge_id=str(uuid.uuid4()),
        agent_id=agent_id,
        filename=file.filename,
        content=content
    )
    db.add(knowledge)
    db.commit()

    # Split content into chunks
    paragraphs = [p.strip() for p in re.split(r'\n+', content) if p.strip()]
    chunks = []
    current_chunk = []
    current_len = 0
    for p in paragraphs:
        if current_len + len(p) > 300:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [p]
                current_len = len(p)
            else:
                chunks.append(p)
                current_chunk = []
                current_len = 0
        else:
            current_chunk.append(p)
            current_len += len(p) + 1
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # Index chunks with embedding vectors
    indexed_count = 0
    for chunk_text in chunks:
        vector = None
        try:
            vector = EmbeddingService.embed(chunk_text)
        except Exception as err:
            print(f"Error generating embedding vector for chunk: {err}")
            vector = [0.0] * 1024

        chunk_model = BuilderKnowledgeChunk(
            chunk_id=str(uuid.uuid4()),
            knowledge_id=knowledge.knowledge_id,
            content=chunk_text,
            embedding=vector
        )
        db.add(chunk_model)
        indexed_count += 1

    db.commit()
    return {
        "status": "success",
        "knowledge_id": knowledge.knowledge_id,
        "filename": file.filename,
        "chunks_count": indexed_count
    }

@router.delete("/knowledge/{knowledge_id}")
def delete_knowledge(knowledge_id: str, db: Session = Depends(get_db)):
    db.query(BuilderKnowledge).filter(BuilderKnowledge.knowledge_id == knowledge_id).delete()
    db.commit()
    return {"status": "success", "message": "Knowledge document deleted."}

@router.post("/webhook/wecom/{agent_id}")
async def wecom_webhook(agent_id: str, request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    content = ""
    customer_id = "wecom_test_user"

    body_str = body.decode("utf-8", errors="ignore")
    if body_str.startswith("<xml") or "<xml>" in body_str:
        try:
            root = ET.fromstring(body_str)
            content = root.findtext("Content") or ""
            customer_id = root.findtext("FromUserName") or customer_id
        except Exception as e:
            print(f"Failed to parse WeCom XML webhook: {e}")
    else:
        try:
            payload = json.loads(body_str)
            content = payload.get("content") or payload.get("Content") or ""
            customer_id = payload.get("from") or payload.get("FromUserName") or customer_id
        except Exception:
            content = body_str

    # Find or create session
    session = db.query(BuilderSandboxSession).filter(
        BuilderSandboxSession.agent_id == agent_id,
        BuilderSandboxSession.status == "active"
    ).first()
    if not session:
        session = BuilderSandboxSession(
            session_id=str(uuid.uuid4()),
            agent_id=agent_id,
            status="active",
            variables={
                "budget": "未收集",
                "phone_usage": "未收集",
                "battery_health": "未收集",
                "age": "未收集",
                "job": "未收集",
                "ktp": "未收集",
                "current_node": "需求探询与推荐",
                "installment_triggered": False
            }
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    user_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="customer",
        content=content
    )
    db.add(user_msg)

    from agent_builder.engine import run_sandbox_agentic_flow
    reply_text, trace = run_sandbox_agentic_flow(db, session, content)

    agent_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="agent",
        content=reply_text,
        execution_trace=trace
    )
    db.add(agent_msg)
    db.commit()

    response_xml = f"""<xml>
   <ToUserName><![CDATA[{customer_id}]]></ToUserName>
   <FromUserName><![CDATA[gh_3chat_agent]]></FromUserName>
   <CreateTime>{int(datetime.datetime.utcnow().timestamp())}</CreateTime>
   <MsgType><![CDATA[text]]></MsgType>
   <Content><![CDATA[{reply_text}]]></Content>
</xml>"""
    return Response(content=response_xml, media_type="application/xml")

@router.post("/webhook/whatsapp/{agent_id}")
async def whatsapp_webhook(agent_id: str, request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    customer_id = payload.get("from") or "whatsapp_test_user"
    content = ""
    if "message" in payload and "text" in payload["message"]:
        content = payload["message"]["text"]
    elif "content" in payload:
        content = payload["content"]
    else:
        content = str(payload)

    session = db.query(BuilderSandboxSession).filter(
        BuilderSandboxSession.agent_id == agent_id,
        BuilderSandboxSession.status == "active"
    ).first()
    if not session:
        session = BuilderSandboxSession(
            session_id=str(uuid.uuid4()),
            agent_id=agent_id,
            status="active",
            variables={
                "budget": "未收集",
                "phone_usage": "未收集",
                "battery_health": "未收集",
                "age": "未收集",
                "job": "未收集",
                "ktp": "未收集",
                "current_node": "需求探询与推荐",
                "installment_triggered": False
            }
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    user_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="customer",
        content=content
    )
    db.add(user_msg)

    from agent_builder.engine import run_sandbox_agentic_flow
    reply_text, trace = run_sandbox_agentic_flow(db, session, content)

    agent_msg = BuilderSandboxMessage(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        sender="agent",
        content=reply_text,
        execution_trace=trace
    )
    db.add(agent_msg)
    db.commit()

    return {
        "status": "success",
        "sender": "whatsapp",
        "to": customer_id,
        "reply": reply_text,
        "trace": trace
    }

@router.post("/webhook/simulate")
async def simulate_webhook(
    channel: str = Body(...),
    agent_id: str = Body(...),
    content: str = Body(...),
    db: Session = Depends(get_db)
):
    agent = db.query(BuilderAgent).filter(BuilderAgent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found.")

    if channel.lower() == "企业微信" or channel.lower() == "wecom" or channel.lower() == "微信客服":
        xml_payload = f"""<xml>
   <ToUserName><![CDATA[gh_3chat_agent]]></ToUserName>
   <FromUserName><![CDATA[wecom_sim_user]]></FromUserName>
   <CreateTime>{int(datetime.datetime.utcnow().timestamp())}</CreateTime>
   <MsgType><![CDATA[text]]></MsgType>
   <Content><![CDATA[{content}]]></Content>
</xml>"""
        class MockRequest:
            async def body(self):
                return xml_payload.encode("utf-8")
        response = await wecom_webhook(agent_id, MockRequest(), db)
        response_body = response.body.decode("utf-8")

        root = ET.fromstring(response_body)
        reply = root.findtext("Content") or ""

        return {
            "status": "success",
            "webhook_url": f"/api/v1/builder/webhook/wecom/{agent_id}",
            "request_payload": xml_payload,
            "response_payload": response_body,
            "reply": reply
        }
    else:
        payload = {"from": "+62899999999", "content": content}
        class MockRequestWhatsApp:
            async def json(self):
                return payload
        res = await whatsapp_webhook(agent_id, MockRequestWhatsApp(), db)
        return {
            "status": "success",
            "webhook_url": f"/api/v1/builder/webhook/whatsapp/{agent_id}",
            "request_payload": json.dumps(payload, ensure_ascii=False),
            "response_payload": json.dumps(res, ensure_ascii=False),
            "reply": res["reply"]
        }

@router.post("/optimize_prompt")
def optimize_prompt(agent_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    run = db.query(BuilderTestRun).filter(BuilderTestRun.agent_id == agent_id).order_by(BuilderTestRun.created_at.desc()).first()
    if not run or not run.details:
        raise HTTPException(status_code=404, detail="No test run or recommendation rules found to inject.")

    recommendations = run.details.get("recommendations", [])
    if not recommendations:
        return {"status": "success", "message": "No optimizations required (100% pass rate achieved)."}

    skills = db.query(BuilderSkill).filter(BuilderSkill.agent_id == agent_id).all()
    injected_skills = []

    for s in skills:
        for rec in recommendations:
            if s.title.strip() == rec.get("target_skill", "").strip():
                s.execution_strategy = s.execution_strategy or {}
                rules = s.execution_strategy.get("rules", [])

                new_rules = rec.get("rules", [])
                added_any = False
                for nr in new_rules:
                    clean_r = nr.replace("建议补充规则 1.1: ", "").replace("建议补充规则 1.2: ", "")
                    clean_r = clean_r.replace("建议补充规则 2.1: ", "").replace("建议补充规则 2.2: ", "")
                    if clean_r not in rules:
                        rules.append(clean_r)
                        added_any = True

                if added_any:
                    s.execution_strategy["rules"] = rules
                    s.status = "已发布"
                    db.add(s)
                    injected_skills.append(s.title)

    db.commit()
    return {
        "status": "success",
        "message": f"Successfully injected self-healing rules into skills: {', '.join(injected_skills)}",
        "injected_skills": injected_skills
    }
