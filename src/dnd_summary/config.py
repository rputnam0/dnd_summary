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
    enable_explicit_cache: bool = True
    require_transcript_cache: bool = True
    transcript_format_version: str = "timecode_v1"
    cache_ttl_seconds: int = 3600
    cache_release_on_complete: bool = True
    cache_release_on_partial: bool = True
    cache_release_on_failed: bool = True
    llm_max_retries: int = 3
    llm_retry_min_seconds: float = 1.0
    llm_retry_max_seconds: float = 12.0
    llm_retry_backoff: float = 2.0
    min_quotes: int = 6
    max_quotes: int = 12
    min_events: int = 8
    llm_input_cost_per_million: float = 0.50
    llm_output_cost_per_million: float = 3.00
    llm_cached_cost_per_million: float = 0.05
    llm_cache_storage_cost_per_million_hour: float = 1.00
    auth_enabled: bool = False

    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 1024
    embedding_version: str = "v1"
    embedding_batch_size: int = 48
    embedding_device: str = "cpu"
    embedding_max_length: int = 8192
    embedding_normalize: bool = True

    rerank_enabled: bool = False
    rerank_provider: str = "hash"
    rerank_model: str = "BAAI/bge-reranker-large"
    rerank_device: str = "cpu"
    rerank_batch_size: int = 32
    rerank_max_length: int = 512

    semantic_dense_top_k: int = 100
    semantic_rerank_top_k: int = 50
    semantic_final_k: int = 15


settings = Settings()
