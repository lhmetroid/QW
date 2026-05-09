import json
import logging
from typing import Any, List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """统一封装知识库 embedding provider 调用。"""

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

        provider = EmbeddingService.provider_name()
        if provider == "ollama":
            return EmbeddingService._embed_ollama(clean_text)
        if provider == "dify":
            return EmbeddingService._embed_dify(clean_text)

        return EmbeddingService._embed_openai_compatible(clean_text)

    @staticmethod
    def _embed_ollama(text: str) -> Optional[List[float]]:
        url = settings.EMBEDDING_API_URL.rstrip("/") + "/api/embeddings"
        payload = {
            "model": settings.EMBEDDING_MODEL,
            "prompt": text,
        }
        try:
            session = requests.Session()
            session.trust_env = settings.HTTP_TRUST_ENV
            response = session.post(
                url,
                json=payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return EmbeddingService._normalize_embedding_vector(
                data.get("embedding"),
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
            session = requests.Session()
            session.trust_env = settings.HTTP_TRUST_ENV
            url = EmbeddingService._dify_base_url() + "/completion-messages"
            response = session.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            if response.status_code == 404:
                url = EmbeddingService._dify_base_url() + "/chat-messages"
                response = session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            return EmbeddingService._normalize_embedding_vector(
                EmbeddingService._extract_dify_embedding(response.json()),
                source_label="Dify embedding",
            )
        except Exception as e:
            logger.error("Dify embedding 调用失败: %s", e)
            raise RuntimeError(f"Dify embedding 调用失败: {e}") from e

    @staticmethod
    def _embed_openai_compatible(text: str) -> Optional[List[float]]:
        if not settings.EMBEDDING_API_KEY:
            raise RuntimeError("知识库 Embedding KEY 未配置")

        url = settings.EMBEDDING_API_URL.rstrip("/") + "/embeddings"
        headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"}
        payload = {"model": settings.EMBEDDING_MODEL, "input": text}
        try:
            session = requests.Session()
            session.trust_env = settings.HTTP_TRUST_ENV
            response = session.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("data", [{}])[0].get("embedding")
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
