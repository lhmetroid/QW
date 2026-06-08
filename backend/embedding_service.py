import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, List, Optional

import requests
from requests import Response

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """统一封装知识库 embedding provider 调用。"""

    _SESSION_LOCK = threading.Lock()
    _SESSION_CACHE: dict[str, requests.Session] = {}
    _EMBED_LOCK = threading.Lock()
    _EMBED_CACHE: "OrderedDict[str, tuple[float, List[float]]]" = OrderedDict()
    _EMBED_CACHE_MAX = 256
    _EMBED_CACHE_TTL_SECONDS = 300

    @staticmethod
    def _cache_key(text: str) -> str:
        return "||".join(
            [
                EmbeddingService.provider_name(),
                settings.EMBEDDING_API_URL.rstrip("/"),
                settings.EMBEDDING_MODEL,
                str(settings.EMBEDDING_DIM),
                text,
            ]
        )

    @classmethod
    def _get_cached_embedding(cls, text: str) -> Optional[List[float]]:
        key = cls._cache_key(text)
        now = time.monotonic()
        with cls._EMBED_LOCK:
            cached = cls._EMBED_CACHE.get(key)
            if not cached:
                return None
            expires_at, vector = cached
            if expires_at <= now:
                cls._EMBED_CACHE.pop(key, None)
                return None
            cls._EMBED_CACHE.move_to_end(key)
            return list(vector)

    @classmethod
    def _set_cached_embedding(cls, text: str, vector: List[float]) -> None:
        key = cls._cache_key(text)
        expires_at = time.monotonic() + cls._EMBED_CACHE_TTL_SECONDS
        with cls._EMBED_LOCK:
            cls._EMBED_CACHE[key] = (expires_at, list(vector))
            cls._EMBED_CACHE.move_to_end(key)
            while len(cls._EMBED_CACHE) > cls._EMBED_CACHE_MAX:
                cls._EMBED_CACHE.popitem(last=False)

    @classmethod
    def _session_for(cls, provider: str) -> requests.Session:
        session_key = f"{provider}|trust_env={settings.HTTP_TRUST_ENV}"
        with cls._SESSION_LOCK:
            session = cls._SESSION_CACHE.get(session_key)
            if session is None:
                session = requests.Session()
                session.trust_env = settings.HTTP_TRUST_ENV
                cls._SESSION_CACHE[session_key] = session
            return session

    @staticmethod
    def provider_name() -> str:
        provider = (settings.EMBEDDING_PROVIDER or "").strip().lower().replace("-", "_")
        if provider == "ollama":
            return "ollama"
        if provider in {"dify", "dify_app"}:
            return "dify"
        return "openai_compatible"

    @staticmethod
    def healthcheck_probe() -> dict[str, Any]:
        provider = EmbeddingService.provider_name()
        headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"} if settings.EMBEDDING_API_KEY else {}
        if provider == "ollama":
            return {
                "provider": provider,
                "url": settings.EMBEDDING_API_URL.rstrip("/") + "/api/tags",
                "headers": {},
                "mode": "ollama_tags",
            }
        if provider == "dify":
            return {
                "provider": provider,
                "url": EmbeddingService._dify_base_url() + "/info",
                "headers": headers,
                "mode": "dify_info",
            }
        return {
            "provider": provider,
            "url": settings.EMBEDDING_API_URL.rstrip("/") + "/models",
            "headers": headers,
            "mode": "openai_models",
        }

    @staticmethod
    def embed(text: str) -> Optional[List[float]]:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Embedding text is empty")

        cached = EmbeddingService._get_cached_embedding(clean_text)
        if cached is not None:
            return cached

        provider = EmbeddingService.provider_name()
        if provider == "ollama":
            vector = EmbeddingService._embed_ollama(clean_text)
        elif provider == "dify":
            vector = EmbeddingService._embed_dify(clean_text)
        else:
            vector = EmbeddingService._embed_openai_compatible(clean_text)

        if vector:
            EmbeddingService._set_cached_embedding(clean_text, vector)
        return vector

    @staticmethod
    def _embed_ollama(text: str) -> Optional[List[float]]:
        base_url = settings.EMBEDDING_API_URL.rstrip("/")
        ollama_url = base_url + "/api/embeddings"
        openai_url = base_url + "/v1/embeddings"
        ollama_payload = {
            "model": settings.EMBEDDING_MODEL,
            "prompt": text,
        }
        openai_payload = {
            "model": settings.EMBEDDING_MODEL,
            "input": text,
        }
        try:
            session = EmbeddingService._session_for("ollama")
            errors = []
            response = session.post(
                openai_url,
                json=openai_payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            if response.ok:
                data = response.json() if response.content else {}
                embedding = (data.get("data") or [{}])[0].get("embedding")
                if embedding:
                    logger.info("EMBEDDING_OK protocol=openai_v1_embeddings model=%s dim=%s", settings.EMBEDDING_MODEL, len(embedding))
                    return EmbeddingService._normalize_embedding_vector(
                        embedding,
                        source_label="OpenAI-compatible embedding via Ollama",
                    )
                errors.append("openai_v1_embeddings:empty_embedding")
                logger.warning("Ollama /v1/embeddings 返回空向量，回退 /api/embeddings: model=%s", settings.EMBEDDING_MODEL)
            else:
                errors.append(f"openai_v1_embeddings:http_{response.status_code}:{EmbeddingService._summarize_error_response(response)}")

            response = session.post(
                ollama_url,
                json=ollama_payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
            embedding = data.get("embedding")
            logger.info("EMBEDDING_OK protocol=ollama_api_embeddings model=%s dim=%s", settings.EMBEDDING_MODEL, len(embedding or []))
            return EmbeddingService._normalize_embedding_vector(
                embedding,
                source_label="Ollama embedding",
            )
        except Exception as e:
            logger.error("Ollama embedding 调用失败: %s", e)
            raise RuntimeError(f"Ollama embedding 调用失败: {e}") from e

    @staticmethod
    def _embed_dify(text: str) -> Optional[List[float]]:
        if not settings.EMBEDDING_API_KEY:
            raise RuntimeError("Dify Embedding KEY 未配置")

        headers = {
            "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": {
                "text": text,
                "model": settings.EMBEDDING_MODEL,
            },
            "query": text,
            "response_mode": "blocking",
            "user": "knowledge_embedding",
        }
        try:
            session = EmbeddingService._session_for("dify")
            app_mode = EmbeddingService._dify_app_mode()
            preferred_paths = ["/chat-messages", "/completion-messages"] if app_mode == "chat" else ["/completion-messages", "/chat-messages"]
            response = None
            url = ""
            for path in preferred_paths:
                url = EmbeddingService._dify_base_url() + path
                response = session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
                )
                if response.status_code in {200, 400, 401, 403}:
                    break
            if response is None:
                raise RuntimeError("Dify embedding 未获得有效响应")
            EmbeddingService._raise_for_status_with_detail(response, url)
            try:
                return EmbeddingService._normalize_embedding_vector(
                    EmbeddingService._extract_dify_embedding(response.json()),
                    source_label="Dify embedding",
                )
            except RuntimeError:
                logger.warning("Dify app 已调用成功，但返回中不含 embedding/vector；将由上层决定是否降级为关键词检索。")
                return None
        except Exception as e:
            logger.error("Dify embedding 调用失败: %s", e)
            raise RuntimeError(f"Dify embedding 调用失败: {e}") from e

    @staticmethod
    def _embed_openai_compatible(text: str) -> Optional[List[float]]:
        base_url = settings.EMBEDDING_API_URL.rstrip("/")
        url = base_url + ("/embeddings" if base_url.endswith("/v1") else "/v1/embeddings")
        headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"} if settings.EMBEDDING_API_KEY else {}
        payload = {"model": settings.EMBEDDING_MODEL, "input": text}
        try:
            session = EmbeddingService._session_for("openai_compatible")
            response = session.post(
                url,
                headers=headers or None,
                json=payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("data", [{}])[0].get("embedding")
            logger.info("EMBEDDING_OK protocol=openai_compatible model=%s dim=%s", settings.EMBEDDING_MODEL, len(embedding or []))
            return EmbeddingService._normalize_embedding_vector(
                embedding,
                source_label="OpenAI-compatible embedding",
            )
        except Exception as e:
            logger.error("OpenAI-compatible embedding 调用失败: %s", e)
            raise RuntimeError(f"OpenAI-compatible embedding 调用失败: {e}") from e

    @staticmethod
    def _dify_base_url() -> str:
        base_url = settings.EMBEDDING_API_URL.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = base_url + "/v1"
        return base_url

    @staticmethod
    def _dify_app_info() -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"}
        session = EmbeddingService._session_for("dify")
        response = session.get(
            EmbeddingService._dify_base_url() + "/info",
            headers=headers,
            timeout=settings.KB_HEALTHCHECK_TIMEOUT_SECONDS,
        )
        EmbeddingService._raise_for_status_with_detail(response, EmbeddingService._dify_base_url() + "/info")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _dify_app_mode() -> str:
        try:
            return str(EmbeddingService._dify_app_info().get("mode") or "").strip().lower()
        except Exception:
            return ""

    @staticmethod
    def _raise_for_status_with_detail(response: Response, url: str) -> None:
        if response.ok:
            return
        detail = EmbeddingService._summarize_error_response(response)
        raise RuntimeError(f"HTTP {response.status_code} endpoint={url} detail={detail}")

    @staticmethod
    def _summarize_error_response(response: Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            code = str(payload.get("code") or "").strip()
            message = str(payload.get("message") or "").strip()
            pieces = []
            if code:
                pieces.append(f"code={code}")
            if message:
                pieces.append(f"message={message}")
            if pieces:
                return ", ".join(pieces)

        text = (response.text or "").strip()
        return text[:300] if text else "empty_response"

    @staticmethod
    def _extract_dify_embedding(payload: Any) -> Any:
        embedding = EmbeddingService._search_embedding_candidate(payload)
        if embedding is not None:
            return embedding

        if isinstance(payload, dict):
            answer = payload.get("answer")
            if isinstance(answer, str) and answer.strip():
                try:
                    parsed_answer = json.loads(answer)
                except json.JSONDecodeError:
                    parsed_answer = None
                embedding = EmbeddingService._search_embedding_candidate(parsed_answer)
                if embedding is not None:
                    return embedding

        raise RuntimeError("Dify embedding 返回中未找到 embedding/vector 字段")

    @staticmethod
    def _search_embedding_candidate(node: Any) -> Any:
        if isinstance(node, list):
            if node and all(isinstance(item, (int, float, str)) for item in node):
                return node
            for item in node:
                candidate = EmbeddingService._search_embedding_candidate(item)
                if candidate is not None:
                    return candidate
            return None

        if isinstance(node, dict):
            for key in ("embedding", "vector"):
                candidate = node.get(key)
                if isinstance(candidate, list):
                    return candidate
            for value in node.values():
                candidate = EmbeddingService._search_embedding_candidate(value)
                if candidate is not None:
                    return candidate

        return None

    @staticmethod
    def _normalize_embedding_vector(raw_embedding: Any, *, source_label: str) -> List[float]:
        if not isinstance(raw_embedding, list):
            raise RuntimeError(f"{source_label} 返回缺少 embedding 向量")

        try:
            embedding = [float(item) for item in raw_embedding]
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{source_label} 返回的 embedding 含非数值元素") from exc

        if settings.EMBEDDING_DIM and len(embedding) != settings.EMBEDDING_DIM:
            raise RuntimeError(
                f"{source_label} 维度不匹配: expected={settings.EMBEDDING_DIM} actual={len(embedding)}"
            )
        return embedding
