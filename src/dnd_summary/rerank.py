from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

from dnd_summary.config import settings


@dataclass(frozen=True)
class RerankCandidate:
    candidate_id: str
    text: str
    dense_score: float
    payload: dict


class RerankerProvider:
    def score(self, query: str, candidates: Sequence[RerankCandidate]) -> list[float]:
        raise NotImplementedError


class HashRerankerProvider(RerankerProvider):
    def score(self, query: str, candidates: Sequence[RerankCandidate]) -> list[float]:
        scores = []
        for candidate in candidates:
            blob = f"{query}::{candidate.text}".encode("utf-8")
            digest = hashlib.sha256(blob).hexdigest()
            scores.append(int(digest[:12], 16) / 0xFFFFFFFFFFFF)
        return scores


class HFRerankerProvider(RerankerProvider):
    def __init__(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Missing sentence-transformers for HF reranker.") from exc

        self._model = CrossEncoder(
            settings.rerank_model,
            device=settings.rerank_device,
            max_length=settings.rerank_max_length,
        )

    def score(self, query: str, candidates: Sequence[RerankCandidate]) -> list[float]:
        pairs = [(query, candidate.text) for candidate in candidates]
        scores = self._model.predict(
            pairs,
            batch_size=settings.rerank_batch_size,
            show_progress_bar=False,
        )
        return [float(score) for score in scores]


_RERANKER: RerankerProvider | None = None
_RERANKER_KEY: tuple[str, str, str, int] | None = None


def _reranker_key() -> tuple[str, str, str, int]:
    return (
        settings.rerank_provider,
        settings.rerank_model,
        settings.rerank_device,
        settings.rerank_max_length,
    )


def _get_reranker() -> RerankerProvider:
    global _RERANKER
    global _RERANKER_KEY
    key = _reranker_key()
    if _RERANKER and _RERANKER_KEY == key:
        return _RERANKER
    if settings.rerank_provider == "hash":
        reranker: RerankerProvider = HashRerankerProvider()
    elif settings.rerank_provider == "hf":
        reranker = HFRerankerProvider()
    else:
        raise ValueError(f"Unsupported rerank_provider: {settings.rerank_provider}")
    _RERANKER = reranker
    _RERANKER_KEY = key
    return reranker


def rerank(query: str, candidates: Sequence[RerankCandidate]) -> list[tuple[RerankCandidate, float]]:
    if not candidates:
        return []
    reranker = _get_reranker()
    scores = reranker.score(query, candidates)
    return list(zip(candidates, scores))
