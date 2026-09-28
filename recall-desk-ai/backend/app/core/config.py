"""Environment based configuration for the RecallDesk AI backend."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, List, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    app_name: str = "RecallDesk AI"
    debug: bool = True

    # Database (MySQL only - SQLite is intentionally not supported)
    database_url: str = "mysql+aiomysql://root:password@localhost:3306/recall_desk"

    # Auth
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Groq
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 60.0
    groq_max_retries: int = 2

    # Hindsight
    hindsight_api_url: str | None = None
    hindsight_api_key: str | None = None
    hindsight_bank_id: str = "recall-desk-ai"
    hindsight_timeout_seconds: float = 60.0
    hindsight_recall_budget: Literal["low", "mid", "high"] = "mid"
    hindsight_recall_max_tokens: int = 1200
    hindsight_retain_async: bool = False

    # Agent
    agent_max_tool_iterations: int = 4

    # CORS (comma separated in the environment)
    cors_origins: Annotated[List[str], NoDecode] = ["http://localhost:5173"]

    # Seed
    seed_demo_email: str = "demo@recalldesk.local"
    seed_demo_password: str = "DemoPassword123!"

    @field_validator("groq_api_key", "hindsight_api_key", "hindsight_api_url", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def hindsight_configured(self) -> bool:
        return bool(self.hindsight_api_url and self.hindsight_api_key)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
