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


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if settings.embedding_provider != "hash":
        raise ValueError(f"Unsupported embedding_provider: {settings.embedding_provider}")
    dimensions = settings.embedding_dimensions
    return [_hash_embedding(text, dimensions) for text in texts]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
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
