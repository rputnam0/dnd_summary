from __future__ import annotations

from dataclasses import dataclass

from dnd_summary.activities.extract import (
    _ensure_pc_mentions,
    _merge_events,
    _merge_quotes,
    _normalize_summary,
)
from dnd_summary.schemas import AtomicEvent, EvidenceSpan, QuoteCandidate, SessionFacts


@dataclass
class DummyParticipant:
    display_name: str


@dataclass
class DummyUtterance:
    id: str
    text: str
    participant: DummyParticipant


def test_merge_quotes_deduplicates():
    primary = [QuoteCandidate(utterance_id="u1", char_start=0, char_end=3)]
    secondary = [
        QuoteCandidate(utterance_id="u1", char_start=0, char_end=3),
        QuoteCandidate(utterance_id="u2", char_start=1, char_end=4),
    ]

    merged = _merge_quotes(primary, secondary)

    assert len(merged) == 2
    assert merged[1].utterance_id == "u2"


def test_merge_events_skips_duplicate_summaries():
    primary = [AtomicEvent(event_type="combat", start_ms=0, end_ms=1, summary="Fight")]
    secondary = [
        AtomicEvent(event_type="combat", start_ms=0, end_ms=1, summary="Fight"),
        AtomicEvent(event_type="social", start_ms=1, end_ms=2, summary="Talk"),
    ]

    merged = _merge_events(primary, secondary)

    assert len(merged) == 2
    assert merged[1].summary == "Talk"


def test_normalize_summary_strips_punctuation():
    assert _normalize_summary("Hello, World!") == "hello world"


def test_ensure_pc_mentions_adds_missing_characters():
    utterances = [
        DummyUtterance(id="u1", text="Hello", participant=DummyParticipant("Alice")),
        DummyUtterance(id="u2", text="More text", participant=DummyParticipant("Bob")),
    ]
    facts = SessionFacts(mentions=[])
    character_map = {"Alice": "Lia", "Bob": "Rex"}

    _ensure_pc_mentions(facts, utterances, character_map)

    names = {mention.text for mention in facts.mentions}
    assert "Lia" in names
    assert "Rex" in names
    for mention in facts.mentions:
        assert mention.evidence
        assert isinstance(mention.evidence[0], EvidenceSpan)
