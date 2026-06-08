import uuid
import json
import logging
from sqlalchemy.orm import Session
from database import SessionLocal, settings
from intent_engine import IntentEngine
from agent_builder.models import (
    BuilderTestCase, BuilderSandboxSession, BuilderSandboxMessage,
    BuilderTestRun, BuilderAgent
)
from agent_builder.engine import run_sandbox_agentic_flow

logger = logging.getLogger(__name__)

def simulate_customer_reply(persona: dict, history_text: str) -> str:
    """
    Simulate customer response based on the test case persona and dialogue history.
    """
    prompt = f"""
你是一个正在尝试购买 iPhone 手机的印尼本地消费者。你正在与一个 AI 客服进行实时聊天。
请根据你被赋予的【用户画像设定】和【对话历史记录】，写出你接下来的第一句回复（只需回复一句话，不要包含解释或多余字）。

用户画像设定：
- 姓名：{persona.get('name')}
- 购机预算：{persona.get('budget')}
- 购机用途与诉求：{persona.get('usage')}
- 性格特征：{persona.get('personality')}
- 你的个人资质：
  * 年龄：{persona.get('eligibility', {}).get('age')}
  * 工作：{persona.get('eligibility', {}).get('job')}
  * 持有KTP身份证：{persona.get('eligibility', {}).get('ktp')}

你的任务：
1. 像一个真实的人类客户一样说话。如果画像里说你想分期，就要主动问起或表达出分期意图；如果销售问你年龄和工作，请真实报出你画像里的设定。
2. 保持简短、口语化，像微信聊天。可以用简单的中文夹杂少许日常词汇。
3. 严格遵循人设。如果设定是学生或者无固定工作，销售问起时千万不要说谎；如果设定为纠结砍价，请继续讨要折扣。

对话历史记录：
{history_text}

请写出你的下一句回复：
"""
    try:
        url = settings.LLM2_API_URL.rstrip('/') + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM2_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.LLM2_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 150
        }
        res = IntentEngine._post_json(url, headers, payload, timeout=25)
        if res.status_code == 200:
            res_data = res.json()
            return res_data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Customer simulation failed: {e}")

    # Basic rule-based fallbacks for test runner
    if "分期" in str(persona.get("usage")):
        return "我想了解一下分期怎么买，首付和条件是什么？"
    return "我想买个 iPhone，主要拿来拍照用，请问有什么机型推荐吗？"

def audit_conversation_with_judge(criteria: str, history_text: str) -> dict:
    """
    Execute LLM-as-a-Judge auditor to grade the transcript.
    """
    prompt = f"""
你是一个专业的 B2B AI 智能体质检裁判 (LLM-as-a-Judge)。
请审计下面这段 AI 手机销售客服与客户之间的真实对话记录，评估其是否遵循了销售 SOP 和逻辑约束。

本测试用例的预期通过标准：
{criteria}

核心销售 SOP 与逻辑约束（红线）：
1. 严禁主动提及分期付款（除非客户先提问分期，否则 AI 提及分期即判定失败）。
2. 在分期介绍中，必须在最终确定转交人工前，完整收集并审查三要素：年满21岁、有固定工作、持有印尼KTP。未集齐或不合格便触发“转人工”，判定为失败。
3. 报价和成色描述必须准确，不能虚假报价或夸大电池健康度。
4. 如果客户资质不符合（年龄未满21、无固定工作、无KTP），AI 必须告知不符并礼貌引导至全款方案。如果继续强行办理分期或直接挂断，判定为失败。

待审计的对话历史：
{history_text}

任务要求：
只输出一个合法的 JSON 对象，不要包含 markdown 格式标记（如 ```json 等）或解释说明。

JSON 必须包含以下字段：
1. status: 只能是 "PASS" (完全符合所有规则与预期), "FAIL" (触碰红线或关键标准不符), "WARN" (无严重规则违背，但有话术重复、啰嗦或小瑕疵)。
2. error_type: 只能是 "instruction_non_compliance" (指令未遵循/抢跑分期/未核对资质), "undefined_boundary" (边界未定义/产生价格幻觉), "none" (无错误)。
3. reason: 详细解释你判定该状态的具体理由（结合对话记录）。

JSON 输出格式：
{{
  "status": "FAIL",
  "error_type": "instruction_non_compliance",
  "reason": "AI客服在首轮客户尚未提及分期时，主动询问客户是否要办理分期，违背了『严禁主动提及分期』的红线约束。"
}}
"""
    try:
        res = IntentEngine.run_llm1_json_prompt(prompt, user_id="judge_auditor", max_retries=1, timeout_seconds=10)
        if isinstance(res, dict):
            return res
    except Exception as e:
        logger.error(f"LLM-as-a-Judge audit failed: {e}")

    return {
        "status": "FAIL",
        "error_type": "instruction_non_compliance",
        "reason": "由于系统超时或接口解析失败，大模型裁判自动判定不通过。"
    }

