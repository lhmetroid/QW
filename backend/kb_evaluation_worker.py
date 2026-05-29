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
    # 2026-05-28: 知识库评估功能已注释停用
    return False

def kb_evaluation_worker():
    """
    Background worker loop.
    """
    logger.info("Knowledge Base Evaluation Worker is disabled/paused.")
    return

def start_kb_evaluation_thread():
    t = threading.Thread(target=kb_evaluation_worker, daemon=True, name="kb-eval-worker")
    t.start()
    return t
