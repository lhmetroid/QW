import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WeCom app configuration. Override these values with environment variables.
    CORP_ID: str = "your-corp-id"
    CORP_SECRET: str = "your-corp-secret"
    AGENT_ID: str = "your-agent-id"
    TOKEN: str = "your-token"
    ENCODING_AES_KEY: str = "your-encoding-aes-key"

    # WeCom chat archive configuration.
    CHATDATA_SECRET: str = "your-chatdata-secret"
    PRIVATE_KEY_PATH: str = os.path.join(os.path.dirname(__file__), "private_key.pem")
    PUBLIC_KEY_VER: int = 2

    # PostgreSQL configuration.
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "your-db-name"
    DB_USER: str = "your-db-user"
    DB_PASSWORD: str = "your-db-password"

    # LLM-1 configuration.
    LLM1_API_URL: str = "https://api.deepseek.com"
    LLM1_API_KEY: str = "your-llm1-api-key"
    LLM1_MODEL: str = "deepseek-chat"
    LLM1_TIMEOUT_SECONDS: int = 100

    # LLM-2 configuration.
    LLM2_API_URL: str = "https://api.deepseek.com"
    LLM2_API_KEY: str = "your-llm2-api-key"
    LLM2_MODEL: str = "deepseek-chat"
    LLM2_TIMEOUT_SECONDS: int = 100
    LOG_LLM_PROMPTS: bool = True
    LOG_LLM_PROMPT_MAX_CHARS: int = 12000

    # Knowledge-base embedding configuration.
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_API_URL: str = "http://localhost:11434"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "bge-m3:latest"
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

    # CRM MSSQL configuration.
    CRM_DBHost: str = "localhost"
    CRM_DBPort: int = 1433
    CRM_DBName: str = "your-crm-db-name"
    CRM_DBUserId: str = "your-crm-db-user"
    CRM_DBPassword: str = "your-crm-db-password"
    CRM_ODBC_DRIVER: str = "ODBC Driver 18 for SQL Server"
    CRM_DB_ENCRYPT: bool = False
    CRM_DB_TRUST_SERVER_CERTIFICATE: bool = True
    CRM_DB_CONNECTION_TIMEOUT: int = 100

    # Redis configuration.
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def database_url(self) -> str:
        import urllib.parse

        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
