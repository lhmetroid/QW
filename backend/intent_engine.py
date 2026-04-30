import re
import logging
from typing import Optional, List, Dict, Any
import requests
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from time import perf_counter
from fastapi import HTTPException
from sqlalchemy import or_
from config import settings
from qywx_utils import QYWXUtils
from database import SessionLocal, KnowledgeBase, IntentSummary, KnowledgeChunk, KnowledgeHitLog, PricingRule, ThreadBusinessFact
from embedding_service import EmbeddingService
from logging_config import sanitize_text
from knowledge_governance import validate_thread_state_consistency

logger = logging.getLogger(__name__)

class IntentEngine:
    """意图分析与提醒引擎"""

    @staticmethod
    def _post_json(url: str, headers: dict, payload: dict, timeout: int):
        session = requests.Session()
        session.trust_env = settings.HTTP_TRUST_ENV
        return session.post(url, headers=headers, json=payload, timeout=timeout)

    @classmethod
    def get_ai_settings(cls):
        import os, json
        filepath = os.path.join(os.path.dirname(__file__), "ai_settings.json")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 ai_settings.json 失败: {e}")
            raise RuntimeError(f"读取 ai_settings.json 失败: {e}") from e

    @classmethod
    def get_rules(cls):
        rules = cls.get_ai_settings().get("FAST_TRACK_RULES", [])
        if not rules:
            raise RuntimeError("ai_settings.json 缺少 FAST_TRACK_RULES")
        return rules

    @classmethod
    def get_prompt1(cls):
        prompt = cls.get_ai_settings().get("SYSTEM_PROMPT_LLM1")
        if not prompt:
            raise RuntimeError("ai_settings.json 缺少 SYSTEM_PROMPT_LLM1")
        return prompt

    @classmethod
    def get_prompt2(cls):
        prompt = cls.get_ai_settings().get("SYSTEM_PROMPT_LLM2")
        if not prompt:
            raise RuntimeError("ai_settings.json 缺少 SYSTEM_PROMPT_LLM2")
        return prompt

    @classmethod
    def get_reply_style_options(cls, enabled_only: bool = True) -> list[dict]:
        raw_options = cls.get_ai_settings().get("REPLY_STYLE_OPTIONS") or []
        options: list[dict] = []
        for idx, item in enumerate(raw_options):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"风格 {idx + 1}").strip()
            content = str(item.get("content") or "").strip()
            if not title and not content:
                continue
            style_id = str(item.get("id") or f"style_{idx + 1}").strip().lower()
            style_id = re.sub(r"[^a-z0-9_]+", "_", style_id).strip("_") or f"style_{idx + 1}"
            options.append({
                "id": style_id,
                "title": title,
                "content": content,
                "enabled": bool(item.get("enabled", True)),
            })
        if enabled_only:
            options = [item for item in options if item.get("enabled")]
        if options:
            return options
        return [{
            "id": "default_style",
            "title": "默认微信风格",
            "content": "微信口语化、简洁、自然，适合直接复制发送。",
            "enabled": True,
        }]

    @staticmethod
    def _llm_provider_label(api_key: str) -> str:
        return "Dify" if str(api_key or "").startswith("app-") else "OpenAI-compatible"

    @staticmethod
    def _is_meaningful_prompt_value(value) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            text = value.strip()
            return text not in {"", "无", "null", "None", "[]", "{}"}
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    @classmethod
    def sanitize_crm_context_for_prompt(cls, crm_context: dict | None) -> dict:
        crm = crm_context or {}
        allowed_keys = [
            "crm_contact_name",
            "company_name",
            "company_industry",
            "recent_opportunities",
            "recent_quote_summary",
            "ongoing_contracts",
            "contact_recent_followup",
            "customer_lifecycle_stage",
            "customer_tier",
            "payment_risk_level",
            "high_risk_flags",
        ]
        sanitized = {}
        for key in allowed_keys:
            value = crm.get(key)
            if cls._is_meaningful_prompt_value(value):
                sanitized[key] = value
        return sanitized

    @classmethod
    def sanitize_thread_fact_for_prompt(cls, thread_fact: dict | None) -> dict:
        fact = thread_fact or {}
        stage_signals = fact.get("stage_signals") or {}
        merged_facts = fact.get("merged_facts") or {}
        sanitized = {}
        for key in ["scenario_label", "intent_label", "language_style", "business_state", "reply_guard_reason"]:
            value = fact.get(key)
            if cls._is_meaningful_prompt_value(value):
                sanitized[key] = value
        allowed_stage_keys = [
            "has_formal_quote",
            "crm_has_quote_history",
            "waiting_customer_material",
            "awaiting_customer_reply",
            "sales_only_conversation",
            "followup_after_no_reply",
        ]
        filtered_stage_signals = {
            key: stage_signals.get(key)
            for key in allowed_stage_keys
            if key in stage_signals
        }
        if filtered_stage_signals:
            sanitized["stage_signals"] = filtered_stage_signals
        allowed_merged_keys = [
            "summary_status",
            "last_sender",
            "sales_message_count",
            "customer_message_count",
            "consecutive_sales_messages",
            "awaiting_customer_reply",
            "sales_only_conversation",
            "followup_after_no_reply",
            "latest_sales_message",
            "recent_sales_messages",
            "latest_customer_message",
            "crm_has_quote_history",
        ]
        filtered_merged_facts = {
            key: merged_facts.get(key)
            for key in allowed_merged_keys
            if cls._is_meaningful_prompt_value(merged_facts.get(key))
        }
        if filtered_merged_facts:
            sanitized["merged_facts"] = filtered_merged_facts
        return sanitized

    @classmethod
    def _followup_retrieval_hints(cls, thread_fact: dict | None) -> list[str]:
        merged_facts = (thread_fact or {}).get("merged_facts") or {}
        sales_messages = merged_facts.get("recent_sales_messages") or []
        if not sales_messages:
            latest_sales_message = str(merged_facts.get("latest_sales_message") or "").strip()
            if latest_sales_message:
                sales_messages = [latest_sales_message]
        hint_text = "\n".join(str(item or "") for item in sales_messages)
        hints = [
            "客户未回复后的跟进话术",
            "降低回复门槛",
            "二选一短问题",
            "补一个具体价值点",
            "避免重复上一轮外联",
        ]
        if any(word in hint_text for word in ["我是", "这边是", "负责", "Tiffany", "tiffany", "岚汇"]):
            hints.append("避免再次自我介绍")
        if any(word in hint_text for word in ["合作", "合作过", "合作记录"]):
            hints.append("避免重复合作背景")
        if any(word in hint_text for word in ["还负责", "是否负责", "您现在", "对接"]):
            hints.append("避免重复确认联系人是否负责")
            hints.append("若对方已不负责，礼貌获取当前对接人")
        if any(word in hint_text for word in ["项目资料", "资料", "整理"]):
            hints.append("不要围绕历史资料寒暄")
        return list(dict.fromkeys(item for item in hints if item))

    @classmethod
    def build_retrieval_query(cls, summary_json: dict | None, thread_fact: dict | None = None) -> str:
        summary = summary_json or {}
        parts: list[str] = []
        for key in ["core_demand", "topic", "status"]:
            value = str(summary.get(key) or "").strip()
            if value and value not in {"未明确", "[]", "{}"} and value not in parts:
                parts.append(value)
        stage_signals = (thread_fact or {}).get("stage_signals") or {}
        merged_facts = (thread_fact or {}).get("merged_facts") or {}
        latest_customer_message = str(merged_facts.get("latest_customer_message") or "").strip()
        if merged_facts.get("last_sender") == "customer" and latest_customer_message:
            parts.insert(0, f"优先回应客户最后一句：{latest_customer_message}")
            if re.search(r"(已有|已经有|我们有|现有).*(报告|资料|英文版|中英文|文档|译文|文件)", latest_customer_message):
                parts.insert(1, "客户已说明已有现成资料或双语内容，优先承接现状，不要跳回旧推进问题")
        if stage_signals.get("followup_after_no_reply") or stage_signals.get("awaiting_customer_reply"):
            for value in cls._followup_retrieval_hints(thread_fact):
                if value not in parts:
                    parts.append(value)
        if merged_facts.get("sales_only_conversation") and "初次触达后的二次跟进" not in parts:
            parts.append("初次触达后的二次跟进")
        return "；".join(dict.fromkeys(part for part in parts if part))

    @classmethod
    def build_sales_assist_request(
        cls,
        summary_json: dict,
        knowledge_list,
        crm_context: dict = None,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        label: str = "LLM2",
        reply_style: dict | None = None,
    ) -> dict:
        knowledge_context = cls.format_knowledge_context(knowledge_list)
        prompt2 = cls.get_prompt2()
        api_url = api_url if api_url is not None else settings.LLM2_API_URL
        api_key = api_key if api_key is not None else settings.LLM2_API_KEY
        model = model if model is not None else settings.LLM2_MODEL
        api_url = api_url or ""
        api_key = api_key or ""
        model = model or ""
        timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.LLM2_TIMEOUT_SECONDS

        summary_str = json.dumps(summary_json, ensure_ascii=False)
        crm_str = json.dumps(cls.sanitize_crm_context_for_prompt(crm_context), ensure_ascii=False)
        thread_fact = knowledge_list.get("thread_business_fact") if isinstance(knowledge_list, dict) else None
        thread_fact_str = json.dumps(cls.sanitize_thread_fact_for_prompt(thread_fact), ensure_ascii=False)
        style = reply_style or cls.get_reply_style_options(enabled_only=True)[0]
        style_title = str(style.get("title") or "默认微信风格").strip()
        style_content = str(style.get("content") or "").strip()
        style_prompt = f"{style_title}\n{style_content}".strip()
        merged_facts = (thread_fact or {}).get("merged_facts") or {}
        latest_customer_message = str(merged_facts.get("latest_customer_message") or "").strip()
        focus_note = ""
        if merged_facts.get("last_sender") == "customer" and latest_customer_message:
            focus_note = (
                f"\n\n【当前回复焦点】当前要直接回应的客户最后一句是：{latest_customer_message}"
                "\n请先直接回应这句客户消息，再决定是否补充下一步推进；不要跳回更早的旧追问或旧目标。"
            )
            if re.search(r"(已有|已经有|我们有|现有).*(报告|资料|英文版|中英文|文档|译文|文件)", latest_customer_message):
                focus_note += (
                    "\n客户最后一句是在说明现有资料/报告/双语版本的现状。"
                    "这类情况下请先做承接和确认，不要立刻改问负责人、报价或更早的旧推进问题。"
                    "\n不要把客户原话自动升级成更强判断，例如把“有中英文报告”扩写成“内部能搞定”“不需要”“婉拒当前需求”。"
                    "只承接客户已经明确说出的事实。"
                )

        final_prompt = prompt2
        if (
            "{{summary_json}}" in final_prompt
            or "{{knowledge_context}}" in final_prompt
            or "{{crm_context_json}}" in final_prompt
            or "{{thread_context_json}}" in final_prompt
            or "{{reply_style_prompt}}" in final_prompt
        ):
            final_prompt = final_prompt.replace("{{summary_json}}", summary_str)
            final_prompt = final_prompt.replace("{{knowledge_context}}", knowledge_context or "无相关参考")
            final_prompt = final_prompt.replace("{{crm_context_json}}", crm_str)
            final_prompt = final_prompt.replace("{{thread_context_json}}", thread_fact_str)
            final_prompt = final_prompt.replace("{{reply_style_prompt}}", style_prompt or "默认微信风格：微信口语化、简洁、自然。")
            final_prompt = f"{final_prompt}{focus_note}"
        else:
            final_prompt = (
                f"{prompt2}\n\n会话摘要档案：{summary_str}\n\n线程推进状态：{thread_fact_str}"
                f"\n\n本次回复风格要求：{style_prompt or '默认微信风格：微信口语化、简洁、自然。'}"
                f"\n\n内部 CRM 客户标签：{crm_str}\n\n参考知识库匹配：\n{knowledge_context or '无相关参考'}"
                f"{focus_note}"
            )

        return {
            "final_prompt": final_prompt,
            "api_url": api_url,
            "api_key": api_key,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "label": label,
            "prompt_trace": {
                "label": label,
                "model": model,
                "provider": cls._llm_provider_label(api_key),
                "api_url": api_url,
                "prompt": final_prompt,
                "prompt_chars": len(final_prompt or ""),
                "reply_style": style,
                "status": "ready",
                "sent_to_ai": True,
                "reason": "",
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
        }

    @classmethod
    def build_llm1_request(
        cls,
        context: List[dict],
        *,
        user_id: str,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        label: str = "LLM1",
    ) -> dict:
        conversation_text = ""
        for msg in context:
            speaker = "客户" if msg.get("sender_type") == "customer" else "销售"
            conversation_text += f"[{speaker}]: {msg.get('content', '')}\n"

        prompt1 = cls.get_prompt1()
        if "{{conversation_text}}" in prompt1:
            full_prompt = prompt1.replace("{{conversation_text}}", conversation_text)
        else:
            full_prompt = f"{prompt1}\n\n请分析以下企微真实对话记录：\n{conversation_text}"

        api_url = api_url if api_url is not None else settings.LLM1_API_URL
        api_key = api_key if api_key is not None else settings.LLM1_API_KEY
        model = model if model is not None else settings.LLM1_MODEL
        timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.LLM1_TIMEOUT_SECONDS
        return {
            "user_id": user_id,
            "full_prompt": full_prompt,
            "api_url": api_url or "",
            "api_key": api_key or "",
            "model": model or "",
            "timeout_seconds": timeout_seconds,
            "label": label,
            "prompt_trace": {
                "label": label,
                "model": model or "",
                "provider": cls._llm_provider_label(api_key),
                "api_url": api_url or "",
                "prompt": full_prompt,
                "prompt_chars": len(full_prompt or ""),
                "status": "ready",
                "sent_to_ai": True,
                "reason": "",
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
        }

    @classmethod
    def run_llm1_request(cls, request_spec: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {request_spec.get('api_key') or ''}",
            "Content-Type": "application/json"
        }
        full_prompt = request_spec.get("full_prompt") or ""
        api_key = request_spec.get("api_key") or ""
        api_url = request_spec.get("api_url") or ""
        model = request_spec.get("model") or ""
        timeout_seconds = request_spec.get("timeout_seconds") or settings.LLM1_TIMEOUT_SECONDS
        user_id = request_spec.get("user_id") or "llm1"
        label = request_spec.get("label") or "LLM1"
        prompt_trace = dict(request_spec.get("prompt_trace") or {})
        raw_text = ""

        try:
            prompt_trace["request_started_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            if api_key.startswith("app-"):
                url = api_url.rstrip('/') + "/chat-messages"
                payload = {
                    "inputs": {},
                    "query": full_prompt,
                    "response_mode": "blocking",
                    "user": user_id
                }
                cls._log_llm_prompt(f"{label}_DIFY", model, url, full_prompt)
                response = cls._post_json(url, headers, payload, timeout_seconds)
                if response.status_code == 404:
                    url = api_url.rstrip('/') + "/completion-messages"
                    cls._log_llm_prompt(f"{label}_DIFY_COMPLETION", model, url, full_prompt)
                    response = cls._post_json(url, headers, payload, timeout_seconds)
                prompt_trace["response_status_code"] = response.status_code
                prompt_trace["response_received_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                if response.status_code != 200:
                    raise RuntimeError(f"Dify 接口错误: HTTP {response.status_code}")
                raw_text = response.json().get("answer", "")
            else:
                url = api_url.rstrip('/') + "/chat/completions"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": 0.1
                }
                cls._log_llm_prompt(f"{label}_OPENAI", model, url, full_prompt)
                response = cls._post_json(url, headers, payload, timeout_seconds)
                prompt_trace["response_status_code"] = response.status_code
                prompt_trace["response_received_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                if response.status_code != 200:
                    raise RuntimeError(f"OpenAI 协议接口错误: HTTP {response.status_code}")
                res_data = response.json()
                raw_text = res_data["choices"][0]["message"]["content"] if "choices" in res_data else ""

            parsed = json.loads(cls._strip_json_fences(raw_text))
            prompt_trace["result"] = "success"
            return {
                "summary": parsed,
                "raw_text": raw_text,
                "prompt_trace": prompt_trace,
            }
        except json.JSONDecodeError as e:
            prompt_trace["result"] = "json_error"
            prompt_trace["reason"] = sanitize_text(str(e))
            logger.error("LLM-1 返回 JSON 解析失败: %s", e)
            raise RuntimeError(f"LLM-1 最终提取的 JSON 无法解析: {e}") from e
        except Exception as e:
            prompt_trace["result"] = "error"
            prompt_trace["reason"] = sanitize_text(str(e))
            logger.error("LLM-1 调用彻底失败: %s", e)
            raise

    @staticmethod
    def _log_llm_prompt(label: str, model: str, url: str, prompt: str):
        if not settings.LOG_LLM_PROMPTS:
            return
        max_chars = settings.LOG_LLM_PROMPT_MAX_CHARS
        prompt_text = prompt or ""
        truncated = len(prompt_text) > max_chars
        logged_prompt = sanitize_text(prompt_text[:max_chars]) if settings.LOG_DESENSITIZE_ENABLED else prompt_text[:max_chars]
        logger.info(
            "LLM_PROMPT_%s %s",
            label,
            json.dumps(
                {
                    "model": model,
                    "url": url,
                    "prompt_chars": len(prompt_text),
                    "truncated": truncated,
                    "prompt": logged_prompt,
                },
                ensure_ascii=True,
            ),
        )

    @staticmethod
    def _strip_json_fences(raw_text: str) -> str:
        text = (raw_text or "").strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    @classmethod
    def run_llm1_json_prompt(cls, prompt: str, user_id: str = "kb_assist"):
        """Run the configured LLM-1 endpoint with a custom prompt and parse JSON."""
        headers = {
            "Authorization": f"Bearer {settings.LLM1_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            if settings.LLM1_API_KEY.startswith("app-"):
                url = settings.LLM1_API_URL.rstrip("/") + "/chat-messages"
                payload = {
                    "inputs": {},
                    "query": prompt,
                    "response_mode": "blocking",
                    "user": user_id
                }
                cls._log_llm_prompt("KB_ASSIST_DIFY", settings.LLM1_MODEL, url, prompt)
                response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                if response.status_code == 404:
                    url = settings.LLM1_API_URL.rstrip("/") + "/completion-messages"
                    cls._log_llm_prompt("KB_ASSIST_DIFY_COMPLETION", settings.LLM1_MODEL, url, prompt)
                    response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                if response.status_code != 200:
                    raise RuntimeError(f"知识库 LLM 辅助 Dify 调用失败: HTTP {response.status_code}")
                raw_text = response.json().get("answer", "")
            else:
                url = settings.LLM1_API_URL.rstrip("/") + "/chat/completions"
                payload = {
                    "model": settings.LLM1_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                cls._log_llm_prompt("KB_ASSIST_OPENAI", settings.LLM1_MODEL, url, prompt)
                response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                if response.status_code != 200:
                    raise RuntimeError(f"知识库 LLM 辅助 OpenAI-compatible 调用失败: HTTP {response.status_code}")
                data = response.json()
                raw_text = data["choices"][0]["message"]["content"] if "choices" in data else ""
            return json.loads(cls._strip_json_fences(raw_text))
        except json.JSONDecodeError as e:
            logger.error("知识库 LLM 辅助返回 JSON 解析失败: %s", e)
            raise RuntimeError(f"知识库 LLM 辅助返回 JSON 解析失败: {e}") from e
        except Exception as e:
            logger.error("知识库 LLM 辅助调用异常: %s", e)
            raise

    @classmethod
    def fast_track_scan(cls, user_id: str, content: str):
        """旁路强信号实时扫描"""
        found_signals = []
        for rule in cls.get_rules():
            if re.search(rule["pattern"], content, re.IGNORECASE):
                found_signals.append(rule["name"])
        
        if found_signals:
            signal_str = "、".join(found_signals)
            logger.info(f"检测到强信号: {signal_str}")
            # 构造提醒卡片
            title = f"🔔 [AI实时提醒] - {found_signals[0]}"
            description = (
                f"<div class=\"gray\">信号类别：{signal_str}</div>\n"
                f"<div class=\"normal\">客户原话：\"{content}\"</div>\n"
                f"<div class=\"highlight\">建议：客户表达了明确需求/风险点，请尽快跟进。</div>"
            )
            QYWXUtils.send_text_card(user_id, title, description)
        
        return found_signals

    @classmethod
    def get_embedding(cls, text: str) -> Optional[List[float]]:
        """调用接口获取文本向量"""
        return EmbeddingService.embed(text)

    @classmethod
    def retrieve_knowledge(cls, query_text: str, top_k: int = 1) -> List[str]:
        """执行向量检索 (降级版：从 DB 拉取后在本地运行相似度运算)"""
        db = SessionLocal()
        try:
            results = db.query(KnowledgeBase).filter(KnowledgeBase.embedding.isnot(None)).all()
            if not results:
                raise RuntimeError("旧知识库为空，无法执行 retrieve_knowledge")

            vector = cls.get_embedding(query_text)
                
            import math
            def cosine_sim(v1, v2):
                if not v1 or not v2 or len(v1) != len(v2): return 0
                dot = sum(a*b for a, b in zip(v1, v2))
                norm1 = math.sqrt(sum(a*a for a in v1))
                norm2 = math.sqrt(sum(b*b for b in v2))
                return dot / (norm1 * norm2) if norm1 and norm2 else 0

            scored_docs = []
            for r in results:
                if r.embedding:
                    sim = cosine_sim(vector, r.embedding)
                    scored_docs.append((sim, r.content))
                    
            scored_docs.sort(key=lambda x: x[0], reverse=True)
            return [doc[1] for doc in scored_docs[:top_k]]
        except Exception as e:
            logger.error(f"RAG 本地检索异常: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def _cosine_sim(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        import math
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

    @staticmethod
    def _knowledge_class_for_chunk(chunk: KnowledgeChunk) -> str | None:
        tags = chunk.structured_tags if isinstance(chunk.structured_tags, dict) else {}
        class_code = tags.get("knowledge_class")
        if class_code:
            if class_code == "script":
                return "email_template"
            return class_code
        if chunk.knowledge_type == "pricing" and chunk.chunk_type == "constraint":
            return "pricing_constraint"
        if chunk.knowledge_type == "capability":
            return "capability"
        if chunk.knowledge_type == "process":
            return "process"
        if chunk.chunk_type == "example":
            return "example"
        if chunk.chunk_type == "template":
            return "email_template"
        if chunk.chunk_type == "definition":
            return "definition"
        if chunk.knowledge_type == "faq":
            return "faq"
        return None

    @staticmethod
    def _knowledge_class_fields(class_code: str | None) -> dict | None:
        return {
            "pricing_constraint": {"knowledge_type": "pricing", "chunk_type": "constraint"},
            "capability": {"knowledge_type": "capability", "chunk_type": "rule"},
            "process": {"knowledge_type": "process", "chunk_type": "rule"},
            "faq": {"knowledge_type": "faq", "chunk_type": "faq"},
            "example": {"knowledge_type": "faq", "chunk_type": "example"},
            "script": {"knowledge_type": "faq", "chunk_type": "template"},
            "email_template": {"knowledge_type": "faq", "chunk_type": "template"},
            "definition": {"knowledge_type": "faq", "chunk_type": "definition"},
        }.get(class_code or "")

    @staticmethod
    def _tokenize_query_text(query_text: str) -> list[str]:
        text = (query_text or "").lower().strip()
        if not text:
            return []
        terms: list[str] = []
        domain_terms = [
            "医药", "医学", "医疗", "药物", "注册资料", "临床", "说明书", "冠脉", "球囊", "导管",
            "案例", "客户案例", "项目案例", "翻译", "笔译", "口译", "同传", "资料", "合同",
            "法律", "技术", "报价", "收费", "价格", "流程", "交付", "发票", "含税", "加急",
            "客户", "经验", "能力", "服务范围", "质检", "审校",
        ]
        for term in domain_terms:
            if term.lower() in text and term.lower() not in terms:
                terms.append(term.lower())
        for token in re.split(r"[\s,，。；;、/？?！!：:（）()《》\"']+", text):
            token = token.strip()
            if len(token) >= 2 and token not in terms:
                terms.append(token)
        chinese_chars = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", text)
        if len(chinese_chars) <= 12:
            for size in (4, 3, 2):
                for idx in range(0, max(len(chinese_chars) - size + 1, 0)):
                    gram = chinese_chars[idx:idx + size]
                    if len(gram) >= 2 and gram not in terms:
                        terms.append(gram)
        return terms[:16]

    @staticmethod
    def _keyword_score(query_text: str, chunk: KnowledgeChunk) -> float:
        query = (query_text or "").lower()
        haystack = "\n".join([
            chunk.title or "",
            chunk.content or "",
            chunk.keyword_text or "",
            chunk.language_pair or "",
            chunk.service_scope or "",
            chunk.sub_service or "",
        ]).lower()
        if not query or not haystack:
            return 0.0

        score = 0.0
        for token in IntentEngine._tokenize_query_text(query):
            if len(token) >= 2 and token in haystack:
                score += 1.0
        for field in [chunk.title, chunk.language_pair, chunk.service_scope]:
            value = (field or "").lower()
            if value and value in query:
                score += 1.0
        return min(score / 5.0, 1.0)

    @staticmethod
    def _query_terms(query_text: str) -> List[str]:
        return IntentEngine._tokenize_query_text(query_text)[:10]

    @staticmethod
    def _exact_phrase_score(query_text: str, chunk: KnowledgeChunk) -> float:
        query = (query_text or "").lower().strip()
        haystack = "\n".join([chunk.title or "", chunk.content or "", chunk.keyword_text or ""]).lower()
        if not query or not haystack:
            return 0.0
        if len(query) >= 4 and query in haystack:
            return 1.0
        terms = IntentEngine._tokenize_query_text(query)
        if not terms:
            return 0.0
        matched = sum(1 for term in terms if len(term) >= 2 and term in haystack)
        return min(matched / max(len(terms), 1), 1.0)

    @staticmethod
    def _bm25ish_score(query_terms: list[str], chunk: KnowledgeChunk) -> float:
        haystack = "\n".join([chunk.title or "", chunk.content or "", chunk.keyword_text or ""]).lower()
        if not query_terms or not haystack:
            return 0.0
        score = 0.0
        for term in query_terms:
            if len(term) < 2:
                continue
            count = haystack.count(term)
            if count:
                score += min(1.0, 0.45 + (count * 0.18))
        return min(score / max(len(query_terms), 1), 1.0)

    @staticmethod
    def _metadata_match_score(features: Dict[str, Any], chunk: KnowledgeChunk) -> float:
        checks = [
            ("business_line", chunk.business_line),
            ("language_pair", chunk.language_pair),
            ("service_scope", chunk.service_scope),
            ("customer_tier", chunk.customer_tier),
        ]
        matched = 0
        total = 0
        for key, value in checks:
            expected = features.get(key)
            if not expected:
                continue
            total += 1
            if value in {expected, None, ""}:
                matched += 1
        return matched / total if total else 0.5

    @classmethod
    def _query_intent_profile(cls, query_text: str, features: Dict[str, Any]) -> dict:
        query = (query_text or "").lower().strip()
        desired_classes: list[str] = []
        desired_types: list[str] = []
        reasons: list[str] = []
        if any(word in query for word in ["案例", "客户案例", "项目案例", "做过", "经验", "客户有哪些", "客户有"]):
            desired_classes.append("example")
            desired_types.append("faq")
            reasons.append("case_intent")
        if any(word in query for word in ["能做", "可做", "是否支持", "能不能", "服务范围", "资料类型", "可以翻译", "能翻译"]):
            desired_classes.append("capability")
            desired_types.append("capability")
            reasons.append("capability_intent")
        if any(word in query for word in ["流程", "怎么", "如何", "步骤", "交付", "下单", "多久", "进度"]):
            desired_classes.append("process")
            desired_types.append("process")
            reasons.append("process_intent")
        if any(word in query for word in ["多少钱", "报价", "价格", "收费", "费用", "最低", "加急", "含税", "发票", "折扣"]):
            desired_classes.extend(["pricing_constraint"])
            desired_types.append("pricing")
            reasons.append("pricing_intent")
        if any(word in query for word in ["话术", "邮件", "怎么回复"]):
            desired_classes.append("email_template")
            desired_types.append("faq")
            reasons.append("template_intent")
        if any(word in query for word in ["未回复", "没回", "跟进", "二次跟进", "再联系", "轻一点"]):
            desired_classes.extend(["email_template", "process", "faq"])
            desired_types.extend(["faq", "process"])
            reasons.append("followup_intent")

        explicit_class = features.get("knowledge_class")
        if explicit_class:
            explicit_values = explicit_class if isinstance(explicit_class, list) else [explicit_class]
            desired_classes = [value for value in explicit_values if value]
            reasons.append("explicit_knowledge_class")

        domain_terms = [term for term in ["医药", "医学", "医疗", "药物", "注册资料", "临床", "说明书", "法律", "合同", "技术"] if term in query]
        generic_terms = {"医药", "医学", "医疗", "翻译", "报价", "案例", "客户", "资料", "流程", "价格"}
        query_terms = cls._query_terms(query)
        meaningful_terms = [term for term in query_terms if term not in generic_terms]
        has_actionable_intent = bool(desired_classes or desired_types)
        ambiguous = (
            bool(query)
            and len(query) <= 6
            and len(meaningful_terms) <= 1
            and not (has_actionable_intent and domain_terms)
        )
        return {
            "desired_knowledge_classes": list(dict.fromkeys(desired_classes)),
            "desired_knowledge_types": list(dict.fromkeys(desired_types)),
            "domain_terms": domain_terms,
            "ambiguous_query": ambiguous,
            "intent_reasons": reasons,
            "query_terms": query_terms,
        }

    @classmethod
    def _intent_score(cls, profile: dict, chunk: KnowledgeChunk) -> float:
        desired_classes = set(profile.get("desired_knowledge_classes") or [])
        desired_types = set(profile.get("desired_knowledge_types") or [])
        chunk_class = cls._knowledge_class_for_chunk(chunk)
        score = 0.0
        if desired_classes:
            score = 1.0 if chunk_class in desired_classes else 0.0
            if "example" in desired_classes and chunk.chunk_type == "example":
                score = 1.0
        elif desired_types:
            score = 0.8 if chunk.knowledge_type in desired_types else 0.0
        else:
            score = 0.5
        haystack = "\n".join([chunk.title or "", chunk.content or "", chunk.keyword_text or ""]).lower()
        if profile.get("domain_terms"):
            domain_hit = any(term in haystack for term in profile["domain_terms"])
            score = (score * 0.75) + (0.25 if domain_hit else 0.0)
        return min(score, 1.0)

    @staticmethod
    def _commercial_thresholds(features: Dict[str, Any]) -> dict:
        return {
            "min_score": float(features.get("min_score", 0.45) or 0.45),
            "auto_ok_score": float(features.get("auto_ok_score", 0.70) or 0.70),
            "supporting_score": float(features.get("supporting_score", 0.35) or 0.35),
        }

    @staticmethod
    def _followup_strategy_score(features: Dict[str, Any], chunk: KnowledgeChunk) -> float:
        if features.get("followup_strategy") != "awaiting_customer_reply":
            return 0.0
        haystack = "\n".join([chunk.title or "", chunk.content or "", chunk.keyword_text or ""]).lower()
        followup_focus = str(features.get("followup_focus") or "").strip()
        scope = str(chunk.service_scope or "").strip().lower()
        owner_terms = ["负责人", "对口负责人", "负责", "不负责", "对接人", "对接", "同事", "转给", "转达", "联系人"]
        low_threshold_terms = ["二选一", "方便", "短问题", "顺手回", "回复", "回应", "跟进", "提醒"]
        generic_intro_terms = [
            "公司简介", "服务范围", "感谢您", "很高兴能再次", "期待能", "祝您", "优势", "背景铺垫", "再次联系",
            "专业可靠", "满怀期待", "回想起过去的合作",
        ]
        score = 0.0
        if scope in {"contact_discovery", "contact_follow_up", "sales_outreach"}:
            score = max(score, 0.85)
        if any(term in haystack for term in owner_terms):
            score = max(score, 1.2)
        elif any(term in haystack for term in low_threshold_terms):
            score = max(score, 0.55)

        if followup_focus == "owner_confirmation":
            if scope == "contact_discovery":
                score = max(score, 1.25)
            elif scope == "contact_follow_up":
                score = max(score, 0.8)
            elif scope == "sales_outreach":
                score -= 1.0
            if any(term in haystack for term in owner_terms):
                score = max(score, 1.25)
            else:
                score -= 0.55
            if any(term in haystack for term in ["很早就有合作", "20多年", "资深项目负责人", "我是上海交大事必达的", "加微信", "供应商信息"]):
                score -= 0.8

        if any(term in haystack for term in generic_intro_terms) and not any(term in haystack for term in owner_terms):
            score -= 1.0

        return max(min(score, 1.25), -1.25)

    @staticmethod
    def _structured_pricing_auto_ready(features: Dict[str, Any], hit: Dict[str, Any] | None, min_score: float) -> bool:
        if not hit or hit.get("knowledge_type") != "pricing":
            return False
        if not hit.get("usable_for_reply") or not hit.get("allowed_for_generation"):
            return False
        if not hit.get("pricing_rules") or hit.get("pricing_rule_missing"):
            return False
        if (hit.get("score") or 0.0) < max(min_score, 0.5):
            return False
        expected_language_pair = features.get("language_pair")
        if expected_language_pair and hit.get("language_pair") != expected_language_pair:
            return False
        expected_service_scope = features.get("service_scope")
        if expected_service_scope and hit.get("service_scope") != expected_service_scope:
            return False
        return True

    @classmethod
    def _chunk_summary(cls, chunk: KnowledgeChunk, score_payload: dict | None = None, relation: str = "related") -> dict:
        score_payload = score_payload or {}
        content = chunk.content or ""
        return {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "chunk_no": chunk.chunk_no,
            "knowledge_class": cls._knowledge_class_for_chunk(chunk),
            "knowledge_type": chunk.knowledge_type,
            "chunk_type": chunk.chunk_type,
            "title": chunk.title,
            "content": content,
            "snippet": content[:240],
            "score": score_payload.get("score"),
            "semantic_score": score_payload.get("semantic_score"),
            "keyword_score": score_payload.get("keyword_score"),
            "exact_phrase_score": score_payload.get("exact_phrase_score"),
            "intent_score": score_payload.get("intent_score"),
            "metadata_score": score_payload.get("metadata_score"),
            "bm25_score": score_payload.get("bm25_score"),
            "business_line": chunk.business_line,
            "sub_service": chunk.sub_service,
            "language_pair": chunk.language_pair,
            "service_scope": chunk.service_scope,
            "region": chunk.region,
            "customer_tier": chunk.customer_tier,
            "library_type": chunk.library_type,
            "allowed_for_generation": chunk.allowed_for_generation,
            "usable_for_reply": chunk.usable_for_reply,
            "publishable": chunk.publishable,
            "useful_score": float(chunk.useful_score) if chunk.useful_score is not None else None,
            "effect_score": float(chunk.effect_score) if getattr(chunk, "effect_score", None) is not None else None,
            "feedback_count": getattr(chunk, "feedback_count", 0),
            "relation": relation,
            "applicability": "supporting" if relation == "supporting" else "same_document_context",
        }

    @staticmethod
    def _constraint_applies(query_text: str, chunk: KnowledgeChunk, keyword_score: float) -> bool:
        if keyword_score > 0:
            return True
        query = (query_text or "").lower()
        haystack = "\n".join([chunk.title or "", chunk.content or "", chunk.keyword_text or ""]).lower()
        guard_terms = [
            "火星语",
            "未知语种",
            "同步传译",
            "特殊折扣",
            "折扣价",
            "从没发布",
            "未发布",
            "未授权",
            "编造价格",
        ]
        return any(term in query and term in haystack for term in guard_terms)

    @staticmethod
    def _is_definition_query(query_text: str) -> bool:
        query = (query_text or "").lower()
        patterns = [
            "是什么",
            "什么意思",
            "含义",
            "定义",
            "区别",
            "简称",
            "全称",
            "指什么",
            "是什么意思",
        ]
        return any(pattern in query for pattern in patterns)

    @staticmethod
    def _definition_alias_markers() -> list[str]:
        return ["简称", "别名", "品牌名", "品牌别名", "也叫", "又称", "指我们公司", "我们公司", "公司简称"]

    @classmethod
    def _is_alias_definition(cls, chunk: KnowledgeChunk) -> bool:
        haystack = "\n".join([chunk.title or "", chunk.content or ""])
        return any(marker in haystack for marker in cls._definition_alias_markers())

    @classmethod
    def _extract_alias_terms(cls, chunk: KnowledgeChunk) -> list[str]:
        if chunk.chunk_type != "definition":
            return []
        title = (chunk.title or "").strip()
        content = (chunk.content or "").strip()
        if not title:
            return []
        terms = [title]
        patterns = [
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,24})是([\u4e00-\u9fa5A-Za-z0-9·]{2,24})的(?:公司)?(?:简称|别名|品牌别名|品牌名)",
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,24})也叫([\u4e00-\u9fa5A-Za-z0-9·]{2,24})",
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,24})又称([\u4e00-\u9fa5A-Za-z0-9·]{2,24})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                for value in match.groups():
                    value = (value or "").strip("：:，,。；; ")
                    if 2 <= len(value) <= 24 and value not in terms:
                        terms.append(value)
        for pattern in [r"(?:简称|别名|品牌名|品牌别名)[：: ]*([\u4e00-\u9fa5A-Za-z0-9·/、，, ]{2,40})"]:
            match = re.search(pattern, content)
            if not match:
                continue
            for value in re.split(r"[/、，, ]+", match.group(1)):
                value = (value or "").strip()
                if 2 <= len(value) <= 24 and value not in terms:
                    terms.append(value)
        return terms

    @classmethod
    def _definition_score_multiplier(cls, query_text: str, chunk: KnowledgeChunk) -> float:
        if chunk.chunk_type != "definition":
            return 1.0
        if cls._is_definition_query(query_text):
            return 1.2
        if cls._is_alias_definition(chunk):
            return 0.08
        return 0.25

    @classmethod
    def _score_bucket(cls, query_text: str, chunk: KnowledgeChunk) -> int:
        if chunk.chunk_type != "definition":
            return 0
        if cls._is_definition_query(query_text):
            return 0
        return 2 if cls._is_alias_definition(chunk) else 1

    @classmethod
    def _normalize_query_with_alias_hints(cls, db, query_text: str) -> str:
        text = (query_text or "").strip()
        if not text:
            return text
        try:
            alias_chunks = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.status == "active",
                KnowledgeChunk.chunk_type == "definition",
            ).limit(200).all()
        except Exception:
            return text

        augmented_terms = []
        for chunk in alias_chunks:
            alias_terms = cls._extract_alias_terms(chunk)
            if not alias_terms:
                continue
            if not any(term in text for term in alias_terms):
                continue
            for term in alias_terms:
                if term not in text and term not in augmented_terms:
                    augmented_terms.append(term)
            if cls._is_alias_definition(chunk):
                augmented_terms.extend(["公司", "本公司"])
        if not augmented_terms:
            return text
        return f"{text} {' '.join(dict.fromkeys(augmented_terms))}".strip()

    @classmethod
    def retrieve_knowledge_v2(
        cls,
        query_text: str,
        query_features: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """知识库 V2 检索：只返回知识证据包，不生成销售回复。"""
        started = perf_counter()
        features = query_features or {}
        filters_used = {
            "status": "active",
            "business_line": features.get("business_line"),
            "knowledge_class": features.get("knowledge_class"),
            "knowledge_type": features.get("knowledge_type"),
            "language_pair": features.get("language_pair"),
            "service_scope": features.get("service_scope"),
            "service_scope_allowlist": features.get("service_scope_allowlist"),
            "customer_tier": features.get("customer_tier"),
            "effective_time": "now",
            "candidate_limit": settings.KB_CANDIDATE_LIMIT,
            "keyword_prefilter_enabled": settings.KB_KEYWORD_PREFILTER_ENABLED,
        }

        db = SessionLocal()
        try:
            normalized_query_text = cls._normalize_query_with_alias_hints(db, query_text)
            vector = cls.get_embedding(normalized_query_text)
            now = datetime.utcnow()
            thread_fact_model = None
            thread_fact = None
            if session_id:
                thread_fact_model = db.query(ThreadBusinessFact).filter(ThreadBusinessFact.session_id == session_id).first()
                if thread_fact_model:
                    thread_fact = {
                        "session_id": thread_fact_model.session_id,
                        "business_state": thread_fact_model.business_state,
                        "scenario_label": thread_fact_model.scenario_label,
                        "intent_label": thread_fact_model.intent_label,
                        "language_style": thread_fact_model.language_style,
                        "stage_signals": thread_fact_model.stage_signals or {},
                        "merged_facts": thread_fact_model.merged_facts or {},
                        "attachment_summary": thread_fact_model.attachment_summary or [],
                        "quality_score": float(thread_fact_model.quality_score) if thread_fact_model.quality_score is not None else None,
                        "usable_for_reply": thread_fact_model.usable_for_reply,
                        "allowed_for_generation": thread_fact_model.allowed_for_generation,
                        "reply_guard_reason": thread_fact_model.reply_guard_reason,
                    }
            query = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.status == "active",
                or_(KnowledgeChunk.effective_from.is_(None), KnowledgeChunk.effective_from <= now),
                or_(KnowledgeChunk.effective_to.is_(None), KnowledgeChunk.effective_to >= now),
            )

            if features.get("business_line"):
                query = query.filter(KnowledgeChunk.business_line == features["business_line"])

            knowledge_type = features.get("knowledge_type")
            if isinstance(knowledge_type, list):
                query = query.filter(KnowledgeChunk.knowledge_type.in_(knowledge_type))
            elif knowledge_type:
                query = query.filter(KnowledgeChunk.knowledge_type == knowledge_type)

            explicit_knowledge_classes = []
            knowledge_class = features.get("knowledge_class")
            if isinstance(knowledge_class, list):
                explicit_knowledge_classes = [item for item in knowledge_class if item]
            elif knowledge_class:
                explicit_knowledge_classes = [knowledge_class]
            explicit_class_fields = [
                class_fields
                for class_fields in (cls._knowledge_class_fields(item) for item in explicit_knowledge_classes)
                if class_fields
            ]
            if len(explicit_class_fields) == 1:
                query = query.filter(KnowledgeChunk.knowledge_type == explicit_class_fields[0]["knowledge_type"])
                query = query.filter(KnowledgeChunk.chunk_type == explicit_class_fields[0]["chunk_type"])
            elif explicit_class_fields:
                query = query.filter(KnowledgeChunk.knowledge_type.in_({item["knowledge_type"] for item in explicit_class_fields}))

            if features.get("language_pair"):
                query = query.filter(or_(
                    KnowledgeChunk.language_pair == features["language_pair"],
                    KnowledgeChunk.language_pair.is_(None),
                ))

            if features.get("service_scope"):
                query = query.filter(or_(
                    KnowledgeChunk.service_scope == features["service_scope"],
                    KnowledgeChunk.service_scope.is_(None),
                ))
            elif isinstance(features.get("service_scope_allowlist"), list) and features.get("service_scope_allowlist"):
                allowlist = [item for item in features["service_scope_allowlist"] if item]
                if allowlist:
                    query = query.filter(or_(
                        KnowledgeChunk.service_scope.in_(allowlist),
                        KnowledgeChunk.service_scope.is_(None),
                    ))

            if features.get("customer_tier"):
                query = query.filter(or_(
                    KnowledgeChunk.customer_tier == features["customer_tier"],
                    KnowledgeChunk.customer_tier.is_(None),
                ))

            candidate_limit = max(20, min(int(settings.KB_CANDIDATE_LIMIT or 500), 2000))
            candidate_query = query
            query_terms = cls._query_terms(normalized_query_text)
            intent_profile = cls._query_intent_profile(normalized_query_text, features)
            thresholds = cls._commercial_thresholds(features)
            filters_used["normalized_query_text"] = normalized_query_text
            filters_used["query_terms"] = query_terms
            filters_used["intent_profile"] = {
                "desired_knowledge_classes": intent_profile.get("desired_knowledge_classes"),
                "desired_knowledge_types": intent_profile.get("desired_knowledge_types"),
                "domain_terms": intent_profile.get("domain_terms"),
                "ambiguous_query": intent_profile.get("ambiguous_query"),
                "intent_reasons": intent_profile.get("intent_reasons"),
            }
            filters_used["thresholds"] = thresholds
            filters_used["thread_business_state"] = thread_fact.get("business_state") if thread_fact else None
            filters_used["thread_fact_available"] = bool(thread_fact)

            candidate_sources_by_id: dict[str, set[str]] = {}
            candidates_by_id: dict[str, KnowledgeChunk] = {}

            def add_candidates(items, source: str):
                for item in items:
                    chunk_id = str(item.chunk_id)
                    candidates_by_id[chunk_id] = item
                    candidate_sources_by_id.setdefault(chunk_id, set()).add(source)

            structured_candidates = candidate_query.order_by(KnowledgeChunk.priority.desc()).limit(candidate_limit).all()
            add_candidates(structured_candidates, "structured_filters")
            keyword_candidates = []
            if settings.KB_KEYWORD_PREFILTER_ENABLED and query_terms:
                keyword_conditions = []
                for term in query_terms:
                    like_term = f"%{term}%"
                    keyword_conditions.extend([
                        KnowledgeChunk.title.ilike(like_term),
                        KnowledgeChunk.keyword_text.ilike(like_term),
                        KnowledgeChunk.content.ilike(like_term),
                    ])
                if keyword_conditions:
                    keyword_candidates = (
                        query.filter(or_(*keyword_conditions))
                        .order_by(KnowledgeChunk.priority.desc())
                        .limit(candidate_limit)
                        .all()
                    )
                    add_candidates(keyword_candidates, "keyword_prefilter")

            candidates = list(candidates_by_id.values())
            if explicit_knowledge_classes:
                candidates = [
                    chunk for chunk in candidates
                    if cls._knowledge_class_for_chunk(chunk) in set(explicit_knowledge_classes)
                ]
            filters_used["candidate_source"] = "hybrid_structured_keyword"
            filters_used["candidate_counts_by_source"] = {
                "structured_filters": len(structured_candidates),
                "keyword_prefilter": len(keyword_candidates),
                "merged": len(candidates),
            }
            filters_used["candidate_count"] = len(candidates)
            scored = []
            for chunk in candidates:
                semantic_score = cls._cosine_sim(vector, chunk.embedding) if vector and chunk.embedding else 0.0
                keyword_score = cls._keyword_score(normalized_query_text, chunk)
                exact_phrase_score = cls._exact_phrase_score(normalized_query_text, chunk)
                bm25_score = cls._bm25ish_score(query_terms, chunk)
                intent_score = cls._intent_score(intent_profile, chunk)
                metadata_score = cls._metadata_match_score(features, chunk)
                priority_score = min((chunk.priority or 50) / 100.0, 1.0)
                quality_score = float(chunk.useful_score) if chunk.useful_score is not None else 0.45
                effect_score = float(chunk.effect_score) if getattr(chunk, "effect_score", None) is not None else 0.5
                generation_score = 1.0 if chunk.usable_for_reply else (0.75 if chunk.allowed_for_generation else 0.45)
                followup_strategy_score = cls._followup_strategy_score(features, chunk)
                definition_multiplier = cls._definition_score_multiplier(normalized_query_text, chunk)
                final_score = round((
                    (semantic_score * 0.45)
                    + (keyword_score * 0.12)
                    + (bm25_score * 0.10)
                    + (exact_phrase_score * 0.12)
                    + (intent_score * 0.12)
                    + (metadata_score * 0.04)
                    + (priority_score * 0.05)
                    + (quality_score * 0.06)
                    + (effect_score * 0.03)
                    + (generation_score * 0.04)
                    + (followup_strategy_score * 0.08)
                ) * definition_multiplier, 6)
                if semantic_score > 0 or keyword_score > 0 or exact_phrase_score > 0 or bm25_score > 0:
                    source_tags = sorted(candidate_sources_by_id.get(str(chunk.chunk_id), set()))
                    scored.append((
                        cls._score_bucket(normalized_query_text, chunk),
                        final_score,
                        semantic_score,
                        keyword_score,
                        exact_phrase_score,
                        intent_score,
                        metadata_score,
                        bm25_score,
                        quality_score,
                        effect_score,
                        generation_score,
                        followup_strategy_score,
                        source_tags,
                        chunk,
                    ))

            scored.sort(key=lambda item: (item[0], -item[1], -item[2], -item[4], -item[5]))
            hits = []
            score_by_chunk_id: dict[str, dict[str, Any]] = {}
            for _bucket, final_score, semantic_score, keyword_score, exact_phrase_score, intent_score, metadata_score, bm25_score, quality_score, effect_score, generation_score, followup_strategy_score, source_tags, chunk in scored:
                score_by_chunk_id[str(chunk.chunk_id)] = {
                    "score": final_score,
                    "semantic_score": round(semantic_score, 6),
                    "keyword_score": round(keyword_score, 6),
                    "exact_phrase_score": round(exact_phrase_score, 6),
                    "intent_score": round(intent_score, 6),
                    "metadata_score": round(metadata_score, 6),
                    "bm25_score": round(bm25_score, 6),
                    "candidate_sources": source_tags,
                    "quality_score": round(quality_score, 6),
                    "effect_score": round(effect_score, 6),
                    "generation_score": round(generation_score, 6),
                    "followup_strategy_score": round(followup_strategy_score, 6),
                }
            for _bucket, final_score, semantic_score, keyword_score, exact_phrase_score, intent_score, metadata_score, bm25_score, quality_score, effect_score, generation_score, followup_strategy_score, source_tags, chunk in scored[:top_k]:
                is_constraint = chunk.chunk_type == "constraint" or bool((chunk.structured_tags or {}).get("manual_review_required"))
                constraint_applies = is_constraint and cls._constraint_applies(query_text, chunk, keyword_score)
                pricing_rules = []
                pricing_rule_missing = False
                if chunk.knowledge_type == "pricing" and not is_constraint:
                    active_rules = db.query(PricingRule).filter(
                        PricingRule.status == "active",
                        PricingRule.document_id == chunk.document_id,
                        or_(PricingRule.chunk_id == chunk.chunk_id, PricingRule.chunk_id.is_(None)),
                        or_(PricingRule.effective_from.is_(None), PricingRule.effective_from <= now),
                        or_(PricingRule.effective_to.is_(None), PricingRule.effective_to >= now),
                    ).all()
                    pricing_rules = [
                        {
                            "rule_id": str(rule.rule_id),
                            "document_id": str(rule.document_id),
                            "chunk_id": str(rule.chunk_id) if rule.chunk_id else None,
                            "business_line": rule.business_line,
                            "language_pair": rule.language_pair,
                            "service_scope": rule.service_scope,
                            "unit": rule.unit,
                            "currency": rule.currency,
                            "price_min": float(rule.price_min) if rule.price_min is not None else None,
                            "price_max": float(rule.price_max) if rule.price_max is not None else None,
                            "urgent_multiplier": float(rule.urgent_multiplier) if rule.urgent_multiplier is not None else None,
                            "tax_policy": rule.tax_policy,
                            "min_charge": float(rule.min_charge) if rule.min_charge is not None else None,
                            "customer_tier": rule.customer_tier,
                            "region": rule.region,
                            "version_no": rule.version_no,
                            "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
                            "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
                        }
                        for rule in active_rules
                    ]
                    pricing_rule_missing = not pricing_rules
                hits.append({
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "knowledge_class": cls._knowledge_class_for_chunk(chunk),
                    "knowledge_type": chunk.knowledge_type,
                    "chunk_type": chunk.chunk_type,
                    "title": chunk.title,
                    "content": chunk.content,
                    "score": final_score,
                    "semantic_score": round(semantic_score, 6),
                    "keyword_score": round(keyword_score, 6),
                    "exact_phrase_score": round(exact_phrase_score, 6),
                    "intent_score": round(intent_score, 6),
                    "metadata_score": round(metadata_score, 6),
                    "bm25_score": round(bm25_score, 6),
                    "candidate_sources": source_tags,
                    "library_type": chunk.library_type,
                    "allowed_for_generation": chunk.allowed_for_generation,
                    "usable_for_reply": chunk.usable_for_reply,
                    "publishable": chunk.publishable,
                    "useful_score": float(chunk.useful_score) if chunk.useful_score is not None else None,
                    "effect_score": float(chunk.effect_score) if getattr(chunk, "effect_score", None) is not None else None,
                    "feedback_count": getattr(chunk, "feedback_count", 0),
                    "positive_feedback_count": getattr(chunk, "positive_feedback_count", 0),
                    "quality_notes": chunk.quality_notes,
                    "priority": chunk.priority,
                    "followup_strategy_score": round(followup_strategy_score, 6),
                    "business_line": chunk.business_line,
                    "sub_service": chunk.sub_service,
                    "language_pair": chunk.language_pair,
                    "service_scope": chunk.service_scope,
                    "region": chunk.region,
                    "customer_tier": chunk.customer_tier,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dim": chunk.embedding_dim,
                    "pricing_rules": pricing_rules,
                    "pricing_rule_missing": pricing_rule_missing,
                    "insufficient_info": pricing_rule_missing or constraint_applies or not bool(chunk.usable_for_reply),
                    "manual_review_required": pricing_rule_missing or constraint_applies or not bool(chunk.usable_for_reply),
                    "applicability": "constraint" if constraint_applies else "matched",
                })

            replyable_hits = [hit for hit in hits if hit.get("usable_for_reply") and hit.get("allowed_for_generation")]
            human_only_hits = [hit for hit in hits if hit not in replyable_hits]
            filters_used["replyable_hit_count"] = len(replyable_hits)
            filters_used["human_only_hit_count"] = len(human_only_hits)

            hit_chunk_ids = {hit["chunk_id"] for hit in hits}
            hit_document_ids = list(dict.fromkeys(hit["document_id"] for hit in hits))
            related_chunks = []
            supporting_chunks = []
            if hit_document_ids:
                siblings = (
                    db.query(KnowledgeChunk)
                    .filter(
                        KnowledgeChunk.status == "active",
                        KnowledgeChunk.document_id.in_(hit_document_ids),
                        or_(KnowledgeChunk.effective_from.is_(None), KnowledgeChunk.effective_from <= now),
                        or_(KnowledgeChunk.effective_to.is_(None), KnowledgeChunk.effective_to >= now),
                    )
                    .order_by(KnowledgeChunk.document_id.asc(), KnowledgeChunk.chunk_no.asc())
                    .limit(max(40, top_k * 8))
                    .all()
                )
                for sibling in siblings:
                    sibling_id = str(sibling.chunk_id)
                    if sibling_id in hit_chunk_ids:
                        continue
                    score_payload = score_by_chunk_id.get(sibling_id)
                    if score_payload and (score_payload.get("score") or 0) >= thresholds["supporting_score"]:
                        supporting_chunks.append(cls._chunk_summary(sibling, score_payload, relation="supporting"))
                    else:
                        related_chunks.append(cls._chunk_summary(sibling, score_payload, relation="related"))
            filters_used["related_chunk_count"] = len(related_chunks)
            filters_used["supporting_chunk_count"] = len(supporting_chunks)

            effective_hits = replyable_hits or hits
            confidence_score = effective_hits[0]["score"] if effective_hits else 0.0
            min_score = thresholds["min_score"]
            auto_ok_score = thresholds["auto_ok_score"]
            structured_pricing_auto_ready = cls._structured_pricing_auto_ready(
                features,
                replyable_hits[0] if replyable_hits else None,
                min_score,
            )
            any_manual_review = any(hit.get("manual_review_required") for hit in effective_hits)
            any_insufficient = any(hit.get("insufficient_info") for hit in effective_hits)
            if not hits:
                status = "no_applicable_knowledge"
                no_hit_reason = "未命中符合 active 状态、适用范围与有效期过滤条件的知识"
                retrieval_quality = "no_hit"
                insufficient_info = True
                manual_review_required = True
            elif not replyable_hits:
                status = "manual_review_required"
                no_hit_reason = "命中知识存在，但当前都只适合人工参考，未达到自动回复可用标准"
                retrieval_quality = "human_only_evidence"
                insufficient_info = False
                manual_review_required = True
            elif intent_profile.get("ambiguous_query"):
                status = "ambiguous_query"
                no_hit_reason = "客户问题过于宽泛，需要先澄清要查案例、能力、报价、流程还是话术"
                retrieval_quality = "needs_clarification"
                insufficient_info = True
                manual_review_required = True
            elif confidence_score < min_score:
                status = "low_confidence"
                no_hit_reason = f"最高命中分 {confidence_score} 低于阈值 {min_score}"
                retrieval_quality = "low_confidence"
                insufficient_info = True
                manual_review_required = True
            elif confidence_score < auto_ok_score and not structured_pricing_auto_ready:
                status = "manual_review_required"
                no_hit_reason = f"最高命中分 {confidence_score} 未达到自动可用阈值 {auto_ok_score}"
                retrieval_quality = "needs_review"
                insufficient_info = True
                manual_review_required = True
            elif any_manual_review or any_insufficient:
                status = "manual_review_required"
                no_hit_reason = "命中结果存在需要人工复核的知识证据"
                retrieval_quality = "needs_review"
                insufficient_info = any_insufficient
                manual_review_required = True
            else:
                status = "ok"
                no_hit_reason = None
                retrieval_quality = "high_confidence"
                insufficient_info = False
                manual_review_required = False

            evidence_context = {
                "rules": [],
                "faqs": [],
                "cases": [],
                "supporting": [],
                "human_only": human_only_hits,
            }
            for hit in replyable_hits:
                if hit.get("chunk_type") in {"rule", "constraint"} or hit["knowledge_type"] == "pricing" or hit.get("pricing_rules"):
                    evidence_context["rules"].append(hit)
                elif hit.get("chunk_type") in {"example", "template"}:
                    evidence_context["cases"].append(hit)
                else:
                    evidence_context["faqs"].append(hit)
            evidence_context["supporting"] = supporting_chunks
            latency_ms = round((perf_counter() - started) * 1000)

            log = KnowledgeHitLog(
                request_id=request_id,
                session_id=session_id,
                query_text=query_text or "",
                query_features=features,
                filters_used=filters_used,
                hit_chunk_ids=[hit["chunk_id"] for hit in hits],
                scores=[hit["score"] for hit in hits],
                no_hit_reason=no_hit_reason,
                status=status,
                retrieval_quality=retrieval_quality,
                confidence_score=confidence_score,
                insufficient_info=insufficient_info,
                manual_review_required=manual_review_required,
                latency_ms=latency_ms,
            )
            db.add(log)
            db.commit()

            return {
                "status": status,
                "query_text": query_text,
                "query_features": features,
                "filters_used": filters_used,
                "hits": hits,
                "replyable_hits": replyable_hits,
                "human_only_hits": human_only_hits,
                "supporting_chunks": supporting_chunks,
                "related_chunks": related_chunks,
                "evidence_context": evidence_context,
                "evidence_refs": cls.build_evidence_refs({"hits": replyable_hits}),
                "confidence_score": confidence_score,
                "retrieval_quality": retrieval_quality,
                "insufficient_info": insufficient_info,
                "manual_review_required": manual_review_required,
                "no_hit_reason": no_hit_reason,
                "latency_ms": latency_ms,
                "log_id": str(log.log_id),
                "thread_business_fact": thread_fact,
            }
        except Exception as e:
            db.rollback()
            logger.error("知识库 V2 检索异常: %s", e)
            raise RuntimeError(f"知识库 V2 检索异常: {e}") from e
        finally:
            db.close()

    @staticmethod
    def infer_query_features(
        summary_json: Dict[str, Any],
        crm_context: Dict[str, Any] | None = None,
        thread_fact: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """从 V1 摘要生成知识库 V2 检索过滤字段；宁可少过滤，不误伤候选。"""
        text = json.dumps(summary_json or {}, ensure_ascii=False)
        merged_facts = (thread_fact or {}).get("merged_facts") or {}
        latest_customer_message = str(merged_facts.get("latest_customer_message") or "").strip()
        if latest_customer_message:
            text = f"{text}\n{latest_customer_message}"
        features: Dict[str, Any] = {}

        if any(word in text for word in ["翻译", "口译", "同传", "字幕", "配音", "语种", "英译", "中译"]):
            features["business_line"] = "translation"
        elif any(word in text for word in ["印刷", "画册", "手册", "样本", "易拉宝"]):
            features["business_line"] = "printing"
        elif any(word in text for word in ["展台", "展会", "搭建", "撤展"]):
            features["business_line"] = "exhibition"
        else:
            features["business_line"] = "general"

        knowledge_types = []
        if any(word in text for word in ["报价", "价格", "多少钱", "收费", "费用", "最低收费", "折扣", "税", "发票"]):
            knowledge_types.append("pricing")
        if any(word in text for word in ["能做", "可做", "是否支持", "业务范围", "服务范围", "能不能", "可以翻译", "能翻译"]):
            knowledge_types.append("capability")
        if any(word in text for word in ["流程", "怎么", "如何", "步骤", "周期", "交付"]):
            knowledge_types.append("process")
        if any(word in text for word in ["案例", "客户案例", "项目案例", "做过", "经验"]):
            features["knowledge_class"] = "example"
        knowledge_types.append("faq")
        features["knowledge_type"] = list(dict.fromkeys(knowledge_types))

        language_patterns = [
            ("en->fr", ["英译法", "英文翻法文", "英语翻法语"]),
            ("en->zh", ["英译中", "英文翻中文", "英语翻中文"]),
            ("zh->en", ["中译英", "中文翻英文", "中文翻英语"]),
            ("zh->ja", ["中译日", "中文翻日文", "中文翻日语"]),
            ("fr->zh", ["法译中", "法文翻中文", "法语翻中文"]),
            ("zh->fr", ["中译法", "中文翻法文", "中文翻法语"]),
            ("de->zh", ["德译中", "德文翻中文", "德语翻中文"]),
            ("zh->de", ["中译德", "中文翻德文", "中文翻德语"]),
            ("en->ru", ["英译俄", "英文翻俄文", "英语翻俄语"]),
            ("ru->zh", ["俄译中", "俄文翻中文", "俄语翻中文"]),
            ("zh->ru", ["中译俄", "中文翻俄文", "中文翻俄语"]),
            ("ja->zh", ["日译中", "日文翻中文"]),
            ("ko->zh", ["韩译中", "韩文翻中文"]),
            ("zh->ko", ["中译韩", "中文翻韩文", "中文翻韩语"]),
            ("it->zh", ["意译中", "意文翻中文", "意大利语翻中文"]),
            ("zh->it", ["中译意", "中文翻意文", "中文翻意大利语"]),
            ("es->zh", ["西译中", "西文翻中文", "西班牙语翻中文"]),
            ("zh->es", ["中译西", "中文翻西文", "中文翻西班牙语"]),
            ("ar->zh", ["阿译中", "阿拉伯语翻中文"]),
            ("zh->ar", ["中译阿", "中文翻阿拉伯语"]),
            ("da->zh", ["丹麦语译中", "丹麦文翻中文"]),
            ("zh->da", ["中译丹麦语", "中文翻丹麦语"]),
            ("pt->zh", ["葡译中", "葡萄牙语翻中文", "葡文翻中文"]),
            ("zh->pt", ["中译葡", "中文翻葡萄牙语", "中文翻葡文"]),
            ("nl->zh", ["荷译中", "荷兰语翻中文", "荷文翻中文"]),
            ("zh->nl", ["中译荷", "中文翻荷兰语", "中文翻荷文"]),
            ("sv->zh", ["瑞典语译中", "瑞典文翻中文"]),
            ("zh->sv", ["中译瑞典语", "中文翻瑞典语"]),
            ("no->zh", ["挪威语译中", "挪威文翻中文"]),
            ("zh->no", ["中译挪威语", "中文翻挪威语"]),
            ("el->zh", ["希腊语译中", "希腊文翻中文"]),
            ("zh->el", ["中译希腊语", "中文翻希腊语"]),
            ("tr->zh", ["土耳其语译中", "土耳其文翻中文"]),
            ("zh->tr", ["中译土耳其语", "中文翻土耳其语"]),
            ("fr->en", ["法译英", "法文翻英文", "法语翻英语"]),
            ("de->en", ["德译英", "德文翻英文", "德语翻英语"]),
            ("en->de", ["英译德", "英文翻德文", "英语翻德语"]),
            ("en->ja", ["英译日", "英文翻日文", "英语翻日语"]),
            ("ja->en", ["日译英", "日文翻英文", "日语翻英语"]),
            ("en->en", ["英文润稿", "英文母语润稿", "英语润稿"]),
        ]
        for code, words in language_patterns:
            if any(word in text for word in words):
                features["language_pair"] = code
                break

        if any(word in text for word in ["法律", "合同", "法务"]):
            features["service_scope"] = "legal"
        elif any(word in text for word in ["医药", "医学", "医疗", "药品", "药物", "注册资料", "临床"]):
            features["service_scope"] = "medical"
        elif any(word in text for word in ["技术", "说明书", "工程"]):
            features["service_scope"] = "technical"
        elif any(word in text for word in ["认证", "盖章", "公证"]):
            features["service_scope"] = "certified"
        elif features.get("business_line") == "translation":
            features["service_scope"] = "general"

        crm = crm_context or {}
        crm_customer_tier = crm.get("customer_tier")
        if crm_customer_tier in {"key", "vip", "strategic"}:
            features["customer_tier"] = crm_customer_tier
        if crm.get("payment_risk_level") == "high":
            features["manual_review_hint"] = True

        stage_signals = (thread_fact or {}).get("stage_signals") or {}
        if stage_signals.get("followup_after_no_reply") or stage_signals.get("awaiting_customer_reply"):
            features["followup_strategy"] = "awaiting_customer_reply"
            features["knowledge_class"] = ["email_template", "process", "faq"]
            if features.get("service_scope") == "general":
                features.pop("service_scope", None)
            features["service_scope_allowlist"] = ["general", "contact_discovery", "contact_follow_up", "sales_outreach"]
            followup_knowledge_types = ["faq", "process"]
            existing_types = features.get("knowledge_type") or []
            if not isinstance(existing_types, list):
                existing_types = [existing_types]
            features["knowledge_type"] = list(dict.fromkeys(followup_knowledge_types + [item for item in existing_types if item]))
            role_focus_text = " ".join(
                str(item or "")
                for item in [
                    (summary_json or {}).get("core_demand"),
                    (summary_json or {}).get("topic"),
                    latest_customer_message,
                    merged_facts.get("latest_sales_message"),
                    " ".join(merged_facts.get("recent_sales_messages") or []),
                ]
            )
            if any(word in role_focus_text for word in ["负责", "负责人", "对接", "同事", "转给"]):
                features["followup_focus"] = "owner_confirmation"

        return features

    @staticmethod
    def format_knowledge_context(knowledge_payload) -> str:
        """把 V2 证据包按规则/FAQ/案例三段格式化为 AI 可用上下文，兼容旧 list[str]。"""
        if not knowledge_payload:
            return ""
        if isinstance(knowledge_payload, list):
            return "\n".join([f"- 参考知识: {item}" for item in knowledge_payload])

        evidence = knowledge_payload.get("evidence_context") if isinstance(knowledge_payload, dict) else None
        if not evidence:
            hits = knowledge_payload.get("hits", []) if isinstance(knowledge_payload, dict) else []
            evidence = {"rules": [], "faqs": [], "cases": hits}

        def render_hit(hit: dict) -> str:
            lines = [
                f"- 标题: {hit.get('title')}",
                f"  内容: {hit.get('content')}",
            ]
            for rule in hit.get("pricing_rules") or []:
                lines.append(
                    "  报价规则: "
                    f"rule_id={rule.get('rule_id')}, version={rule.get('version_no')}, "
                    f"unit={rule.get('unit')}, currency={rule.get('currency')}, "
                    f"price_min={rule.get('price_min')}, price_max={rule.get('price_max')}, "
                    f"min_charge={rule.get('min_charge')}, effective={rule.get('effective_from')}~{rule.get('effective_to')}"
                )
            if hit.get("manual_review_required"):
                lines.append("  风险: 该知识需要人工复核，不能直接生成确定性承诺。")
            return "\n".join(lines)

        sections = [
            ("[规则型知识]", evidence.get("rules") or []),
            ("[FAQ型知识]", evidence.get("faqs") or []),
            ("[案例型知识]", evidence.get("cases") or []),
            ("[补充证据]", evidence.get("supporting") or []),
        ]
        rendered = []
        for title, hits in sections:
            rendered.append(title)
            rendered.append("\n".join(render_hit(hit) for hit in hits) if hits else "- 无")
        return "\n".join(rendered)

    @staticmethod
    def _normalize_numeric(value) -> str | None:
        if value in (None, ""):
            return None
        try:
            return str(Decimal(str(value)).normalize())
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def build_evidence_refs(cls, knowledge_payload) -> List[Dict[str, Any]]:
        if not isinstance(knowledge_payload, dict):
            return []
        refs: List[Dict[str, Any]] = []
        seen = set()
        for hit in knowledge_payload.get("hits") or []:
            chunk_ref_id = f"chunk:{hit.get('chunk_id')}"
            if hit.get("chunk_id") and chunk_ref_id not in seen:
                refs.append({
                    "ref_id": chunk_ref_id,
                    "ref_type": "chunk",
                    "document_id": hit.get("document_id"),
                    "chunk_id": hit.get("chunk_id"),
                    "knowledge_type": hit.get("knowledge_type"),
                    "title": hit.get("title"),
                    "score": hit.get("score"),
                    "business_line": hit.get("business_line"),
                    "service_scope": hit.get("service_scope"),
                    "snippet": sanitize_text((hit.get("content") or "")[:160]),
                })
                seen.add(chunk_ref_id)
            for rule in hit.get("pricing_rules") or []:
                rule_ref_id = f"pricing_rule:{rule.get('rule_id')}"
                if rule.get("rule_id") and rule_ref_id not in seen:
                    refs.append({
                        "ref_id": rule_ref_id,
                        "ref_type": "pricing_rule",
                        "document_id": rule.get("document_id"),
                        "chunk_id": rule.get("chunk_id"),
                        "rule_id": rule.get("rule_id"),
                        "title": hit.get("title"),
                        "knowledge_type": "pricing",
                        "version_no": rule.get("version_no"),
                        "business_line": rule.get("business_line"),
                        "service_scope": rule.get("service_scope"),
                        "summary": {
                            "unit": rule.get("unit"),
                            "currency": rule.get("currency"),
                            "price_min": rule.get("price_min"),
                            "price_max": rule.get("price_max"),
                            "min_charge": rule.get("min_charge"),
                            "urgent_multiplier": rule.get("urgent_multiplier"),
                            "effective_from": rule.get("effective_from"),
                            "effective_to": rule.get("effective_to"),
                        },
                    })
                    seen.add(rule_ref_id)
        return refs

    @classmethod
    def validate_sales_assist_output(cls, response_text: str | None, knowledge_payload, crm_context: dict | None = None) -> Dict[str, Any]:
        text = (response_text or "").strip()
        hits = knowledge_payload.get("hits") if isinstance(knowledge_payload, dict) else []
        thread_fact = knowledge_payload.get("thread_business_fact") if isinstance(knowledge_payload, dict) else None
        evidence_refs = cls.build_evidence_refs(knowledge_payload)
        warnings: List[str] = []
        blocking_issues: List[str] = []
        pricing_rules = [rule for hit in hits for rule in (hit.get("pricing_rules") or [])]

        pricing_mentions = re.findall(r"(\d+(?:\.\d+)?)\s*(元|%|％|倍)", text)
        if "/千字" in text or "每千字" in text:
            pricing_mentions.extend((match, "千字") for match in re.findall(r"(\d+(?:\.\d+)?)\s*(?:元\s*/?\s*(?:每)?千字)", text))
        mentioned_numbers = [cls._normalize_numeric(value) for value, _unit in pricing_mentions]
        mentioned_numbers = [value for value in mentioned_numbers if value is not None]
        allowed_numbers = {
            normalized
            for rule in pricing_rules
            for normalized in [
                cls._normalize_numeric(rule.get("price_min")),
                cls._normalize_numeric(rule.get("price_max")),
                cls._normalize_numeric(rule.get("min_charge")),
                cls._normalize_numeric(rule.get("urgent_multiplier")),
            ]
            if normalized is not None
        }
        if mentioned_numbers:
            if not pricing_rules:
                blocking_issues.append("话术包含价格/倍率数字，但当前没有命中结构化 pricing_rule 证据。")
            else:
                unmatched = sorted({value for value in mentioned_numbers if value not in allowed_numbers})
                if unmatched:
                    blocking_issues.append(f"话术包含未在 pricing_rule 中出现的数字: {', '.join(unmatched)}")

        capability_claim_patterns = [
            r"能做", r"可做", r"支持", r"可承接", r"可以承接", r"能够提供", r"可以安排",
        ]
        capability_claimed = any(re.search(pattern, text) for pattern in capability_claim_patterns)
        capability_hits = [
            hit for hit in hits
            if hit.get("knowledge_type") in {"capability", "faq", "process"}
        ]
        if capability_claimed and not capability_hits:
            blocking_issues.append("话术包含能力/流程承诺，但当前没有命中对应 active 知识证据。")

        if isinstance(knowledge_payload, dict) and knowledge_payload.get("manual_review_required"):
            warnings.append("知识检索本身已标记人工复核，话术必须保守使用。")

        crm = crm_context or {}
        if crm.get("recent_quote_summary") and mentioned_numbers:
            warnings.append("CRM 中存在历史报价记录，当前价格承诺需以现行 pricing_rule 为准。")
        if crm.get("payment_risk_level") == "high" and (mentioned_numbers or capability_claimed):
            warnings.append("当前客户存在较高回款/跟进风险，报价或能力承诺建议人工复核。")
        thread_state_validation = validate_thread_state_consistency(text, thread_fact)
        warnings.extend(thread_state_validation.get("warnings") or [])
        blocking_issues.extend(thread_state_validation.get("blocking_issues") or [])

        manual_review_required = bool(blocking_issues) or bool(knowledge_payload.get("manual_review_required")) if isinstance(knowledge_payload, dict) else bool(blocking_issues)
        if crm.get("payment_risk_level") == "high" and (mentioned_numbers or capability_claimed):
            manual_review_required = True
        return {
            "status": "manual_review_required" if manual_review_required else "ok",
            "manual_review_required": manual_review_required,
            "warnings": warnings,
            "blocking_issues": blocking_issues,
            "evidence_refs": evidence_refs,
            "thread_business_fact": thread_fact,
        }

    @staticmethod
    def build_safe_assist_response(summary_json: dict, validation: dict) -> str:
        topic = (summary_json or {}).get("topic") or "当前需求"
        issues = validation.get("blocking_issues") or ["知识证据不足"]
        issue_lines = "\n".join(f"- {item}" for item in issues[:3])
        return (
            f"当前关于“{topic}”的知识证据不足，涉及报价、能力或流程承诺请先人工确认。\n"
            f"{issue_lines}\n"
            "- 建议先向客户补充确认资料类型、语种、用途、交付要求。\n"
            "- 再依据已发布知识或请运营/负责人复核后回复。"
        )

    @staticmethod
    def _needs_followup_rewrite_retry(validation: dict | None) -> bool:
        issues = validation.get("blocking_issues") or [] if isinstance(validation, dict) else []
        return any("客户未回复后的跟进" in item or "不能复述旧话术" in item for item in issues)

    @staticmethod
    def build_followup_guard_response(summary_json: dict | None = None) -> str:
        return (
            "【企微回复参考】\n"
            "不多打扰，想确认下这块近期还有在推进吗？您回我“有/暂时没有”都行。\n\n"
            "【跟进思路说明】\n"
            "客户未回复时先降门槛，不重复自我介绍和旧问题，用最短确认口拿状态信号。"
        )

    @staticmethod
    def extract_reply_reference_text(response_text: str | None) -> str:
        text = str(response_text or "").strip()
        if not text:
            return ""
        match = re.search(r"【企微回复参考】\s*(.*?)\s*(?:【跟进思路说明】|$)", text, flags=re.S)
        if match:
            return match.group(1).strip()
        return text.splitlines()[0].strip()

    @staticmethod
    def _char_ngram_set(text: str, size: int = 2) -> set[str]:
        normalized = re.sub(r"\s+", "", str(text or ""))
        if not normalized:
            return set()
        if len(normalized) <= size:
            return {normalized}
        return {normalized[idx:idx + size] for idx in range(0, len(normalized) - size + 1)}

    @classmethod
    def _text_overlap_ratio(cls, left: str | None, right: str | None) -> float:
        left_set = cls._char_ngram_set(left or "")
        right_set = cls._char_ngram_set(right or "")
        if not left_set or not right_set:
            return 0.0
        union = left_set | right_set
        if not union:
            return 0.0
        return len(left_set & right_set) / len(union)

    @staticmethod
    def _clamp_score(value: float, minimum: int = 0, maximum: int = 100) -> int:
        return int(max(minimum, min(maximum, round(value))))

    @classmethod
    def _reply_dimension_scores(
        cls,
        *,
        reply_text: str,
        validation: dict | None,
        summary_json: dict | None,
        thread_fact: dict | None,
        style: dict | None,
    ) -> dict:
        validation = validation or {}
        style = style or {}
        merged_facts = (thread_fact or {}).get("merged_facts") or {}
        latest_sales_message = str(merged_facts.get("latest_sales_message") or "").strip()
        recent_sales_messages = [str(item or "").strip() for item in (merged_facts.get("recent_sales_messages") or []) if str(item or "").strip()]
        reply_len = len(re.sub(r"\s+", "", reply_text))
        style_text = f"{style.get('title', '')} {style.get('content', '')}".strip()

        conciseness = 96
        if reply_len <= 8:
            conciseness = 70
        elif reply_len <= 16:
            conciseness = 90
        elif reply_len <= 50:
            conciseness = 96
        elif reply_len <= 80:
            conciseness = 82
        else:
            conciseness = 62

        low_barrier = 72
        if any(token in reply_text for token in ["还是", "有/没有", "有或没有", "有的话", "没有的话"]):
            low_barrier += 12
        if any(token in reply_text for token in ["吗", "呢", "可否", "方便", "是否", "?","？"]):
            low_barrier += 10
        if any(token in reply_text for token in ["回我", "回个", "确认下", "简单说", "短答"]):
            low_barrier += 6
        low_barrier = cls._clamp_score(low_barrier)

        max_overlap = 0.0
        for old_message in recent_sales_messages[:3] or ([latest_sales_message] if latest_sales_message else []):
            max_overlap = max(max_overlap, cls._text_overlap_ratio(reply_text, old_message))
        non_repetition = cls._clamp_score(100 - max_overlap * 90)

        safety = 94
        safety -= len(validation.get("warnings") or []) * 6
        safety -= len(validation.get("blocking_issues") or []) * 18
        if validation.get("manual_review_required"):
            safety -= 10
        safety = cls._clamp_score(safety)

        style_match = 82
        if "商务" in style_text or "正式" in style_text or "稳重" in style_text:
            if any(token in reply_text for token in ["您好", "请问", "请教", "确认", "是否", "方便"]):
                style_match += 10
            if any(token in reply_text for token in ["哈", "啦", "呐"]):
                style_match -= 8
        elif "亲和" in style_text or "自然" in style_text or "微信" in style_text:
            if any(token in reply_text for token in ["最近", "忙吗", "辛苦", "回我", "就行"]):
                style_match += 10
            if reply_len > 48:
                style_match -= 8
        style_match = cls._clamp_score(style_match)

        context_alignment = 80
        focus_text = " ".join([
            str((summary_json or {}).get("topic") or ""),
            str((summary_json or {}).get("core_demand") or ""),
            str(merged_facts.get("latest_customer_message") or ""),
        ])
        keyword_hits = 0
        for token in ["负责", "项目", "翻译", "报价", "资料", "对接", "确认", "推进"]:
            if token in focus_text and token in reply_text:
                keyword_hits += 1
        context_alignment = cls._clamp_score(context_alignment + keyword_hits * 4)

        overall = cls._clamp_score(
            conciseness * 0.18
            + low_barrier * 0.24
            + non_repetition * 0.22
            + safety * 0.22
            + style_match * 0.08
            + context_alignment * 0.06
        )
        return {
            "conciseness": conciseness,
            "low_barrier": low_barrier,
            "non_repetition": non_repetition,
            "safety": safety,
            "style_match": style_match,
            "context_alignment": context_alignment,
            "overall": overall,
        }

    @classmethod
    def score_reply_candidates(
        cls,
        *,
        summary_json: dict | None,
        knowledge_payload,
        crm_context: dict | None = None,
        candidates: list[dict] | None = None,
        actual_sales_replies: list[dict] | None = None,
    ) -> dict:
        thread_fact = knowledge_payload.get("thread_business_fact") if isinstance(knowledge_payload, dict) else None
        ai_candidates: list[dict] = []
        heuristic_by_ai_id: dict[str, dict] = {}
        for item in candidates or []:
            if item.get("status") != "done" or not item.get("content"):
                continue
            validation = item.get("validation") or cls.validate_sales_assist_output(item.get("content"), knowledge_payload, crm_context=crm_context)
            reply_text = cls.extract_reply_reference_text(item.get("content"))
            heuristic_scores = cls._reply_dimension_scores(
                reply_text=reply_text,
                validation=validation,
                summary_json=summary_json,
                thread_fact=thread_fact,
                style=item.get("reply_style"),
            )
            entry = {
                "candidate_id": item.get("candidate_id"),
                "model_slot": item.get("model_slot"),
                "model_display_name": item.get("model_display_name"),
                "style_id": item.get("style_id"),
                "style_title": item.get("style_title"),
                "reply_text": reply_text,
                "overall_score": heuristic_scores["overall"],
                "scores": heuristic_scores,
                "validation_status": validation.get("status"),
                "manual_review_required": bool(validation.get("manual_review_required")),
                "score_reason": "heuristic_fallback",
            }
            ai_candidates.append(entry)
            if entry["candidate_id"]:
                heuristic_by_ai_id[entry["candidate_id"]] = entry

        sales_scores: list[dict] = []
        heuristic_by_sales_id: dict[str, dict] = {}
        for item in actual_sales_replies or []:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            validation = cls.validate_sales_assist_output(content, knowledge_payload, crm_context=crm_context)
            heuristic_scores = cls._reply_dimension_scores(
                reply_text=content,
                validation=validation,
                summary_json=summary_json,
                thread_fact=thread_fact,
                style=None,
            )
            entry = {
                "reply_id": item.get("id"),
                "time": item.get("time"),
                "content": content,
                "overall_score": heuristic_scores["overall"],
                "scores": heuristic_scores,
                "validation_status": validation.get("status"),
                "manual_review_required": bool(validation.get("manual_review_required")),
                "score_reason": "heuristic_fallback",
            }
            sales_scores.append(entry)
            heuristic_by_sales_id[str(item.get("id"))] = entry

        evaluation_payload = {
            "summary": {
                "topic": (summary_json or {}).get("topic"),
                "core_demand": (summary_json or {}).get("core_demand"),
                "status": (summary_json or {}).get("status"),
            },
            "thread_context": cls.sanitize_thread_fact_for_prompt(thread_fact),
            "crm_context": cls.sanitize_crm_context_for_prompt(crm_context),
            "candidates": [
                {
                    "candidate_id": item.get("candidate_id"),
                    "model_slot": item.get("model_slot"),
                    "model_display_name": item.get("model_display_name"),
                    "style_title": item.get("style_title"),
                    "reply_text": item.get("reply_text"),
                }
                for item in ai_candidates
            ],
            "actual_sales_replies": [
                {
                    "reply_id": item.get("reply_id"),
                    "time": item.get("time"),
                    "content": item.get("content"),
                }
                for item in sales_scores
            ],
            "dimensions": [
                "overall",
                "low_barrier",
                "non_repetition",
                "safety",
                "conciseness",
                "style_match",
                "context_alignment",
            ],
        }
        if ai_candidates or sales_scores:
            score_prompt = (
                "你是销售回复评分器。请使用当前 LLM-1 模型，对下列候选回复和销售实发回复分别打分。\n"
                "评分维度：overall, low_barrier, non_repetition, safety, conciseness, style_match, context_alignment。\n"
                "每个维度取 0-100 的整数。评分要结合线程历史、最近我方已发内容、客户最后状态、风格要求和 CRM 风险。\n"
                "请只返回 JSON 对象，不要输出 markdown。\n"
                "JSON 结构：\n"
                "{\n"
                "  \"ai_candidates\": [{\"candidate_id\": \"...\", \"scores\": {...}, \"reason\": \"一句话原因\"}],\n"
                "  \"actual_sales_replies\": [{\"reply_id\": \"...\", \"scores\": {...}, \"reason\": \"一句话原因\"}]\n"
                "}\n\n"
                f"评分输入：{json.dumps(evaluation_payload, ensure_ascii=False)}"
            )
            try:
                llm_scores = cls.run_llm1_json_prompt(score_prompt, user_id="reply_score")
                for item in llm_scores.get("ai_candidates") or []:
                    candidate_id = str(item.get("candidate_id") or "").strip()
                    target = heuristic_by_ai_id.get(candidate_id)
                    if not target:
                        continue
                    score_block = item.get("scores") or {}
                    normalized = {}
                    for key in ["overall", "low_barrier", "non_repetition", "safety", "conciseness", "style_match", "context_alignment"]:
                        base_value = score_block.get(key, target["scores"].get(key))
                        normalized[key] = cls._clamp_score(float(base_value))
                    target["scores"] = normalized
                    target["overall_score"] = normalized["overall"]
                    target["score_reason"] = str(item.get("reason") or "llm1_scored").strip()
                for item in llm_scores.get("actual_sales_replies") or []:
                    reply_id = str(item.get("reply_id") or "").strip()
                    target = heuristic_by_sales_id.get(reply_id)
                    if not target:
                        continue
                    score_block = item.get("scores") or {}
                    normalized = {}
                    for key in ["overall", "low_barrier", "non_repetition", "safety", "conciseness", "style_match", "context_alignment"]:
                        base_value = score_block.get(key, target["scores"].get(key))
                        normalized[key] = cls._clamp_score(float(base_value))
                    target["scores"] = normalized
                    target["overall_score"] = normalized["overall"]
                    target["score_reason"] = str(item.get("reason") or "llm1_scored").strip()
            except Exception as exc:
                logger.error("LLM-1 评分失败，回退启发式评分: %s", exc)

        ai_candidates.sort(key=lambda item: item.get("overall_score", 0), reverse=True)
        sales_scores.sort(key=lambda item: item.get("overall_score", 0), reverse=True)

        return {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "scored_by": {
                "model": settings.LLM1_MODEL,
                "provider": cls._llm_provider_label(settings.LLM1_API_KEY),
                "score_mode": "llm1_with_heuristic_fallback",
            },
            "dimensions": [
                {"key": "overall", "label": "总分"},
                {"key": "low_barrier", "label": "易回复"},
                {"key": "non_repetition", "label": "差异化"},
                {"key": "safety", "label": "稳妥度"},
                {"key": "conciseness", "label": "微信感"},
                {"key": "style_match", "label": "风格匹配"},
                {"key": "context_alignment", "label": "上下文贴合"},
            ],
            "ai_candidates": ai_candidates,
            "actual_sales_replies": sales_scores,
            "best_ai_candidate_id": ai_candidates[0]["candidate_id"] if ai_candidates else None,
        }

    @staticmethod
    def update_knowledge_hit_log_outcome(log_id: str | None, final_response: str | None = None, manual_feedback: dict | None = None, feedback_status: str | None = None):
        if not log_id:
            return
        db = SessionLocal()
        try:
            log = db.query(KnowledgeHitLog).filter(KnowledgeHitLog.log_id == log_id).first()
            if not log:
                return
            if final_response is not None:
                log.final_response = final_response
            if manual_feedback is not None:
                log.manual_feedback = manual_feedback
            if feedback_status is not None:
                log.feedback_status = feedback_status
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("知识命中日志结果更新失败: %s", e)
        finally:
            db.close()

    @classmethod
    def get_crm_context(cls, external_userid: str, strict: bool = False) -> dict:
        """从 CRM 数据库拉取最新商机、合同、跟进和生命周期信息"""
        empty_profile = {
            "crm_external_userid": external_userid or None,
            "crm_contact_name": None,
            "company_name": None,
            "company_industry": None,
            "recent_opportunities": None,
            "recent_quote_summary": None,
            "ongoing_contracts": None,
            "contact_recent_followup": None,
            "customer_lifecycle_stage": None,
            "customer_tier": None,
            "payment_risk_level": None,
            "high_risk_flags": [],
            "crm_profile_status": "empty"
        }

        if not external_userid:
            if strict:
                raise RuntimeError("CRM 查询失败: external_userid 为空")
            empty_profile["crm_profile_error"] = "external_userid 为空"
            return empty_profile

        try:
            from crm_database import CRMSessionLocal
            from crm_profile import fetch_crm_profile

            db = CRMSessionLocal()
            try:
                profile_model = fetch_crm_profile(external_userid, db)
            finally:
                db.close()

            data = profile_model.model_dump()
            return {
                "crm_external_userid": data.get("crm_external_userid") or external_userid,
                "crm_contact_name": data.get("crm_contact_name"),
                "company_name": data.get("company_name"),
                "company_industry": data.get("company_industry"),
                "recent_opportunities": data.get("recent_opportunities"),
                "recent_quote_summary": data.get("recent_quote_summary"),
                "ongoing_contracts": data.get("ongoing_contracts"),
                "contact_recent_followup": data.get("contact_recent_followup"),
                "customer_lifecycle_stage": data.get("customer_lifecycle_stage"),
                "customer_tier": data.get("customer_tier"),
                "payment_risk_level": data.get("payment_risk_level"),
                "high_risk_flags": data.get("high_risk_flags") or [],
                "crm_profile_status": "success"
            }

        except HTTPException as e:
            if strict:
                raise RuntimeError(f"CRM 客户画像查询失败: {e.detail}") from e
            if e.status_code == 404:
                empty_profile["crm_profile_status"] = "not_found"
                empty_profile["crm_profile_error"] = e.detail
                logger.info(f"CRM 客户画像未找到: {e.detail}")
            else:
                empty_profile["crm_profile_status"] = "error"
                empty_profile["crm_profile_error"] = e.detail
                logger.error(f"CRM 客户画像查询异常: {e.detail}")
        except Exception as e:
            if strict:
                raise RuntimeError(f"CRM 数据库查询失败: {e}") from e
            empty_profile["crm_profile_status"] = "error"
            empty_profile["crm_profile_error"] = f"CRM 数据库查询失败: {e}"
            logger.error(empty_profile["crm_profile_error"])

        return empty_profile

    @classmethod
    def generate_sales_assist(cls, summary_json: dict, knowledge_list, crm_context: dict = None):
        bundle = cls.generate_sales_assist_bundle(summary_json, knowledge_list, crm_context)
        return bundle.get("content")

    @classmethod
    def generate_sales_assist_bundle(
        cls,
        summary_json: dict,
        knowledge_list,
        crm_context: dict = None,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        label: str = "LLM2",
        prepared_request: dict | None = None,
    ):
        """调用 LLM-2 生成销售辅助建议"""
        request_spec = prepared_request or cls.build_sales_assist_request(
            summary_json,
            knowledge_list,
            crm_context,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            label=label,
        )
        final_prompt = request_spec.get("final_prompt") or ""
        api_url = request_spec.get("api_url") or ""
        api_key = request_spec.get("api_key") or ""
        model = request_spec.get("model") or ""
        timeout_seconds = request_spec.get("timeout_seconds") or settings.LLM2_TIMEOUT_SECONDS
        prompt_trace = dict(request_spec.get("prompt_trace") or {})
        prompt_trace.setdefault("status", "ready")
        prompt_trace.setdefault("sent_to_ai", True)
        retry_forbidden = bool(request_spec.get("retry_forbidden"))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            logger.info("正在调用 %s 生成回复建议...", label)
            prompt_trace["request_started_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            if api_key.startswith("app-"):
                url = api_url.rstrip("/") + "/chat-messages"
                payload = {
                    "inputs": {},
                    "query": final_prompt,
                    "response_mode": "blocking",
                    "user": f"sales_assist_{label.lower()}",
                }
                cls._log_llm_prompt(f"{label}_DIFY", model, url, final_prompt)
                response = cls._post_json(url, headers=headers, timeout=timeout_seconds, payload=payload)
                if response.status_code == 404:
                    url = api_url.rstrip("/") + "/completion-messages"
                    cls._log_llm_prompt(f"{label}_DIFY_COMPLETION", model, url, final_prompt)
                    response = cls._post_json(url, headers=headers, timeout=timeout_seconds, payload=payload)
                prompt_trace["response_status_code"] = response.status_code
                prompt_trace["response_received_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                if response.status_code != 200:
                    raise RuntimeError(f"Dify 接口错误: HTTP {response.status_code}")
                raw_content = response.json().get("answer", "")
                if raw_content:
                    validation = cls.validate_sales_assist_output(raw_content, knowledge_list, crm_context=crm_context)
                    if cls._needs_followup_rewrite_retry(validation):
                        if not retry_forbidden:
                            retry_request = dict(request_spec)
                            retry_request["retry_forbidden"] = True
                            retry_request["final_prompt"] = (
                                f"{final_prompt}\n\n"
                                "【纠偏重写】上一版仍然重复了我方刚发过的话。请完全重写，只保留同一业务目标，"
                                "不要再次自我介绍，不要再问是否负责，不要再提合作记录；"
                                "请改成更低门槛的一句话跟进，最好是短确认或二选一。"
                            )
                            return cls.generate_sales_assist_bundle(
                                summary_json,
                                knowledge_list,
                                crm_context,
                                prepared_request=retry_request,
                            )
                        guarded_content = cls.build_followup_guard_response(summary_json)
                        guarded_validation = cls.validate_sales_assist_output(guarded_content, knowledge_list, crm_context=crm_context)
                        prompt_trace["result"] = "success_guarded"
                        prompt_trace["post_validation_status"] = guarded_validation.get("status") or "ok"
                        prompt_trace["post_validation_manual_review_required"] = bool(guarded_validation.get("manual_review_required"))
                        prompt_trace["post_validation_reason"] = "followup_repetition_guard"
                        return {
                            "content": guarded_content,
                            "raw_content": raw_content,
                            "validation": guarded_validation,
                            "evidence_refs": guarded_validation.get("evidence_refs") or [],
                            "prompt_trace": prompt_trace,
                        }
                    prompt_trace["result"] = "success"
                    prompt_trace["post_validation_status"] = validation.get("status") or "ok"
                    prompt_trace["post_validation_manual_review_required"] = bool(validation.get("manual_review_required"))
                    prompt_trace["post_validation_reason"] = "；".join(validation.get("blocking_issues") or validation.get("warnings") or []) or ""
                    return {
                        "content": raw_content,
                        "raw_content": raw_content,
                        "validation": validation,
                        "evidence_refs": validation.get("evidence_refs") or [],
                        "prompt_trace": prompt_trace,
                    }
                raise RuntimeError("Dify 返回缺少 answer 字段")

            url = api_url.rstrip("/") + "/chat/completions"
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": final_prompt}
                ],
                "temperature": 0.7
            }
            cls._log_llm_prompt(f"{label}_OPENAI", model, url, final_prompt)
            response = cls._post_json(url, headers=headers, timeout=timeout_seconds, payload=payload)
            prompt_trace["response_status_code"] = response.status_code
            prompt_trace["response_received_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI 协议接口错误: HTTP {response.status_code}")
            res_data = response.json()
            raw_content = res_data["choices"][0]["message"]["content"] if "choices" in res_data else ""
            if raw_content:
                validation = cls.validate_sales_assist_output(raw_content, knowledge_list, crm_context=crm_context)
                if cls._needs_followup_rewrite_retry(validation):
                    if not retry_forbidden:
                        retry_request = dict(request_spec)
                        retry_request["retry_forbidden"] = True
                        retry_request["final_prompt"] = (
                            f"{final_prompt}\n\n"
                            "【纠偏重写】上一版仍然重复了我方刚发过的话。请完全重写，只保留同一业务目标，"
                            "不要再次自我介绍，不要再问是否负责，不要再提合作记录；"
                            "请改成更低门槛的一句话跟进，最好是短确认或二选一。"
                        )
                        return cls.generate_sales_assist_bundle(
                            summary_json,
                            knowledge_list,
                            crm_context,
                            prepared_request=retry_request,
                        )
                    guarded_content = cls.build_followup_guard_response(summary_json)
                    guarded_validation = cls.validate_sales_assist_output(guarded_content, knowledge_list, crm_context=crm_context)
                    prompt_trace["result"] = "success_guarded"
                    prompt_trace["post_validation_status"] = guarded_validation.get("status") or "ok"
                    prompt_trace["post_validation_manual_review_required"] = bool(guarded_validation.get("manual_review_required"))
                    prompt_trace["post_validation_reason"] = "followup_repetition_guard"
                    return {
                        "content": guarded_content,
                        "raw_content": raw_content,
                        "validation": guarded_validation,
                        "evidence_refs": guarded_validation.get("evidence_refs") or [],
                        "prompt_trace": prompt_trace,
                    }
                prompt_trace["result"] = "success"
                prompt_trace["post_validation_status"] = validation.get("status") or "ok"
                prompt_trace["post_validation_manual_review_required"] = bool(validation.get("manual_review_required"))
                prompt_trace["post_validation_reason"] = "；".join(validation.get("blocking_issues") or validation.get("warnings") or []) or ""
                return {
                    "content": raw_content,
                    "raw_content": raw_content,
                    "validation": validation,
                    "evidence_refs": validation.get("evidence_refs") or [],
                    "prompt_trace": prompt_trace,
                }
        except Exception as e:
            prompt_trace["result"] = "error"
            logger.error(f"LLM-2 调用异常: {e}")
            raise RuntimeError(f"LLM-2 调用异常: {e}") from e
        raise RuntimeError("LLM-2 返回缺少有效内容")

    @classmethod
    def slow_track_analyze(cls, user_id: str, context: List[dict]):
        """独立阶段一：异步全量分析链路 (仅 LLM-1 提取写入库)"""
        # 1. 结构化提取 (LLM-1)
        summary = cls._run_llm1(user_id, context)
        if not summary:
            raise RuntimeError("LLM-1 未返回有效结构化摘要")
        
        # 2. 存回数据库存证
        db = SessionLocal()
        try:
            def _safe_str(val, max_len=None):
                if not val:
                    return "未明确"
                if isinstance(val, (dict, list)):
                    import json
                    text_val = json.dumps(val, ensure_ascii=False)
                else:
                    text_val = str(val)
                return text_val[:max_len] if max_len else text_val

            summary_record = IntentSummary(
                user_id=user_id,
                topic=_safe_str(summary.get("topic"), 200),
                core_demand=_safe_str(summary.get("core_demand")),
                key_facts=summary.get("key_facts", {}),
                todo_items=summary.get("todo_items", []),
                risks=_safe_str(summary.get("risks")),
                to_be_confirmed=_safe_str(summary.get("to_be_confirmed")),
                status=_safe_str(summary.get("status"), 50),
            )
            db.add(summary_record)
            db.commit()
            
        except Exception as e:
            logger.error(f"分析摘要入库失败: {e}")
        finally:
            db.close()
        
        return summary

    @classmethod
    def _run_llm1(cls, user_id, context):
        """内部 LLM-1 调用实现逻辑 (剥离原 slow_track_analyze 内容)"""
        request_spec = cls.build_llm1_request(context, user_id=user_id, label="LLM1")
        bundle = cls.run_llm1_request(request_spec)
        return bundle.get("summary")
