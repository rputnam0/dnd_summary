from __future__ import annotations

from dnd_summary.rerank import RerankCandidate, rerank


def test_hash_rerank_is_deterministic(settings_overrides):
    settings_overrides(rerank_provider="hash")
    candidates = [
        RerankCandidate(candidate_id="a", text="alpha", dense_score=0.5, payload={}),
        RerankCandidate(candidate_id="b", text="beta", dense_score=0.4, payload={}),
    ]

    first = rerank("query", candidates)
    second = rerank("query", candidates)

    assert [score for _candidate, score in first] == [score for _candidate, score in second]
