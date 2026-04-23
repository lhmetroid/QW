from __future__ import annotations

import os
import sys

from config import settings


def is_placeholder(value: object) -> bool:
    text = str(value or "").strip()
    return not text or text.startswith("your-")


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
    required_missing.extend(name for name, value in required.items() if is_placeholder(value))

    if required_missing:
        print("启动失败：知识库核心配置缺失或仍为占位值: " + ", ".join(required_missing), file=sys.stderr)
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

    print("知识库核心启动配置检查通过")
    for item in warnings:
        print("可选功能提示：" + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