def run_single_case_in_thread(case_id: int, agent_id: str) -> dict:
    db = SessionLocal()
    try:
        c = db.query(BuilderTestCase).filter(BuilderTestCase.case_id == case_id).first()
        if not c:
            return None

        # 1. Initialize simulation session
        session = BuilderSandboxSession(
            session_id=str(uuid.uuid4()),
            agent_id=agent_id,
            case_id=c.case_id,
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

        # Start dialogue simulation loop (Max 5 turns)
        # Greeting turn
        greeting_msg = BuilderSandboxMessage(
            message_id=str(uuid.uuid4()),
            session_id=session.session_id,
            sender="agent",
            content="您好！我是 SPARK 手机零售助手。请问有什么我可以帮您的？",
            execution_trace={"current_node": "需求探询与推荐", "action_triggered": "系统初始化", "reason": "展示欢迎语并等待客户提问。"}
        )
        db.add(greeting_msg)
        db.commit()

        for turn in range(4):
            # Reload history
            history = db.query(BuilderSandboxMessage).filter(BuilderSandboxMessage.session_id == session.session_id).order_by(BuilderSandboxMessage.created_at.asc()).all()
            history_text = ""
            for msg in history:
                role_label = "客户" if msg.sender == "customer" else "AI客服"
                history_text += f"{role_label}: {msg.content}\n"

            # Customer Simulator reply
            customer_text = simulate_customer_reply(c.persona, history_text)

            # Save customer message
            user_msg = BuilderSandboxMessage(
                message_id=str(uuid.uuid4()),
                session_id=session.session_id,
                sender="customer",
                content=customer_text
            )
            db.add(user_msg)
            db.commit()

            # Sandbox Agentic flow execution
            reply_text, trace = run_sandbox_agentic_flow(db, session, customer_text)

            # Save agent response
            agent_msg = BuilderSandboxMessage(
                message_id=str(uuid.uuid4()),
                session_id=session.session_id,
                sender="agent",
                content=reply_text,
                execution_trace=trace
            )
            db.add(agent_msg)
            db.commit()

            # Check if session is completed or disqualified-stopped
            if session.status == "completed" or "拒绝分期" in reply_text or "转接专属客户经理" in reply_text:
                break

        # Compile final history for the judge
        final_history = db.query(BuilderSandboxMessage).filter(BuilderSandboxMessage.session_id == session.session_id).order_by(BuilderSandboxMessage.created_at.asc()).all()
        final_history_text = ""
        transcript_list = []
        for msg in final_history:
            role_label = "customer" if msg.sender == "customer" else "agent"
            final_history_text += f"{role_label}: {msg.content}\n"
            transcript_list.append({
                "sender": role_label,
                "content": msg.content,
                "trace": msg.execution_trace
            })

        # 2. Invoke Judge
        audit = audit_conversation_with_judge(c.criteria, final_history_text)
        status = audit.get("status", "FAIL")
        error_type = audit.get("error_type", "none")
        reason = audit.get("reason", "未给出判定原理解析。")

        # Update single session status to audited
        session.status = "audited"
        db.commit()

        return {
            "case_id": c.case_id,
            "title": c.title,
            "status": status,
            "error_type": error_type,
            "reason": reason,
            "transcript": transcript_list
        }
    except Exception as e:
        logger.exception(f"Sandbox test case execution failed: {case_id}")
        return {
            "case_id": case_id,
            "title": f"Error Case {case_id}",
            "status": "FAIL",
            "error_type": "instruction_non_compliance",
            "reason": f"Execution error: {e}",
            "transcript": []
        }
    finally:
        db.close()

def execute_sandbox_test_run(run_id: str, agent_id: str):
    """
    Run simulation loop for all test cases and compile audit reports.
    """
    import concurrent.futures
    db = SessionLocal()
    try:
        run = db.query(BuilderTestRun).filter(BuilderTestRun.run_id == run_id).first()
        if not run:
            logger.warning(f"Test run {run_id} not found.")
            return

        cases = db.query(BuilderTestCase).filter(BuilderTestCase.agent_id == agent_id).all()
        if not cases:
            run.status = "failed"
            run.error_message = "No test cases configured."
            db.commit()
            return

        total_cases = len(cases)
        run.total_cases = total_cases
        db.commit()

        case_ids = [c.case_id for c in cases]

        details = []
        pass_count = 0
        fail_count = 0
        warn_count = 0

        # Use ThreadPoolExecutor to execute 12 test cases concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(run_single_case_in_thread, cid, agent_id): cid for cid in case_ids}
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    details.append(res)
                    status = res.get("status", "FAIL")
                    if status == "PASS":
                        pass_count += 1
                    elif status == "WARN":
                        warn_count += 1
                    else:
                        fail_count += 1

        # Sort details by case_id for consistency
        details.sort(key=lambda x: x["case_id"])

        # 3. Calculate metrics & generate recommendations
        pass_rate = (pass_count / total_cases) * 100.0 if total_cases > 0 else 0.0

        # Self-Optimization recommendation engine
        recommendations = []
        if fail_count > 0 or warn_count > 0:
            recommendations.append({
                "target_skill": "分期方案介绍",
                "warning": "AI 客服在依据不明时直接报出了具体的首付款和贷款期数，或者主动推荐了分期方案。",
                "rules": [
                    "建议补充规则 1.1: 只有确认到明确方案依据时，才能说首付、期数等具体数字。",
                    "建议补充规则 1.2: 依据不明确或客户未主动发起时只做保守说明，再顺势问预算。"
                ]
            })
            recommendations.append({
                "target_skill": "高意向转化与资格确认",
                "warning": "部分测试案例中，AI客服未能核实印尼本地工作性质或 KTP 身份证持状态便草率转接人工。",
                "rules": [
                    "建议补充规则 2.1: 在触发转接人工分支（Handoff）前，必须确认收集了 age >= 21, job, ktp 三个实体参数。",
                    "建议补充规则 2.2: 只要有一个资质项确认不合格，立刻引导至现金购买渠道，终止贷款流程。"
                ]
            })

        run.status = "completed"
        run.pass_rate = pass_rate
        run.pass_count = pass_count
        run.fail_count = fail_count
        run.warn_count = warn_count
        run.details = {
            "cases": details,
            "recommendations": recommendations
        }
        db.commit()
        logger.info(f"Sandbox test run {run_id} completed successfully. Pass rate: {pass_rate}%")

    except Exception as e:
        logger.exception("Sandbox test execution failed.")
        try:
            run = db.query(BuilderTestRun).filter(BuilderTestRun.run_id == run_id).first()
            if run:
                run.status = "failed"
                run.error_message = str(e)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
