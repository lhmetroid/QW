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
                ensure_ascii=False,
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
                        source_tags,
                        chunk,
                    ))

            scored.sort(key=lambda item: (item[0], -item[1], -item[2], -item[4], -item[5]))
            hits = []
            score_by_chunk_id: dict[str, dict[str, Any]] = {}
            for _bucket, final_score, semantic_score, keyword_score, exact_phrase_score, intent_score, metadata_score, bm25_score, quality_score, effect_score, generation_score, source_tags, chunk in scored:
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
                }
            for _bucket, final_score, semantic_score, keyword_score, exact_phrase_score, intent_score, metadata_score, bm25_score, quality_score, effect_score, generation_score, source_tags, chunk in scored[:top_k]:
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
            elif confidence_score < auto_ok_score:
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
    def infer_query_features(summary_json: Dict[str, Any], crm_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """从 V1 摘要生成知识库 V2 检索过滤字段；宁可少过滤，不误伤候选。"""
        text = json.dumps(summary_json or {}, ensure_ascii=False)
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

        return features

    @staticmethod
    def format_knowledge_context(knowledge_payload) -> str:
        """把 V2 证据包按规则/FAQ/案例三段格式化，兼容旧 list[str]。"""
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
                f"  分数: {hit.get('score')}",
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
        if knowledge_payload.get("related_chunks"):
            rendered.append("[同文档关联资料]")
            rendered.append("- 已检索到同文档关联切片，但未注入自动回复证据；仅供人工展开核对。")
        if knowledge_payload.get("human_only_hits"):
            rendered.append("[仅人工参考证据]")
            rendered.append(f"- 已命中 {len(knowledge_payload.get('human_only_hits') or [])} 条人工参考证据，不直接注入自动回复。")
        if knowledge_payload.get("thread_business_fact"):
            fact = knowledge_payload.get("thread_business_fact") or {}
            rendered.append("[线程业务事实]")
            rendered.append(
                f"- 当前线程状态: {fact.get('business_state') or 'unknown'} / 场景: {fact.get('scenario_label') or 'general'} / 意图: {fact.get('intent_label') or 'general'}"
            )
            if fact.get("reply_guard_reason"):
                rendered.append(f"- 门禁提示: {fact.get('reply_guard_reason')}")
        if knowledge_payload.get("manual_review_required"):
            rendered.append("[低命中保护]")
            rendered.append(f"- 当前状态: {knowledge_payload.get('status')}")
            rendered.append(f"- 原因: {knowledge_payload.get('no_hit_reason') or '命中证据需要人工确认'}")
            rendered.append("- 要求: 涉及报价、承诺、能力或流程时必须保守回复；证据不足时先请客户补充资料类型、语种、用途、交付要求，并提示人工确认，不得编造。")
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
    ):
        """调用 LLM-2 生成销售辅助建议"""
        if isinstance(knowledge_list, dict):
            retrieval_status = str(knowledge_list.get("status") or "").strip()
            retrieval_manual_review = bool(knowledge_list.get("manual_review_required"))
            if retrieval_status in {"manual_review_required", "low_confidence", "ambiguous_query", "no_applicable_knowledge"} or retrieval_manual_review:
                blocking_issues = []
                no_hit_reason = str(knowledge_list.get("no_hit_reason") or "").strip()
                if no_hit_reason:
                    blocking_issues.append(no_hit_reason)
                blocking_issues.append(f"知识检索状态为 {retrieval_status or 'manual_review_required'}，未达到自动回复标准。")
                validation = {
                    "status": "manual_review_required",
                    "manual_review_required": True,
                    "warnings": ["知识检索未达到自动回复标准，已跳过 LLM-2 证据注入并直接输出保守回复。"],
                    "blocking_issues": blocking_issues,
                    "evidence_refs": cls.build_evidence_refs(knowledge_list),
                }
                return {
                    "content": cls.build_safe_assist_response(summary_json, validation),
                    "raw_content": "",
                    "validation": validation,
                    "evidence_refs": validation.get("evidence_refs") or [],
                }

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
        crm_str = json.dumps(crm_context or {}, ensure_ascii=False)
        
        final_prompt = prompt2
        if "{{summary_json}}" in final_prompt or "{{knowledge_context}}" in final_prompt or "{{crm_context_json}}" in final_prompt:
            final_prompt = final_prompt.replace("{{summary_json}}", summary_str)
            final_prompt = final_prompt.replace("{{knowledge_context}}", knowledge_context or '无相关参考')
            final_prompt = final_prompt.replace("{{crm_context_json}}", crm_str)
        else:
            final_prompt = f"{prompt2}\n\n会话摘要档案：{summary_str}\n\n内部 CRM 客户标签：{crm_str}\n\n参考知识库匹配：\n{knowledge_context or '无相关参考'}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            logger.info("正在调用 %s 生成回复建议...", label)
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
                if response.status_code != 200:
                    raise RuntimeError(f"Dify 接口错误: HTTP {response.status_code}")
                raw_content = response.json().get("answer", "")
                if raw_content:
                    validation = cls.validate_sales_assist_output(raw_content, knowledge_list, crm_context=crm_context)
                    if validation.get("blocking_issues") or validation.get("manual_review_required"):
                        content = cls.build_safe_assist_response(summary_json, validation)
                    else:
                        content = raw_content
                    return {
                        "content": content,
                        "raw_content": raw_content,
                        "validation": validation,
                        "evidence_refs": validation.get("evidence_refs") or [],
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
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI 协议接口错误: HTTP {response.status_code}")
            res_data = response.json()
            raw_content = res_data["choices"][0]["message"]["content"] if "choices" in res_data else ""
            if raw_content:
                validation = cls.validate_sales_assist_output(raw_content, knowledge_list, crm_context=crm_context)
                if validation.get("blocking_issues") or validation.get("manual_review_required"):
                    content = cls.build_safe_assist_response(summary_json, validation)
                else:
                    content = raw_content
                return {
                    "content": content,
                    "raw_content": raw_content,
                    "validation": validation,
                    "evidence_refs": validation.get("evidence_refs") or [],
                }
        except Exception as e:
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
                status=_safe_str(summary.get("status"), 50)
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
        conversation_text = ""
        for msg in context:
            speaker = "客户" if msg["sender_type"] == "customer" else "销售"
            conversation_text += f"[{speaker}]: {msg['content']}\n"

        headers = {
            "Authorization": f"Bearer {settings.LLM1_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt1 = cls.get_prompt1()
        if "{{conversation_text}}" in prompt1:
            full_prompt = prompt1.replace("{{conversation_text}}", conversation_text)
        else:
            full_prompt = f"{prompt1}\n\n请分析以下企微真实对话记录：\n{conversation_text}"
        
        try:
            # Dify API 兼容判定
            if settings.LLM1_API_KEY.startswith("app-"):
                url = settings.LLM1_API_URL.rstrip('/') + "/chat-messages"
                payload = {
                    "inputs": {},
                    "query": full_prompt,
                    "response_mode": "blocking",
                    "user": user_id
                }
                cls._log_llm_prompt("LLM1_DIFY", settings.LLM1_MODEL, url, full_prompt)
                response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                
                # 兼容 Dify 文本生成应用 (如果不幸是 Workflow/Text Generator类型)
                if response.status_code == 404:
                    url = settings.LLM1_API_URL.rstrip('/') + "/completion-messages"
                    cls._log_llm_prompt("LLM1_DIFY_COMPLETION", settings.LLM1_MODEL, url, full_prompt)
                    response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                    
                if response.status_code != 200:
                    raise RuntimeError(f"Dify 接口错误: HTTP {response.status_code}")
                    
                res_data = response.json()
                raw_text = res_data.get("answer", "")
            else:
                # 兼容标准 OpenAI 协议
                url = settings.LLM1_API_URL.rstrip('/') + "/chat/completions"
                payload = {
                    "model": settings.LLM1_MODEL,
                    "messages": [
                        {"role": "user", "content": full_prompt}
                    ],
                    "temperature": 0.1
                }
                cls._log_llm_prompt("LLM1_OPENAI", settings.LLM1_MODEL, url, full_prompt)
                response = cls._post_json(url, headers, payload, settings.LLM1_TIMEOUT_SECONDS)
                if response.status_code != 200:
                    raise RuntimeError(f"OpenAI 协议接口错误: HTTP {response.status_code}")
                
                try:
                    res_data = response.json()
                except Exception:
                    raise RuntimeError("LLM 接口返回了无法解析的错误报文")
                    
                raw_text = res_data["choices"][0]["message"]["content"] if "choices" in res_data else ""
            
            # 强化 JSON 解析保护，防止 LLM 返回时带有 Markdown block (比如 ```json ...)
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            return json.loads(raw_text.strip())
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM-1 最终提取的 JSON 无法解析: {e}\n原文: {raw_text[:200]}")
            raise RuntimeError(f"LLM-1 最终提取的 JSON 无法解析: {e}") from e
        except Exception as e:
            logger.error(f"LLM-1 调用彻底失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
