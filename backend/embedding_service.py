import logging
from typing import List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """统一封装知识库 embedding provider 调用。"""

    @staticmethod
    def embed(text: str) -> Optional[List[float]]:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Embedding text is empty")

        provider = (settings.EMBEDDING_PROVIDER or "").lower()
        if provider == "ollama":
            return EmbeddingService._embed_ollama(clean_text)

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
            embedding = data.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError("Ollama embedding 返回缺少 embedding 字段")
            if settings.EMBEDDING_DIM and len(embedding) != settings.EMBEDDING_DIM:
                raise RuntimeError(
                    f"Ollama embedding 维度不匹配: expected={settings.EMBEDDING_DIM} actual={len(embedding)}"
                )
            return embedding
        except Exception as e:
            logger.error("Ollama embedding 调用失败: %s", e)
            raise RuntimeError(f"Ollama embedding 调用失败: {e}") from e

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
            if not isinstance(embedding, list):
                raise RuntimeError("OpenAI-compatible embedding 返回缺少 data[0].embedding 字段")
            if settings.EMBEDDING_DIM and len(embedding) != settings.EMBEDDING_DIM:
                raise RuntimeError(
                    f"OpenAI-compatible embedding 维度不匹配: expected={settings.EMBEDDING_DIM} actual={len(embedding)}"
                )
            return embedding
        except Exception as e:
            logger.error("OpenAI-compatible embedding 调用失败: %s", e)
            raise RuntimeError(f"OpenAI-compatible embedding 调用失败: {e}") from e
