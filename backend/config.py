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

    # PostgreSQL configuration.
    DATABASE_URL: str | None = None
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""

    # LLM-1 configuration: structured extraction.
    LLM1_API_URL: str = ""
    LLM1_API_KEY: str = ""
    LLM1_MODEL: str = ""
    LLM1_TIMEOUT_SECONDS: int = 100

    # LLM-2 configuration: sales-assist comparison/generation.
    LLM2_API_URL: str = ""
    LLM2_API_KEY: str = ""
    LLM2_MODEL: str = ""
    LLM2_TIMEOUT_SECONDS: int = 100

    # LLM-2 comparison configuration: optional second sales-assist output.
    LLM2_COMPARE_API_URL: str = ""
    LLM2_COMPARE_API_KEY: str = ""
    LLM2_COMPARE_MODEL: str = ""
    LLM2_COMPARE_TIMEOUT_SECONDS: int = 100
    LOG_LLM_PROMPTS: bool = True
    LOG_LLM_PROMPT_MAX_CHARS: int = 12000
    LOG_DESENSITIZE_ENABLED: bool = True
    SLOW_REQUEST_MS: int = 3000
    HTTP_TRUST_ENV: bool = False

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
    PGVECTOR_REQUIRED: bool = False
    PGVECTOR_ENABLED: bool = False
    PGVECTOR_DIM: int = 1024
    KB_CANDIDATE_LIMIT: int = 500
    KB_KEYWORD_PREFILTER_ENABLED: bool = True
    KB_FULLTEXT_INDEX_ENABLED: bool = True
    KB_HEALTHCHECK_TIMEOUT_SECONDS: int = 5

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
