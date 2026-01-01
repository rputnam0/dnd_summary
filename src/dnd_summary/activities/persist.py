from __future__ import annotations

from temporalio import activity

from dnd_summary.db import get_session
from dnd_summary.models import (
    Event,
    Mention,
    Quote,
    Scene,
    SessionExtraction,
    Thread,
    ThreadUpdate,
    Utterance,
)
import re
from difflib import SequenceMatcher

from dnd_summary.run_steps import run_step
from dnd_summary.schemas import EvidenceSpan, SessionFacts


def _clean_evidence(
    utterance_lookup: dict[str, str],
    evidence_list: list,
) -> tuple[list, int, int]:
    cleaned = []
    dropped = 0
    clamped = 0
    for evidence in evidence_list:
        utterance_text = utterance_lookup.get(evidence.utterance_id)
        if utterance_text is None:
            dropped += 1
            continue
        if evidence.char_start is None or evidence.char_end is None:
            cleaned.append(evidence)
            continue
        if evidence.char_start < 0 or evidence.char_end <= evidence.char_start:
            dropped += 1
            continue
        if evidence.char_start >= len(utterance_text):
            dropped += 1
            continue
        if evidence.char_end > len(utterance_text):
            evidence.char_end = len(utterance_text)
            clamped += 1
            if evidence.char_end <= evidence.char_start:
                dropped += 1
                continue
        cleaned.append(evidence)
    return cleaned, dropped, clamped


def _build_mention_pattern(text: str) -> re.Pattern | None:
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return None
    if len(tokens) == 1:
        return re.compile(re.escape(tokens[0]), re.IGNORECASE)
    pattern = r"\b" + r"\W+".join(re.escape(token) for token in tokens) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def _find_mention_span(
    utterances: list[Utterance],
    mention_text: str,
) -> EvidenceSpan | None:
    pattern = _build_mention_pattern(mention_text)
    if not pattern:
        return None
    for utt in utterances:
        match = pattern.search(utt.text)
        if match:
            return EvidenceSpan(
                utterance_id=utt.id,
                char_start=match.start(),
                char_end=match.end(),
                kind="mention",
                confidence=0.7,
            )
    return None


