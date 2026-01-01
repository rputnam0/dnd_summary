from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator

from dnd_summary.config import settings

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - optional dependency is installed for Postgres
    Vector = None  # type: ignore


class EmbeddingVector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and Vector is not None:
            return dialect.type_descriptor(Vector(settings.embedding_dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        return value


def _hash_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _hash_embedding(text: str, dimensions: int) -> list[float]:
    rng = random.Random(_hash_seed(text))
    return [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


class EmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [_hash_embedding(text, settings.embedding_dimensions) for text in texts]
        if settings.embedding_normalize:
            return [_normalize_vector(vector) for vector in vectors]
        return vectors


class HFEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Missing sentence-transformers for HF embeddings.") from exc

        self._model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        self._model.max_seq_length = settings.embedding_max_length
        model_dims = self._model.get_sentence_embedding_dimension()
        if settings.embedding_dimensions != model_dims:
            raise ValueError(
                "Embedding dimensions mismatch: "
                f"config={settings.embedding_dimensions} model={model_dims}"
            )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=settings.embedding_normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


_PROVIDER: EmbeddingProvider | None = None
_PROVIDER_KEY: tuple[str, str, str, int, bool] | None = None


def _provider_key() -> tuple[str, str, str, int, bool]:
    return (
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_device,
        settings.embedding_dimensions,
        settings.embedding_normalize,
    )


def _get_provider() -> EmbeddingProvider:
    global _PROVIDER
    global _PROVIDER_KEY
    key = _provider_key()
    if _PROVIDER and _PROVIDER_KEY == key:
        return _PROVIDER
    if settings.embedding_provider == "hash":
        provider: EmbeddingProvider = HashEmbeddingProvider()
    elif settings.embedding_provider == "hf":
        provider = HFEmbeddingProvider()
    else:
        raise ValueError(f"Unsupported embedding_provider: {settings.embedding_provider}")
    _PROVIDER = provider
    _PROVIDER_KEY = key
    return provider


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    provider = _get_provider()
    return provider.embed(texts)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if left is None or right is None:
        return 0.0
    if len(left) == 0 or len(right) == 0 or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(frozen=True)
class EmbeddingInput:
    target_type: str
    target_id: str
    campaign_id: str
    session_id: str | None
    run_id: str | None
    content: str
