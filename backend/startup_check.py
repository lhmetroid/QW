from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

import requests

from config import settings


LEGACY_SALES_KB_HOSTS = {"192.168.31.124"}


def is_placeholder(value: object) -> bool:
    text = str(value or "").strip()
    return not text or text.startswith("your-")


def normalized_embedding_provider() -> str:
    provider = (settings.EMBEDDING_PROVIDER or "").strip().lower().replace("-", "_")
    if provider == "ollama":
        return "ollama"
    if provider in {"dify", "dify_app"}:
        return "dify"
    return "openai_compatible"


def validate_sales_kb_base_url() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    base_url = str(settings.SALES_KB_API_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        return ["SALES_KB_API_BASE_URL"], warnings

    parsed = urlparse(base_url)
    host = str(parsed.hostname or "").strip().lower()
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme != "https":
        errors.append("SALES_KB_API_BASE_URL 必须使用 https://knowledgebase.speedasia.net")
    if host in LEGACY_SALES_KB_HOSTS:
        errors.append("SALES_KB_API_BASE_URL 仍指向旧内网 IP，请改为 https://knowledgebase.speedasia.net")
    if parsed.port:
        warnings.append("SALES_KB_API_BASE_URL 当前不需要显式端口号，请改为不带端口的反向代理域名")
    try:
        session = requests.Session()
        session.trust_env = settings.HTTP_TRUST_ENV
        response = session.post(
            f"{base_url}/kb-units/qa-retrieve",
            json={"question": "付款"},
            timeout=settings.KB_HEALTHCHECK_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            warnings.append(f"知识库2 Q&A 探测返回 HTTP {response.status_code}，页面运行状态会显示异常")
        else:
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
                warnings.append("知识库2 Q&A 探测返回结构不是 {answers:[...]}，请检查反向代理目标服务")
    except Exception as exc:
        warnings.append(f"知识库2 Q&A 探测失败：{exc}")
    return errors, warnings


def main() -> int:
    db_configured = bool(settings.DATABASE_URL and not is_placeholder(settings.DATABASE_URL)) or not any(
        is_placeholder(value)
        for value in [settings.DB_NAME, settings.DB_USER, settings.DB_PASSWORD]
    )

    required_missing: list[str] = []
    if not db_configured:
        required_missing.append("DATABASE_URL 或 DB_NAME/DB_USER/DB_PASSWORD")

    required = {
        "EMBEDDING_API_URL": settings.EMBEDDING_API_URL,
        "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        "LLM1_API_URL": settings.LLM1_API_URL,
        "LLM1_API_KEY": settings.LLM1_API_KEY,
        "LLM1_MODEL": settings.LLM1_MODEL,
        "LLM2_API_URL": settings.LLM2_API_URL,
        "LLM2_API_KEY": settings.LLM2_API_KEY,
        "LLM2_MODEL": settings.LLM2_MODEL,
        "LLM2_COMPARE_API_URL": settings.LLM2_COMPARE_API_URL,
        "LLM2_COMPARE_API_KEY": settings.LLM2_COMPARE_API_KEY,
        "LLM2_COMPARE_MODEL": settings.LLM2_COMPARE_MODEL,
    }
    if normalized_embedding_provider() != "ollama":
        required["EMBEDDING_API_KEY"] = settings.EMBEDDING_API_KEY
    required_missing.extend(name for name, value in required.items() if is_placeholder(value))
    sales_kb_errors, sales_kb_warnings = validate_sales_kb_base_url()
    required_missing.extend(sales_kb_errors)

    if required_missing:
        messages: list[str] = []
        if required_missing:
            messages.append("缺失或仍为占位值: " + ", ".join(required_missing))
        print("启动失败：知识库核心配置错误。 " + "；".join(messages), file=sys.stderr)
        return 1

    warnings: list[str] = []
    crm_ready = not any(
        is_placeholder(value)
        for value in [settings.CRM_DBHost, settings.CRM_DBName, settings.CRM_DBUserId, settings.CRM_DBPassword]
    )
    if not crm_ready:
        warnings.append("CRM 只读辅助未完整配置，客户画像/CRM 融合会不可用；知识库导入、检索、发布不受影响")

    wecom_app_ready = not any(is_placeholder(value) for value in [settings.CORP_ID, settings.CORP_SECRET])
    if not wecom_app_ready:
        warnings.append("企微应用 CorpID/Secret 未完整配置，企微 token 与发消息不可用")
    if is_placeholder(settings.AGENT_ID):
        warnings.append("AGENT_ID 未配置，企微应用卡片/消息发送暂不启用")
    if any(is_placeholder(value) for value in [settings.TOKEN, settings.ENCODING_AES_KEY]):
        warnings.append("企微回调 Token/EncodingAESKey 未配置，回调验签暂不启用")

    sdk_path = os.path.join(os.path.dirname(__file__), "WeWorkFinanceSdk.dll")
    private_key_path = settings.PRIVATE_KEY_PATH
    if not os.path.isabs(private_key_path):
        private_key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), private_key_path)
    archive_ready = (
        os.path.exists(sdk_path)
        and os.path.exists(private_key_path)
        and not is_placeholder(settings.CHATDATA_SECRET)
    )
    if not archive_ready:
        warnings.append("企微会话存档 SDK/私钥/CHATDATA_SECRET 未完整配置，同步今日真实记录不可用")
    if settings.ENABLE_ARCHIVE_POLLING and not archive_ready:
        warnings.append("ENABLE_ARCHIVE_POLLING=true 但会话存档配置不完整，后台会跳过自动轮询")
    warnings.extend(sales_kb_warnings)

    print("知识库核心启动配置检查通过")
    for item in warnings:
        print("可选功能提示：" + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
