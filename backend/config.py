import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime values are loaded from the project-root .env file.
    # The defaults below are placeholders only, so stale credentials do not
    # appear configured when .env is missing.

    # External deployment base URL.
    EXTERNAL_API_BASE_URL: str = ""
    CLOUDFLARED_TUNNEL_TOKEN: str = ""
    CLOUDFLARED_PUBLIC_HOSTNAME: str = ""
    CLOUDFLARED_TARGET_URL: str = ""
    CLOUDFLARED_BIN: str = ""
    CLOUDFLARED_LOG_FILE: str = "logs/cloudflared.log"
    ENABLE_LOCAL_HTTPS: bool = False
    LOCAL_HTTPS_CERT_FILE: str = "backend/certs/localhost-cert.pem"
    LOCAL_HTTPS_KEY_FILE: str = "backend/certs/localhost-key.pem"

    # WeCom app configuration.
    CORP_ID: str = ""
    CORP_SECRET: str = ""
    AGENT_ID: str = ""
    TOKEN: str = ""
    ENCODING_AES_KEY: str = ""

    # WeCom chat archive configuration.
    CHATDATA_SECRET: str = ""
    PRIVATE_KEY_PATH: str = ""
    PUBLIC_KEY_VER: int = 2
    ENABLE_ARCHIVE_POLLING: bool = False
    ARCHIVE_SYNC_TIMEOUT_SECONDS: int = 300
    SIDEBAR_ASSIST_SYNC_ARCHIVE_BEFORE_READ_DEFAULT: bool = False

    # PostgreSQL configuration.
    DATABASE_URL: str | None = None
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DATABASE_CONNECT_TIMEOUT_SECONDS: int = 15
    DATABASE_STATEMENT_TIMEOUT_MS: int = 20000
    DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS: int = 60000
    DATABASE_LOCK_TIMEOUT_MS: int = 5000

    # LLM-1 configuration: structured extraction.
    LLM1_API_URL: str = ""
    LLM1_API_KEY: str = ""
    LLM1_MODEL: str = ""
    LLM1_TIMEOUT_SECONDS: int = 100
    LLM1_MAX_TOKENS: int = 700
    STAGE1_USE_LLM2: bool = False
    LLM1_COMPARE_API_URL: str = ""
    LLM1_COMPARE_API_KEY: str = ""
    LLM1_COMPARE_MODEL: str = ""
    LLM1_COMPARE_TIMEOUT_SECONDS: int = 100

    # LLM-2 configuration: sales-assist comparison/generation.
    LLM2_API_URL: str = ""
    LLM2_API_KEY: str = ""
    LLM2_MODEL: str = ""
    LLM2_TIMEOUT_SECONDS: int = 100

    # Mail draft LLM provider. `deepseek` reuses LLM2_* by default.
    MAIL_DRAFT_LLM_PROVIDER: str = "deepseek"
    MAIL_DRAFT_LLM_TEMPERATURE: float = 0.55
    MAIL_DRAFT_LLM_MAX_TOKENS: int = 1800
    MAIL_DRAFT_OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"
    MAIL_DRAFT_OPENAI_API_KEY: str = ""
    MAIL_DRAFT_OPENAI_MODEL: str = "gpt-4o-mini"
    MAIL_DRAFT_OPENAI_TIMEOUT_SECONDS: int = 60
    MAIL_DRAFT_ANTHROPIC_API_URL: str = "https://api.anthropic.com/v1/messages"
    MAIL_DRAFT_ANTHROPIC_API_KEY: str = ""
    MAIL_DRAFT_ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    MAIL_DRAFT_ANTHROPIC_TIMEOUT_SECONDS: int = 60
    # Backward-compatible alias from the recording parser config. Do not log the key.
    RECORDING_PARSE_OPENAI_VISION_API_URL: str = ""
    RECORDING_PARSE_OPENAI_VISION_API_KEY: str = ""

    # 训练AI (train_ai) 配置：另一条 AI 回复途径，调用平台 model-chat 接口，与当前流程并行触发。
    TRAIN_AI_ENABLED: bool = True
    TRAIN_AI_BASE_URL: str = "http://zjsphs.2288.org:11486"
    TRAIN_AI_API_KEY: str = ""
    TRAIN_AI_MODEL: str = "unsloth-qwen2.5-task-60"
    TRAIN_AI_TIMEOUT_SECONDS: int = 10
    TRAIN_AI_MODEL_LIST_TIMEOUT_SECONDS: int = 2
    TRAIN_AI_MAX_TOKENS: int = 300
    TRAIN_AI_TEMPERATURE: float = 0.2

    # LLM-2 comparison configuration: optional second sales-assist output.
    LLM2_COMPARE_API_URL: str = ""
    LLM2_COMPARE_API_KEY: str = ""
    LLM2_COMPARE_MODEL: str = ""
    LLM2_COMPARE_TIMEOUT_SECONDS: int = 100
    API_REPLY_SINGLE_MODEL_SINGLE_STYLE: bool = True
    API_REPLY_ENABLE_SCORING: bool = False
    WECOM_FOLLOWUP_SCORING_WINDOW_ENABLED: bool = True
    WECOM_FOLLOWUP_SCORING_WINDOW_START_HOUR_BJ: int = 20
    WECOM_FOLLOWUP_SCORING_WINDOW_END_HOUR_BJ: int = 24
    LOG_LLM_PROMPTS: bool = True
    LOG_LLM_PROMPT_MAX_CHARS: int = 12000
    LOG_DESENSITIZE_ENABLED: bool = True
    SLOW_REQUEST_MS: int = 3000
    HTTP_TRUST_ENV: bool = False
    FRONTEND_AUTH_ENABLED: bool = True
    FRONTEND_AUTH_USERNAME: str = "admin"
    FRONTEND_AUTH_PASSWORD: str = "Qw@2026"
    FRONTEND_AUTH_EXTRA_USERS: str = "hj:123456:mail_quality_only"
    FRONTEND_AUTH_SECRET: str = ""
    FRONTEND_AUTH_SESSION_SECONDS: int = 86400

    # Knowledge-base embedding configuration.
    EMBEDDING_PROVIDER: str = ""
    EMBEDDING_API_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_DIM: int = 1024
    EMBEDDING_TIMEOUT_SECONDS: int = 100

    # Knowledge-base LLM assist configuration.
    KB_LLM_ASSIST_PROVIDER: str = "llm1"
    KB_LLM_ASSIST_USE_LLM1_CONFIG: bool = True
    KB_LLM_ASSIST_MODEL: str = ""

    # Knowledge-base rerank/vector-store strategy.
    RERANK_ENABLED: bool = False
    RERANK_PROVIDER: str = ""
    RERANK_MODEL: str = ""
    KB_RRF_K_CONSTANT: int = 60
    ENABLE_QUERY_REWRITING: bool = True
    AGENT_BUILDER_CHUNK_OVERLAP: int = 80
    PGVECTOR_REQUIRED: bool = False
    PGVECTOR_ENABLED: bool = False
    PGVECTOR_DIM: int = 1024
    KB_CANDIDATE_LIMIT: int = 300
    KB_KEYWORD_PREFILTER_ENABLED: bool = True
    KB_FULLTEXT_INDEX_ENABLED: bool = True
    KB_HEALTHCHECK_TIMEOUT_SECONDS: int = 5
    SALES_KB_API_BASE_URL: str = "https://knowledgebase.speedasia.net"
    SALES_KB_API_TIMEOUT_SECONDS: int = 8

    # Mail Few-Shot retrieval admission.
    MAIL_FEWSHOT_MIN_USEFUL_SCORE: float = 0.60

    # Offline training pipeline runner.
    TRAINING_RUNNER_COMMAND: str = ""
    TRAINING_RUNNER_WORKDIR: str = ""
    TRAINING_RUNNER_TIMEOUT_SECONDS: int = 7200

    # CRM MSSQL configuration.
    CRM_DBHost: str = ""
    CRM_DBPort: int = 1433
    CRM_DBName: str = ""
    CRM_DBUserId: str = ""
    CRM_DBPassword: str = ""
    CRM_ODBC_DRIVER: str = ""
    CRM_DB_ENCRYPT: bool = False
    CRM_DB_TRUST_SERVER_CERTIFICATE: bool = True
    CRM_DB_CONNECTION_TIMEOUT: int = 100

    # Redis configuration.
    REDIS_HOST: str = ""
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def database_url(self) -> str:
        import urllib.parse

        if self.DATABASE_URL:
            return self.DATABASE_URL
        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
