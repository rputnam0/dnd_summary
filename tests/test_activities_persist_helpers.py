from __future__ import annotations

from dataclasses import dataclass

from dnd_summary.activities.persist import (
    _build_mention_pattern,
    _clean_evidence,
    _clean_quotes,
    _clean_text_similarity,
    _fallback_span_by_time,
    _find_mention_span,
    _find_quote_span,
    _recover_utterance_by_time,
)
from dnd_summary.schemas import EvidenceSpan, QuoteCandidate, SessionFacts


@dataclass
class DummyUtterance:
    id: str
    start_ms: int
    end_ms: int
    text: str


def test_clean_evidence_drops_invalid_spans():
    utterance_lookup = {"u1": "hello"}
    evidence = [
        EvidenceSpan(utterance_id="u1", char_start=0, char_end=2),
        EvidenceSpan(utterance_id="u1", char_start=-1, char_end=1),
        EvidenceSpan(utterance_id="missing", char_start=0, char_end=1),
        EvidenceSpan(utterance_id="u1", char_start=0, char_end=99),
    ]

    cleaned, dropped, clamped = _clean_evidence(utterance_lookup, evidence)

    assert len(cleaned) == 2
    assert dropped == 2
    assert clamped == 1


def test_build_mention_pattern_handles_tokens():
    pattern = _build_mention_pattern("Sir Galahad")
    assert pattern is not None
    assert pattern.search("sir galahad")


def test_find_mention_span_returns_span():
    utterances = [DummyUtterance(id="u1", start_ms=0, end_ms=1, text="Hello Galahad")]

    span = _find_mention_span(utterances, "Galahad")

    assert span is not None
    assert span.utterance_id == "u1"


def test_clean_text_similarity_scores_match():
    assert _clean_text_similarity("Hello", "hello") >= 0.9


def test_find_quote_span_locates_text():
    span = _find_quote_span("Hello there", "there")
    assert span == (6, 11)


def test_recover_utterance_by_time_selects_overlap():
    utterances = [
        DummyUtterance(id="u1", start_ms=0, end_ms=1000, text="first"),
        DummyUtterance(id="u2", start_ms=1000, end_ms=2000, text="second"),
    ]

    recovered = _recover_utterance_by_time(utterances, 900, 1100)

    assert recovered is not None
    assert recovered.id in {"u1", "u2"}


def test_fallback_span_by_time_returns_support_span():
    utterances = [DummyUtterance(id="u1", start_ms=0, end_ms=1000, text="first")]

    span = _fallback_span_by_time(utterances, 100, 200)

    assert span is not None
    assert span.utterance_id == "u1"


def test_clean_quotes_clamps_spans():
    utterances = [DummyUtterance(id="u1", start_ms=0, end_ms=1000, text="hello")]
    facts = SessionFacts(quotes=[QuoteCandidate(utterance_id="u1", char_start=0, char_end=99)])
    utterance_lookup = {"u1": "hello"}

    cleaned, dropped, clean_text_dropped, clamped, deduped = _clean_quotes(
        utterance_lookup, utterances, facts
    )

    assert len(cleaned) == 1
    assert dropped == 0
    assert clean_text_dropped == 0
    assert clamped >= 1
    assert deduped == 0