def _normalize_text(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _clean_text_similarity(raw: str, clean: str) -> float:
    raw_norm = _normalize_text(raw)
    clean_norm = _normalize_text(clean)
    if not raw_norm or not clean_norm:
        return 0.0
    return SequenceMatcher(None, raw_norm, clean_norm).ratio()


def _find_quote_span(text: str, clean_text: str | None) -> tuple[int, int] | None:
    if not clean_text:
        return None
    cleaned = clean_text.strip()
    if not cleaned:
        return None
    lower_text = text.lower()
    lower_clean = cleaned.lower()
    idx = lower_text.find(lower_clean)
    if idx == -1:
        return None
    return idx, idx + len(cleaned)


def _recover_utterance_by_time(
    utterances: list[Utterance],
    start_ms: int,
    end_ms: int,
) -> Utterance | None:
    best = None
    best_overlap = 0
    for utt in utterances:
        if utt.start_ms <= start_ms and utt.end_ms >= end_ms:
            return utt
        overlap = min(end_ms, utt.end_ms) - max(start_ms, utt.start_ms)
        if overlap > best_overlap:
            best_overlap = overlap
            best = utt
    if best_overlap > 0:
        return best
    return None


def _fallback_span_by_time(
    utterances: list[Utterance],
    start_ms: int,
    end_ms: int,
) -> EvidenceSpan | None:
    if not utterances:
        return None
    candidate = _recover_utterance_by_time(utterances, start_ms, end_ms)
    if not candidate:
        return None
    if not candidate.text:
        return None
    return EvidenceSpan(
        utterance_id=candidate.id,
        char_start=0,
        char_end=len(candidate.text),
        kind="support",
        confidence=0.3,
    )


def _clean_quotes(
    utterance_lookup: dict[str, str],
    utterances: list[Utterance],
    facts: SessionFacts,
) -> tuple[list, int, int, int, int]:
    cleaned = []
    dropped = 0
    clean_text_dropped = 0
    clamped = 0
    deduped = 0
    seen: dict[str, set[str]] = {}
    for quote in facts.quotes:
        utterance_text = utterance_lookup.get(quote.utterance_id)
        if utterance_text is None and quote.utterance_id:
            match = re.match(r"^(\\d+)-(\\d+)$", quote.utterance_id)
            if match:
                start_ms = int(match.group(1))
                end_ms = int(match.group(2))
                recovered = _recover_utterance_by_time(utterances, start_ms, end_ms)
                if recovered:
                    quote.utterance_id = recovered.id
                    utterance_text = recovered.text
                    clamped += 1
            if utterance_text is None and quote.clean_text:
                for utt in utterances:
                    span = _find_quote_span(utt.text, quote.clean_text)
                    if span:
                        quote.utterance_id = utt.id
                        quote.char_start, quote.char_end = span
                        utterance_text = utt.text
                        clamped += 1
                        break
        if utterance_text is None:
            dropped += 1
            continue
        if quote.char_start is None or quote.char_end is None:
            if not utterance_text:
                dropped += 1
                continue
            span = _find_quote_span(utterance_text, quote.clean_text)
            if span:
                quote.char_start, quote.char_end = span
            else:
                quote.char_start = 0
                quote.char_end = len(utterance_text)
            clamped += 1
        if quote.char_start < 0 or quote.char_end <= quote.char_start:
            if not utterance_text:
                dropped += 1
                continue
            span = _find_quote_span(utterance_text, quote.clean_text)
            if span:
                quote.char_start, quote.char_end = span
            else:
                quote.char_start = 0
                quote.char_end = len(utterance_text)
            clamped += 1
        if quote.char_start >= len(utterance_text):
            dropped += 1
            continue
        if quote.char_end > len(utterance_text):
            quote.char_end = len(utterance_text)
            clamped += 1
            if quote.char_end <= quote.char_start:
                dropped += 1
                continue
        if quote.clean_text:
            raw_span = utterance_text[quote.char_start : quote.char_end]
            if _clean_text_similarity(raw_span, quote.clean_text) < 0.6:
                quote.clean_text = None
                clean_text_dropped += 1
        quote_text = quote.clean_text or utterance_text[quote.char_start : quote.char_end]
        normalized = _normalize_text(quote_text)
        if normalized:
            existing = seen.setdefault(quote.utterance_id, set())
            if normalized in existing:
                deduped += 1
                continue
            existing.add(normalized)
        cleaned.append(quote)
    return cleaned, dropped, clean_text_dropped, clamped, deduped


def _count_missing_evidence(items: list) -> int:
    missing = 0
    for item in items:
        if not item.evidence:
            missing += 1
    return missing


def _count_update_missing_evidence(updates: list) -> int:
    missing = 0
    for update in updates:
        if not update.evidence:
            missing += 1
    return missing


def _count_evidence_missing_spans(items: list) -> int:
    missing = 0
    for item in items:
        for ev in item.evidence or []:
            if ev.char_start is None or ev.char_end is None:
                missing += 1
    return missing


def _count_update_evidence_missing_spans(updates: list) -> int:
    missing = 0
    for update in updates:
        for ev in update.evidence or []:
            if ev.char_start is None or ev.char_end is None:
                missing += 1
    return missing


@activity.defn
async def persist_session_facts_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]

    with run_step(run_id, session_id, "persist_session_facts"):
        with get_session() as session:
            extraction = (
                session.query(SessionExtraction)
                .filter_by(run_id=run_id, session_id=session_id, kind="session_facts")
                .order_by(SessionExtraction.created_at.desc())
                .first()
            )
            if not extraction:
                raise ValueError("Missing session_facts extraction")

            facts = SessionFacts.model_validate(extraction.payload)
            utterances = (
                session.query(Utterance)
                .filter_by(session_id=session_id)
                .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
                .all()
            )
            utterance_lookup = {utt.id: utt.text for utt in utterances}
            (
                cleaned_quotes,
                dropped_quotes,
                clean_text_dropped,
                quotes_clamped,
                quotes_deduped,
            ) = _clean_quotes(
                utterance_lookup, utterances, facts
            )

            for model in (Mention, Scene, Event, Quote, Thread, ThreadUpdate):
                session.query(model).filter_by(run_id=run_id, session_id=session_id).delete()

            dropped_evidence = 0
            clamped_evidence = 0
            for mention in facts.mentions:
                mention.evidence, dropped, clamped = _clean_evidence(
                    utterance_lookup, mention.evidence
                )
                dropped_evidence += dropped
                clamped_evidence += clamped
            for scene in facts.scenes:
                scene.evidence, dropped, clamped = _clean_evidence(
                    utterance_lookup, scene.evidence
                )
                dropped_evidence += dropped
                clamped_evidence += clamped
            for event in facts.events:
                event.evidence, dropped, clamped = _clean_evidence(
                    utterance_lookup, event.evidence
                )
                dropped_evidence += dropped
                clamped_evidence += clamped
            for thread in facts.threads:
                thread.evidence, dropped, clamped = _clean_evidence(
                    utterance_lookup, thread.evidence
                )
                dropped_evidence += dropped
                clamped_evidence += clamped
                for update in thread.updates:
                    update.evidence, dropped, clamped = _clean_evidence(
                        utterance_lookup, update.evidence
                    )
                    dropped_evidence += dropped
                    clamped_evidence += clamped

            for scene in facts.scenes:
                if not scene.evidence:
                    fallback = _fallback_span_by_time(
                        utterances, scene.start_ms, scene.end_ms
                    )
                    if fallback:
                        scene.evidence = [fallback]

            for event in facts.events:
                if not event.evidence:
                    fallback = _fallback_span_by_time(
                        utterances, event.start_ms, event.end_ms
                    )
                    if fallback:
                        event.evidence = [fallback]

            for thread in facts.threads:
                if not thread.evidence:
                    for update in thread.updates:
                        if update.evidence:
                            thread.evidence = update.evidence
                            break
                for update in thread.updates:
                    if update.evidence or not update.related_event_indexes:
                        continue
                    for idx in update.related_event_indexes:
                        if 0 <= idx < len(facts.events):
                            event_evidence = facts.events[idx].evidence
                            if event_evidence:
                                update.evidence = event_evidence
                                break

            mention_repairs = 0
            mentions_dropped = 0
            repaired_mentions = []
            for mention in facts.mentions:
                if not mention.evidence:
                    repaired = _find_mention_span(utterances, mention.text)
                    if repaired:
                        mention.evidence = [repaired]
                        mention_repairs += 1
                if not mention.evidence:
                    mentions_dropped += 1
                    continue
                repaired_mentions.append(mention)
            facts.mentions = repaired_mentions

            mentions = [
                Mention(
                    run_id=run_id,
                    session_id=session_id,
                    text=mention.text,
                    entity_type=mention.entity_type,
                    description=mention.description,
                    evidence=[e.model_dump(mode="json") for e in mention.evidence],
                    confidence=mention.confidence,
                )
                for mention in facts.mentions
            ]
            scenes = [
                Scene(
                    run_id=run_id,
                    session_id=session_id,
                    title=scene.title,
                    summary=scene.summary,
                    location=scene.location,
                    start_ms=scene.start_ms,
                    end_ms=scene.end_ms,
                    participants=scene.participants,
                    evidence=[e.model_dump(mode="json") for e in scene.evidence],
                )
                for scene in facts.scenes
            ]
            events = [
                Event(
                    run_id=run_id,
                    session_id=session_id,
                    event_type=event.event_type,
                    summary=event.summary,
                    start_ms=event.start_ms,
                    end_ms=event.end_ms,
                    entities=event.entities,
                    evidence=[e.model_dump(mode="json") for e in event.evidence],
                    confidence=event.confidence,
                )
                for event in facts.events
            ]
            quotes = [
                Quote(
                    run_id=run_id,
                    session_id=session_id,
                    utterance_id=quote.utterance_id,
                    char_start=quote.char_start,
                    char_end=quote.char_end,
                    speaker=quote.speaker,
                    note=quote.note,
                    clean_text=quote.clean_text,
                )
                for quote in cleaned_quotes
            ]

            session.add_all(mentions)
            session.add_all(scenes)
            session.add_all(events)
            session.add_all(quotes)
            session.flush()

            thread_rows = []
            thread_updates = []
            event_index_to_id = {idx: event.id for idx, event in enumerate(events)}
            for thread in facts.threads:
                thread_row = Thread(
                    run_id=run_id,
                    session_id=session_id,
                    title=thread.title,
                    kind=thread.kind,
                    status=thread.status,
                    summary=thread.summary,
                    evidence=[e.model_dump(mode="json") for e in thread.evidence],
                    confidence=thread.confidence,
                )
                session.add(thread_row)
                session.flush()
                thread_rows.append(thread_row)

                for update in thread.updates:
                    related_ids = []
                    for idx in update.related_event_indexes:
                        event_id = event_index_to_id.get(idx)
                        if event_id:
                            related_ids.append(event_id)
                    thread_updates.append(
                        ThreadUpdate(
                            run_id=run_id,
                            session_id=session_id,
                            thread_id=thread_row.id,
                            update_type=update.update_type,
                            note=update.note,
                            evidence=[e.model_dump(mode="json") for e in update.evidence],
                            related_event_ids=related_ids,
                        )
                    )

            if thread_updates:
                session.add_all(thread_updates)

            metrics = {
                "mentions": len(facts.mentions),
                "scenes": len(facts.scenes),
                "events": len(facts.events),
                "threads": len(facts.threads),
                "quotes": len(cleaned_quotes),
                "quotes_dropped": dropped_quotes,
                "quotes_deduped": quotes_deduped,
                "quotes_clamped": quotes_clamped,
                "evidence_dropped": dropped_evidence,
                "evidence_clamped": clamped_evidence,
                "mentions_repaired": mention_repairs,
                "mentions_dropped_no_evidence": mentions_dropped,
                "clean_text_dropped": clean_text_dropped,
            }
            metrics_record = SessionExtraction(
                run_id=run_id,
                session_id=session_id,
                kind="persist_metrics",
                model="system",
                prompt_id="persist_session_facts",
                prompt_version="1",
                payload=metrics,
            )
            session.add(metrics_record)

            quality_report = {
                "mentions_missing_evidence": _count_missing_evidence(facts.mentions),
                "scenes_missing_evidence": _count_missing_evidence(facts.scenes),
                "events_missing_evidence": _count_missing_evidence(facts.events),
                "threads_missing_evidence": _count_missing_evidence(facts.threads),
                "thread_updates_missing_evidence": _count_update_missing_evidence(
                    [u for t in facts.threads for u in t.updates]
                ),
                "mentions_evidence_missing_spans": _count_evidence_missing_spans(facts.mentions),
                "scenes_evidence_missing_spans": _count_evidence_missing_spans(facts.scenes),
                "events_evidence_missing_spans": _count_evidence_missing_spans(facts.events),
                "threads_evidence_missing_spans": _count_evidence_missing_spans(facts.threads),
                "thread_updates_evidence_missing_spans": _count_update_evidence_missing_spans(
                    [u for t in facts.threads for u in t.updates]
                ),
                "quotes_missing_clean_text": len(
                    [q for q in cleaned_quotes if not q.clean_text]
                ),
                "quotes_with_clean_text": len(
                    [q for q in cleaned_quotes if q.clean_text]
                ),
            }
            session.add(
                SessionExtraction(
                    run_id=run_id,
                    session_id=session_id,
                    kind="quality_report",
                    model="system",
                    prompt_id="quality_report",
                    prompt_version="1",
                    payload=quality_report,
                )
            )

        return {
            "run_id": run_id,
            "session_id": session_id,
            **metrics,
        }
