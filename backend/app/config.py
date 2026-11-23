"""Application configuration loaded from environment variables using Pydantic v2."""

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Typed application settings validated at startup."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "AI Keyword Research & Content Planning Agent"
    APP_VERSION: str = "0.1.0"
    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    APP_DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Database
    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/keyword_research_db"
    )

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Security & Auth
    JWT_SECRET_KEY: SecretStr = SecretStr(
        "dev-only-jwt-secret-key-change-before-production-32chars"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, gt=0)
    OAUTH_TOKEN_ENCRYPTION_KEY: SecretStr = SecretStr(
        "dev-only-fernet-placeholder-replace-with-fernet-key="
    )

    # OpenAI & Embeddings
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    EMBEDDING_PROVIDER: Literal["openai", "sentence_transformers"] = "openai"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    LOCAL_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"

    # DataForSEO
    DATAFORSEO_LOGIN: str | None = None
    DATAFORSEO_PASSWORD: SecretStr | None = None
    DATAFORSEO_USE_SANDBOX: bool = True
    DATAFORSEO_ENABLE_KEYWORD_API: bool = False

    # Semrush
    SEMRUSH_API_KEY: SecretStr | None = None
    SEMRUSH_API_BASE_URL: str = "https://api.semrush.com"

    # Google OAuth (GSC & Google Sheets)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/v1/oauth/google/callback"

    # Safe Competitor HTML Crawler
    CRAWLER_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0.0, le=60.0)
    CRAWLER_MAX_BYTES: int = Field(default=2_097_152, gt=0)
    CRAWLER_USER_AGENT: str = "KeywordResearchAgentBot/1.0 (+https://example.com/bot)"

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value: Any) -> str:
        """Uppercase and validate logging level."""
        level = str(value).strip().upper()
        if level not in VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")
        return level

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parse comma-separated origins string or JSON list into a list of strings."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        if isinstance(value, (list, tuple)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list of strings")

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Enforce strict secret and debug rules in production environments."""
        if self.APP_ENV == "production":
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False when APP_ENV is production")
            jwt_secret = self.JWT_SECRET_KEY.get_secret_value()
            if "replace-with" in jwt_secret or "dev-only" in jwt_secret or len(jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be a non-placeholder secret of at least 32 characters in production"
                )
            enc_key = self.OAUTH_TOKEN_ENCRYPTION_KEY.get_secret_value()
            if "replace-with" in enc_key or "dev-only" in enc_key:
                raise ValueError(
                    "OAUTH_TOKEN_ENCRYPTION_KEY must not use a placeholder value in production"
                )
        return self

    @property
    def is_production(self) -> bool:
        """Return True when running in production."""
        return self.APP_ENV == "production"

    @property
    def use_json_logs(self) -> bool:
        """Use JSON log output in staging and production environments."""
        return self.APP_ENV in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
