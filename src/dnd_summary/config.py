from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DND_", extra="ignore", env_file=".env")

    database_url: str = "postgresql+psycopg://dnd:dnd@localhost:5432/dnd_summary"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "dnd-summary"

    transcripts_root: str = "transcripts"
    prompts_root: str = "prompts"
    artifacts_root: str = "artifacts"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash"
    min_quotes: int = 6
    max_quotes: int = 12
    min_events: int = 8


settings = Settings()
