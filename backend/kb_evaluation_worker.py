import threading
import time
import json
import logging
import requests
from datetime import datetime
from sqlalchemy import or_, and_
from database import SessionLocal, ApiAssistInvocation, WecomTriggerRecord
from config import settings

logger = logging.getLogger(__name__)

# Evaluation API Config from Settings
EVAL_API_URL = settings.LLM2_COMPARE_API_URL or "http://zjsphs.2288.org:11599/v1"
EVAL_API_KEY = settings.LLM2_COMPARE_API_KEY or "app-VyIZSsGidDjVbHsNhBaZY4or"
EVAL_MODEL = settings.LLM2_COMPARE_MODEL or "qwen3-480b-cloud"

def _post_json(url, headers, payload, timeout=1000):
    session = requests.Session()
    session.trust_env = settings.HTTP_TRUST_ENV
    return session.post(url, headers=headers, json=payload, timeout=timeout)

def call_evaluation_api(query, knowledge, generated_text, context_summary):
    """
    Calls the evaluation API to get a score and reason.
    """
    prompt = f"""你是一个专业的销售对话分析专家。请对本次知识库检索的质量进行评估。

【客户沟通上下文/意图摘要】：
{context_summary}

【客户当前问题/锚点消息】：
{query}

【检索到的知识库内容】：
{knowledge}

【AI生成的候选话术】：
{generated_text}

请从以下维度进行分析：
1. 针对性：检索到的知识是否直接回答了客户的问题或满足了当前的沟通需求。
2. 价值：提供的知识是否准确、专业、有深度。
3. 效果：在LLM2生成环节是否起到了实质性的支撑作用，提升了话术质量。

请输出一个 0-100 的综合评价分数，并提供简要说明。
必须以 JSON 格式返回，包含字段 "score" (数字) 和 "reason" (字符串)。
例如：{{"score": 85, "reason": "知识库精准命中了报价逻辑，LLM2 生成的话术非常专业且具有针对性。"}}
"""
    headers = {
        "Authorization": f"Bearer {EVAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        # Assuming Dify-style API based on the app- prefix in key
        if EVAL_API_KEY.startswith("app-"):
            payload = {
                "inputs": {},
                "query": prompt,
                "response_mode": "blocking",
                "user": "kb_eval_worker"
            }
            chat_url = EVAL_API_URL.rstrip("/") + "/chat-messages"
            response = _post_json(chat_url, headers, payload)
            if response.status_code != 200:
                logger.error(f"Eval API error: {response.status_code} {response.text}")
                return None, f"API Error: {response.status_code}"
            
            raw_answer = response.json().get("answer", "")
        else:
            # Fallback to OpenAI-compatible
            url = EVAL_API_URL.rstrip("/") + "/chat/completions"
            payload = {
                "model": EVAL_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            }
            response = _post_json(url, headers, payload)
            if response.status_code != 200:
                return None, f"API Error: {response.status_code}"
            raw_answer = response.json()["choices"][0]["message"]["content"]

        # Parse JSON from response
        # Find JSON block
        json_match = raw_answer.strip()
        if "```json" in json_match:
            json_match = json_match.split("```json")[1].split("```")[0].strip()
        elif "```" in json_match:
            json_match = json_match.split("```")[1].split("```")[0].strip()
        
        data = json.loads(json_match)
        return data.get("score"), data.get("reason")
    except Exception as e:
        logger.error(f"Error in call_evaluation_api: {e}")
        return None, str(e)

def process_eval_record(db, record, type_label):
    """
    Process a single record (ApiAssistInvocation or WecomTriggerRecord).
    """
    try:
        payload = record.result_payload if hasattr(record, "result_payload") else {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except:
                payload = {}
        if not payload or not isinstance(payload, dict):
            return False
        
        # We need query, KB content, and LLM output
        query = record.anchor_message_text or ""
        
        # KB1
        kb1_content = ""
        kb1_data = payload.get("knowledge_v2") or {}
        if isinstance(kb1_data, dict):
            hits = kb1_data.get("hits") or []
            kb1_content = "\n".join([h.get("content", "") for h in hits])
        
        # KB2
        kb2_content = ""
        kb2_data = payload.get("knowledge_external_api") or {}
        if isinstance(kb2_data, dict):
            hits = kb2_data.get("hits") or []
            kb2_content = "\n".join([h.get("content", "") for h in hits])
            
        # LLM Output (Main model candidates)
        candidates = payload.get("reply_style_results_v2") or []
        llm_out_kb1 = ""
        llm_out_kb2 = ""
        
        for c in candidates:
            if c.get("model_slot") == "llm2":
                text = f"风格: {c.get('style_title')}\n参考: {c.get('reply_reference')}\n思路: {c.get('followup_rationale')}"
                if c.get("knowledge_source") == "knowledge_v2":
                    llm_out_kb1 += text + "\n---\n"
                elif c.get("knowledge_source") == "knowledge_external_api":
                    llm_out_kb2 += text + "\n---\n"
        
        context_summary = ""
        if "llm1_summary" in payload:
            context_summary = json.dumps(payload["llm1_summary"], ensure_ascii=False)
        elif "summary" in payload:
             context_summary = json.dumps(payload["summary"], ensure_ascii=False)

        updated = False
        # Eval KB1
        if kb1_content and record.kb1_eval_score is None:
            score, reason = call_evaluation_api(query, kb1_content, llm_out_kb1, context_summary)
            if score is not None:
                record.kb1_eval_score = score
                record.kb1_eval_reason = reason
                updated = True
        
        # Eval KB2
        if kb2_content and record.kb2_eval_score is None:
            score, reason = call_evaluation_api(query, kb2_content, llm_out_kb2, context_summary)
            if score is not None:
                record.kb2_eval_score = score
                record.kb2_eval_reason = reason
                updated = True
        
        if updated:
            db.commit()
            return True
    except Exception as e:
        logger.error(f"Error processing {type_label} {getattr(record, 'invocation_id', getattr(record, 'record_id', 'unknown'))}: {e}")
        db.rollback()
    return False

def kb_evaluation_worker():
    """
    Background worker loop.
    """
    logger.info("Knowledge Base Evaluation Worker started.")
    # Start date filter: 2026-05-11
    start_date = datetime(2026, 5, 11)
    
    while True:
        db = SessionLocal()
        try:
            # Simplified query to avoid JSON containment operator issues
            # We fetch records that are missing evaluations and check the JSON content in Python
            api_candidates = db.query(ApiAssistInvocation).filter(
                ApiAssistInvocation.triggered_at >= start_date,
                or_(
                    ApiAssistInvocation.kb1_eval_score.is_(None),
                    ApiAssistInvocation.kb2_eval_score.is_(None)
                )
            ).all()
            
            trigger_candidates = db.query(WecomTriggerRecord).filter(
                WecomTriggerRecord.triggered_at >= start_date,
                or_(
                    WecomTriggerRecord.kb1_eval_score.is_(None),
                    WecomTriggerRecord.kb2_eval_score.is_(None)
                )
            ).all()
            
            if len(api_candidates) > 0 or len(trigger_candidates) > 0:
                logger.info(f"KB Eval Worker: SQL found {len(api_candidates)} ApiAssist and {len(trigger_candidates)} Trigger candidates.")

            # Filter candidates in Python to see if they actually have knowledge hits
            def has_kb_hits(record):
                payload = record.result_payload if hasattr(record, "result_payload") else {}
                if isinstance(payload, str):
                    try: payload = json.loads(payload)
                    except: payload = {}
                if not isinstance(payload, dict): return False
                
                # Check KB1
                kb1 = payload.get("knowledge_v2") or {}
                kb1_has_content = kb1.get("status") in ("hit", "manual_review_required") or len(kb1.get("hits") or []) > 0
                
                # Check KB2
                kb2 = payload.get("knowledge_external_api") or {}
                kb2_has_content = kb2.get("status") in ("hit", "manual_review_required") or len(kb2.get("hits") or []) > 0
                
                return (kb1_has_content and record.kb1_eval_score is None) or (kb2_has_content and record.kb2_eval_score is None)

            api_to_process = [r for r in api_candidates if has_kb_hits(r)]
            trigger_to_process = [r for r in trigger_candidates if has_kb_hits(r)]
            
            total_pending = len(api_to_process) + len(trigger_to_process)
            if total_pending > 0:
                logger.info(f"知识库评分开始：发现 {total_pending} 条待处理记录（ApiAssist: {len(api_to_process)}, Trigger: {len(trigger_to_process)}）")

            # 1. 处理 ApiAssistInvocation
            processed_count = 0
            for r in api_to_process[:10]: # 每次处理 10 条
                logger.info(f"正在评估 ApiAssist 记录: {r.invocation_id} ...")
                if process_eval_record(db, r, "ApiAssistInvocation"):
                    processed_count += 1
                    logger.info(f"ApiAssist 记录 {r.invocation_id} 评估完成。")
            
            if processed_count > 0:
                logger.info(f"知识库评分：成功处理 {processed_count} 条 ApiAssist 记录。")

            # 2. 处理 WecomTriggerRecord
            processed_count = 0
            for r in trigger_to_process[:10]:
                logger.info(f"正在评估 Trigger 记录: {r.record_id} ...")
                if process_eval_record(db, r, "WecomTriggerRecord"):
                    processed_count += 1
                    logger.info(f"Trigger 记录 {r.record_id} 评估完成。")
            
            if processed_count > 0:
                logger.info(f"知识库评分：成功处理 {processed_count} 条 WecomTriggerRecord 记录。")

        except Exception as e:
            logger.error(f"KB Eval Worker error: {e}")
        finally:
            db.close()
        
        # Sleep before next poll
        time.sleep(60)

def start_kb_evaluation_thread():
    t = threading.Thread(target=kb_evaluation_worker, daemon=True, name="kb-eval-worker")
    t.start()
    return t
