from __future__ import annotations

from dataclasses import dataclass

from dnd_summary.schemas import (
    EvidenceSpan,
    EventExtraction,
    QuoteExtraction,
    SessionFacts,
)
from dnd_summary.transcript_format import (
    format_transcript,
    map_event_extraction_utterance_ids,
    map_quote_extraction_utterance_ids,
    map_session_facts_utterance_ids,
)


@dataclass
class DummyParticipant:
    display_name: str


@dataclass
class DummyUtterance:
    id: str
    start_ms: int
    text: str
    participant: DummyParticipant


def test_format_transcript_generates_timecode_keys():
    alice = DummyParticipant(display_name="Alice")
    bob = DummyParticipant(display_name="Bob")
    utterances = [
        DummyUtterance(id="utt-1", start_ms=0, text="Hello", participant=alice),
        DummyUtterance(id="utt-2", start_ms=0, text="Hi", participant=bob),
        DummyUtterance(id="utt-3", start_ms=1000, text="Yo", participant=alice),
    ]

    transcript, id_map = format_transcript(utterances, {})

    assert "[00:00:00#1] Alice: Hello" in transcript
    assert "[00:00:00#2] Bob: Hi" in transcript
    assert "[00:00:01] Alice: Yo" in transcript
    assert id_map["00:00:00#1"] == "utt-1"
    assert id_map["00:00:01"] == "utt-3"


def test_map_session_facts_updates_evidence_ids():
    id_map = {"00:00:00": "utt-1", "00:00:01#1": "utt-2"}
    facts = SessionFacts(
        mentions=[
            {
                "text": "Goblin",
                "entity_type": "monster",
                "evidence": [EvidenceSpan(utterance_id="00:00:00")],
            }
        ],
        quotes=[{"utterance_id": "00:00:01#1"}],
    )

    map_session_facts_utterance_ids(facts, id_map)

    assert facts.mentions[0].evidence[0].utterance_id == "utt-1"
    assert facts.quotes[0].utterance_id == "utt-2"


def test_map_extraction_helpers_replace_ids():
    id_map = {"00:00:02": "utt-3"}
    quote_extraction = QuoteExtraction(quotes=[{"utterance_id": "00:00:02"}])
    event_extraction = EventExtraction(
        events=[{"event_type": "combat", "start_ms": 0, "end_ms": 1, "summary": "Fight", "evidence": [EvidenceSpan(utterance_id="00:00:02")]}]
    )

    map_quote_extraction_utterance_ids(quote_extraction, id_map)
    map_event_extraction_utterance_ids(event_extraction, id_map)

    assert quote_extraction.quotes[0].utterance_id == "utt-3"
    assert event_extraction.events[0].evidence[0].utterance_id == "utt-3"
