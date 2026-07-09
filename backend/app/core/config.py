from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app config, loaded from environment variables / .env.

    env_file lists both the backend-local and repo-root .env so this works
    whether uvicorn is launched from /backend or from the repo root.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: Literal["openai"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Session management
    session_ttl_minutes: int = 30

    # Upload / query limits
    max_upload_size_mb: int = 50
    max_rows_returned: int = 5000
    query_timeout_seconds: int = 10
    llm_timeout_seconds: int = 20

    # Multi-turn chat
    history_turns_context: int = 3

    # Rate limiting (per session, in-memory token bucket)
    rate_limit_capacity: int = 10
    rate_limit_refill_per_minute: int = 20

    # CORS
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
