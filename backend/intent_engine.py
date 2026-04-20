import re
import logging
from typing import Optional, List, Dict, Any
import requests
import json
from datetime import datetime
from time import perf_counter
from fastapi import HTTPException
from sqlalchemy import or_
from config import settings
from qywx_utils import QYWXUtils
from database import SessionLocal, KnowledgeBase, IntentSummary, KnowledgeChunk, KnowledgeHitLog, PricingRule
from embedding_service import EmbeddingService
from logging_config import sanitize_text

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
            return {}

    @classmethod
    def get_rules(cls):
        rules = cls.get_ai_settings().get("FAST_TRACK_RULES", [])
        return rules if rules else [
            {"id": 1, "name": "防挂底库", "pattern": r"(地址|电话)"}
        ]

    @classmethod
    def get_prompt1(cls):
        return cls.get_ai_settings().get("SYSTEM_PROMPT_LLM1", "提取客户核心诉求。")

    @classmethod
    def get_prompt2(cls):
        return cls.get_ai_settings().get("SYSTEM_PROMPT_LLM2", "极简输出。")

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
                    logger.error("知识库 LLM 辅助 Dify 调用失败: HTTP %s", response.status_code)
                    return None
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
                    logger.error("知识库 LLM 辅助 OpenAI-compatible 调用失败: HTTP %s", response.status_code)
                    return None
                data = response.json()
                raw_text = data["choices"][0]["message"]["content"] if "choices" in data else ""
            return json.loads(cls._strip_json_fences(raw_text))
        except json.JSONDecodeError as e:
            logger.error("知识库 LLM 辅助返回 JSON 解析失败: %s", e)
            return None
        except Exception as e:
            logger.error("知识库 LLM 辅助调用异常: %s", e)
            return None

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
                return []

            vector = cls.get_embedding(query_text)
            if not vector:
                return []
                
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
            return []
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
        for token in re.split(r"[\s,，。；;、/？?！!：:]+", query):
            token = token.strip()
            if len(token) >= 2 and token in haystack:
                score += 1.0
        for field in [chunk.title, chunk.language_pair, chunk.service_scope]:
            value = (field or "").lower()
            if value and value in query:
                score += 1.0
        return min(score / 5.0, 1.0)

    @staticmethod
    def _query_terms(query_text: str) -> List[str]:
        terms = []
        for token in re.split(r"[\s,，。；;、/？?！!：:（）()《》\"']+", query_text or ""):
            token = token.strip().lower()
            if len(token) >= 2 and token not in terms:
                terms.append(token)
        return terms[:8]

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
            "knowledge_type": features.get("knowledge_type"),
            "language_pair": features.get("language_pair"),
            "service_scope": features.get("service_scope"),
            "customer_tier": features.get("customer_tier"),
            "effective_time": "now",
            "candidate_limit": settings.KB_CANDIDATE_LIMIT,
            "keyword_prefilter_enabled": settings.KB_KEYWORD_PREFILTER_ENABLED,
        }

        vector = cls.get_embedding(query_text)
        db = SessionLocal()
        try:
            now = datetime.utcnow()
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
            candidate_source = "structured_filters"
            candidate_query = query
            query_terms = cls._query_terms(query_text)
            if settings.KB_KEYWORD_PREFILTER_ENABLED and query_terms:
                keyword_conditions = []
                for term in query_terms:
                    like_term = f"%{term}%"
                    keyword_conditions.extend([
                        KnowledgeChunk.title.ilike(like_term),
                        KnowledgeChunk.keyword_text.ilike(like_term),
                        KnowledgeChunk.content.ilike(like_term),
                    ])
                keyword_query = query.filter(or_(*keyword_conditions))
                keyword_candidates = keyword_query.order_by(KnowledgeChunk.priority.desc()).limit(candidate_limit).all()
                if keyword_candidates:
                    candidates = keyword_candidates
                    candidate_source = "keyword_prefilter"
                else:
                    candidates = query.order_by(KnowledgeChunk.priority.desc()).limit(candidate_limit).all()
                    candidate_source = "structured_filters_fallback"
            else:
                candidates = candidate_query.order_by(KnowledgeChunk.priority.desc()).limit(candidate_limit).all()
            filters_used["candidate_source"] = candidate_source
            filters_used["candidate_count"] = len(candidates)
            scored = []
            for chunk in candidates:
                semantic_score = cls._cosine_sim(vector, chunk.embedding) if vector and chunk.embedding else 0.0
                keyword_score = cls._keyword_score(query_text, chunk)
                priority_score = min((chunk.priority or 50) / 100.0, 1.0)
                final_score = round((semantic_score * 0.75) + (keyword_score * 0.15) + (priority_score * 0.10), 6)
                if semantic_score > 0 or keyword_score > 0:
                    scored.append((final_score, semantic_score, keyword_score, chunk))

            scored.sort(key=lambda item: item[0], reverse=True)
            hits = []
            for final_score, semantic_score, keyword_score, chunk in scored[:top_k]:
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
                    "knowledge_type": chunk.knowledge_type,
                    "title": chunk.title,
                    "content": chunk.content,
                    "score": final_score,
                    "semantic_score": round(semantic_score, 6),
                    "keyword_score": round(keyword_score, 6),
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
                    "insufficient_info": pricing_rule_missing or constraint_applies,
                    "manual_review_required": pricing_rule_missing or constraint_applies,
                    "applicability": "constraint" if constraint_applies else "matched",
                })

            confidence_score = hits[0]["score"] if hits else 0.0
            min_score = float(features.get("min_score", 0.18) or 0.18)
            any_manual_review = any(hit.get("manual_review_required") for hit in hits)
            any_insufficient = any(hit.get("insufficient_info") for hit in hits)
            if not hits:
                status = "empty_or_unavailable"
                no_hit_reason = "未命中符合 active 状态、适用范围与有效期过滤条件的知识"
                retrieval_quality = "no_hit"
                insufficient_info = True
                manual_review_required = True
            elif confidence_score < min_score:
                status = "low_confidence"
                no_hit_reason = f"最高命中分 {confidence_score} 低于阈值 {min_score}"
                retrieval_quality = "low_confidence"
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
            }
            for hit in hits:
                if hit["knowledge_type"] == "pricing" or hit.get("pricing_rules"):
                    evidence_context["rules"].append(hit)
                elif hit["knowledge_type"] == "faq":
                    evidence_context["faqs"].append(hit)
                else:
                    evidence_context["cases"].append(hit)
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
                "evidence_context": evidence_context,
                "confidence_score": confidence_score,
                "retrieval_quality": retrieval_quality,
                "insufficient_info": insufficient_info,
                "manual_review_required": manual_review_required,
                "no_hit_reason": no_hit_reason,
                "latency_ms": latency_ms,
                "log_id": str(log.log_id),
            }
        except Exception as e:
            db.rollback()
            logger.error("知识库 V2 检索异常: %s", e)
            return {
                "status": "error",
                "query_text": query_text,
                "query_features": features,
                "filters_used": filters_used,
                "hits": [],
                "evidence_context": {"rules": [], "faqs": [], "cases": []},
                "confidence_score": 0.0,
                "retrieval_quality": "error",
                "insufficient_info": True,
                "manual_review_required": True,
                "no_hit_reason": str(e),
                "latency_ms": round((perf_counter() - started) * 1000),
            }
        finally:
            db.close()

    @staticmethod
    def infer_query_features(summary_json: Dict[str, Any]) -> Dict[str, Any]:
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
        if any(word in text for word in ["能做", "可做", "是否支持", "业务范围", "服务范围"]):
            knowledge_types.append("capability")
        if any(word in text for word in ["流程", "怎么", "如何", "步骤", "周期", "交付"]):
            knowledge_types.append("process")
        knowledge_types.append("faq")
        features["knowledge_type"] = list(dict.fromkeys(knowledge_types))

        language_patterns = [
            ("en->fr", ["英译法", "英文翻法文", "英语翻法语"]),
            ("en->zh", ["英译中", "英文翻中文", "英语翻中文"]),
            ("zh->en", ["中译英", "中文翻英文", "中文翻英语"]),
            ("en->ru", ["英译俄", "英文翻俄文", "英语翻俄语"]),
            ("ja->zh", ["日译中", "日文翻中文"]),
            ("ko->zh", ["韩译中", "韩文翻中文"]),
        ]
        for code, words in language_patterns:
            if any(word in text for word in words):
                features["language_pair"] = code
                break

        if any(word in text for word in ["法律", "合同", "法务"]):
            features["service_scope"] = "legal"
        elif any(word in text for word in ["医学", "医疗", "药品"]):
            features["service_scope"] = "medical"
        elif any(word in text for word in ["技术", "说明书", "工程"]):
            features["service_scope"] = "technical"
        elif any(word in text for word in ["认证", "盖章", "公证"]):
            features["service_scope"] = "certified"
        elif features.get("business_line") == "translation":
            features["service_scope"] = "general"

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
        ]
        rendered = []
        for title, hits in sections:
            rendered.append(title)
            rendered.append("\n".join(render_hit(hit) for hit in hits) if hits else "- 无")
        if knowledge_payload.get("manual_review_required"):
            rendered.append("[低命中保护]")
            rendered.append(f"- 当前状态: {knowledge_payload.get('status')}")
            rendered.append(f"- 原因: {knowledge_payload.get('no_hit_reason') or '命中证据需要人工确认'}")
            rendered.append("- 要求: 涉及报价、承诺或规则时必须提示人工确认，不得编造。")
        return "\n".join(rendered)

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
    def get_crm_context(cls, external_userid: str) -> dict:
        """从 CRM 数据库拉取最新商机、合同、跟进和生命周期信息"""
        empty_profile = {
            "crm_contact_name": None,
            "company_name": None,
            "recent_opportunities": None,
            "ongoing_contracts": None,
            "contact_recent_followup": None,
            "customer_lifecycle_stage": None,
            "crm_profile_status": "empty"
        }

        if not external_userid:
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
                "crm_contact_name": data.get("crm_contact_name"),
                "company_name": data.get("company_name"),
                "recent_opportunities": data.get("recent_opportunities"),
                "ongoing_contracts": data.get("ongoing_contracts"),
                "contact_recent_followup": data.get("contact_recent_followup"),
                "customer_lifecycle_stage": data.get("customer_lifecycle_stage"),
                "crm_profile_status": "success"
            }

        except HTTPException as e:
            if e.status_code == 404:
                empty_profile["crm_profile_status"] = "not_found"
                empty_profile["crm_profile_error"] = e.detail
                logger.info(f"CRM 客户画像未找到: {e.detail}")
            else:
                empty_profile["crm_profile_status"] = "error"
                empty_profile["crm_profile_error"] = e.detail
                logger.error(f"CRM 客户画像查询异常: {e.detail}")
        except Exception as e:
            empty_profile["crm_profile_status"] = "error"
            empty_profile["crm_profile_error"] = f"CRM 数据库查询失败: {e}"
            logger.error(empty_profile["crm_profile_error"])

        return empty_profile

    @classmethod
    def generate_sales_assist(cls, summary_json: dict, knowledge_list, crm_context: dict = None):
        """调用 LLM-2 生成销售辅助建议"""
        knowledge_context = cls.format_knowledge_context(knowledge_list)
        prompt2 = cls.get_prompt2()
        
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
            "Authorization": f"Bearer {settings.LLM2_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.LLM2_MODEL,
            "messages": [
                {"role": "user", "content": final_prompt}
            ],
            "temperature": 0.7
        }
        cls._log_llm_prompt("LLM2", settings.LLM2_MODEL, settings.LLM2_API_URL, final_prompt)

        try:
            logger.info("正在调用 LLM-2 生成回复建议...")
            response = cls._post_json(
                settings.LLM2_API_URL + "/chat/completions",
                headers=headers,
                timeout=settings.LLM2_TIMEOUT_SECONDS,
                payload=payload,
            )
            res_data = response.json()
            if "choices" in res_data:
                return res_data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM-2 调用异常: {e}")
        return None

    @classmethod
    def slow_track_analyze(cls, user_id: str, context: List[dict]):
        """独立阶段一：异步全量分析链路 (仅 LLM-1 提取写入库)"""
        # 1. 结构化提取 (LLM-1)
        summary = cls._run_llm1(user_id, context)
        if not summary:
            return None
        
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
                    logger.error(f"Dify 接口错误: HTTP {response.status_code} - 需检查 10.0.0.210 服务端点配置。(包含非JSON数据)")
                    return None
                    
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
                    logger.error(f"OpenAI 协议接口错误: HTTP {response.status_code} - URL无响应或报错。")
                    return None
                
                try:
                    res_data = response.json()
                except Exception:
                    logger.error(f"LLM 接口返回了无法解析的错误报文 (例如 HTML 面板)。")
                    return None
                    
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
        except Exception as e:
            logger.error(f"LLM-1 调用彻底失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        return None
