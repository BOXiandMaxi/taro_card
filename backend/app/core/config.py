from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DEFAULT_AI_MODEL = "gpt-6.1-terra"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "mysql+pymysql://tarot_user:change_me@127.0.0.1:3307/tarot_reading?charset=utf8mb4"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False
    secret_key: SecretStr = SecretStr("")
    session_ttl_seconds: int = Field(default=604800, ge=1, le=2592000)
    auth_attempt_limit: int = Field(default=10, ge=1)
    auth_window_seconds: int = Field(default=900, ge=1, le=86400)
    guest_reading_retention_days: int = Field(default=30, ge=1, le=365)
    reversed_cards_enabled: bool = False
    ai_provider: Literal["disabled", "openai", "gemini"] = "disabled"
    ai_model: str = Field(default=DEFAULT_AI_MODEL, max_length=150)
    ai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    ai_timeout_seconds: float = Field(default=15, gt=0, le=30)
    ai_max_output_tokens: int = Field(default=4000, ge=16, le=32768)
    ai_daily_request_limit: int = Field(default=100, ge=0)
    ai_account_daily_request_limit: int = Field(default=20, ge=0)
    ai_guest_ip_daily_request_limit: int = Field(default=10, ge=0)
    ai_input_usd_per_million: Decimal | None = Field(default=None, ge=0)
    ai_output_usd_per_million: Decimal | None = Field(default=None, ge=0)

    @field_validator("ai_model")
    @classmethod
    def default_ai_model(cls, value: str) -> str:
        return value.strip() or DEFAULT_AI_MODEL

    @model_validator(mode="after")
    def validate_ai_prices(self):
        if (self.ai_input_usd_per_million is None) != (self.ai_output_usd_per_million is None):
            raise ValueError("Set both AI token prices together")
        return self

    @model_validator(mode="after")
    def require_production_secret(self):
        from urllib.parse import urlsplit

        external_origin = any(
            urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
            for origin in self.cors_origins
        )
        secret = self.secret_key.get_secret_value()
        if (external_origin or self.cookie_secure) and (
            len(secret) < 32 or secret == "replace-with-a-long-random-secret"
        ):
            raise ValueError("Set a random SECRET_KEY of at least 32 characters for production")
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if make_url(value).drivername != "mysql+pymysql":
            raise ValueError("DATABASE_URL must use mysql+pymysql")
        return value

    @field_validator("frontend_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        from urllib.parse import urlsplit

        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("At least one explicit frontend origin is required")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("FRONTEND_ORIGINS must contain explicit HTTP(S) origins")
        return ",".join(origins)

    @property
    def cors_origins(self) -> list[str]:
        return self.frontend_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
