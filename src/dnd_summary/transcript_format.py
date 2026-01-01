from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from dnd_summary.schemas import EvidenceSpan, EventExtraction, QuoteExtraction, SessionFacts


def _timecode(ms: int) -> str:
    total_seconds = max(ms, 0) // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_transcript(
    utterances: Iterable,
    character_map: dict[str, str],
) -> tuple[str, dict[str, str]]:
    counts = Counter()
    for utt in utterances:
        counts[_timecode(utt.start_ms)] += 1

    indices: dict[str, int] = defaultdict(int)
    lines: list[str] = []
    key_to_id: dict[str, str] = {}

    for utt in utterances:
        timecode = _timecode(utt.start_ms)
        if counts[timecode] > 1:
            indices[timecode] += 1
            key = f"{timecode}#{indices[timecode]}"
        else:
            key = timecode
        speaker = character_map.get(utt.participant.display_name, utt.participant.display_name)
        lines.append(f"[{key}] {speaker}: {utt.text}")
        key_to_id[key] = utt.id

    return "\n".join(lines), key_to_id


def _map_utterance_id(value: str, id_map: dict[str, str]) -> str:
    return id_map.get(value, value)


def _map_evidence(evidence: Iterable[EvidenceSpan], id_map: dict[str, str]) -> None:
    for span in evidence:
        span.utterance_id = _map_utterance_id(span.utterance_id, id_map)


def map_session_facts_utterance_ids(facts: SessionFacts, id_map: dict[str, str]) -> None:
    for mention in facts.mentions:
        _map_evidence(mention.evidence, id_map)
    for scene in facts.scenes:
        _map_evidence(scene.evidence, id_map)
    for event in facts.events:
        _map_evidence(event.evidence, id_map)
    for thread in facts.threads:
        _map_evidence(thread.evidence, id_map)
        for update in thread.updates:
            _map_evidence(update.evidence, id_map)
    for quote in facts.quotes:
        quote.utterance_id = _map_utterance_id(quote.utterance_id, id_map)


def map_quote_extraction_utterance_ids(
    extraction: QuoteExtraction, id_map: dict[str, str]
) -> None:
    for quote in extraction.quotes:
        quote.utterance_id = _map_utterance_id(quote.utterance_id, id_map)


def map_event_extraction_utterance_ids(
    extraction: EventExtraction, id_map: dict[str, str]
) -> None:
    for event in extraction.events:
        _map_evidence(event.evidence, id_map)
