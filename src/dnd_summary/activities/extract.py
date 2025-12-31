from __future__ import annotations

import json
import time
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import ENGINE, get_session
from dnd_summary.llm import LLMClient
from dnd_summary.llm_cache import ensure_transcript_cache, record_llm_usage
from dnd_summary.mappings import load_character_map
from dnd_summary.models import Base, LLMCall, Run, SessionExtraction, Utterance
from dnd_summary.schema_genai import events_schema, quotes_schema, session_facts_schema
from dnd_summary.schemas import EventExtraction, EvidenceSpan, Mention, QuoteExtraction, SessionFacts


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(settings.prompts_root) / prompt_name
    return prompt_path.read_text(encoding="utf-8")


def _format_transcript(utterances: list[Utterance], character_map: dict[str, str]) -> str:
    lines = []
    for utt in utterances:
        speaker = character_map.get(utt.participant.display_name, utt.participant.display_name)
        lines.append(
            f"[{utt.id}] {speaker} {utt.start_ms}-{utt.end_ms} {utt.text}"
        )
    return "\n".join(lines)


def _merge_quotes(primary: list, secondary: list) -> list:
    seen = {(q.utterance_id, q.char_start, q.char_end) for q in primary}
    merged = list(primary)
    for quote in secondary:
        key = (quote.utterance_id, quote.char_start, quote.char_end)
        if key in seen:
            continue
        merged.append(quote)
        seen.add(key)
    return merged


def _normalize_summary(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(tokens)


def _merge_events(primary: list, secondary: list) -> list:
    seen = {_normalize_summary(event.summary) for event in primary if event.summary}
    merged = list(primary)
    for event in secondary:
        key = _normalize_summary(event.summary)
        if not key or key in seen:
            continue
        merged.append(event)
        seen.add(key)
    return merged


def _find_mention_span(utterances: list[Utterance], name: str) -> EvidenceSpan | None:
    if not name:
        return None
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    for utt in utterances:
        match = pattern.search(utt.text)
        if match:
            return EvidenceSpan(
                utterance_id=utt.id,
                char_start=match.start(),
                char_end=match.end(),
                kind="mention",
                confidence=0.6,
            )
    return None


def _ensure_pc_mentions(
    facts: SessionFacts,
    utterances: list[Utterance],
    character_map: dict[str, str],
) -> None:
    mentioned = {mention.text.lower() for mention in facts.mentions if mention.text}
    speaker_to_utterances: dict[str, list[Utterance]] = {}
    for utt in utterances:
        speaker = character_map.get(utt.participant.display_name, utt.participant.display_name)
        speaker_to_utterances.setdefault(speaker, []).append(utt)

    for character in sorted(set(character_map.values())):
        if not character:
            continue
        if character.lower() in mentioned:
            continue
        evidence = _find_mention_span(utterances, character)
        if not evidence:
            speaker_utts = speaker_to_utterances.get(character, [])
            if speaker_utts:
                utt = speaker_utts[0]
                evidence = EvidenceSpan(
                    utterance_id=utt.id,
                    char_start=0,
                    char_end=len(utt.text),
                    kind="mention",
                    confidence=0.4,
                )
        if evidence:
            facts.mentions.append(
                Mention(
                    text=character,
                    entity_type="character",
                    description=None,
                    evidence=[evidence],
                    confidence=0.5,
                )
            )
            mentioned.add(character.lower())


@activity.defn
async def extract_session_facts_activity(payload: dict) -> dict:
    Base.metadata.create_all(bind=ENGINE)

    run_id = payload["run_id"]
    session_id = payload["session_id"]

    with get_session() as session:
        run = session.query(Run).filter_by(id=run_id).one()
        utterances = (
            session.query(Utterance)
            .filter_by(session_id=session_id)
            .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
            .all()
        )
        if not utterances:
            raise ValueError(f"No utterances found for session {session_id}")

        character_map = load_character_map(session, run.campaign_id)
        transcript_text = _format_transcript(utterances, character_map)
        cache_name, transcript_block = ensure_transcript_cache(
            session, run, transcript_text
        )

        prompt_template = _load_prompt("extract_session_facts_v1.txt")
        speakers = sorted(
            {
                character_map.get(utt.participant.display_name, utt.participant.display_name)
                for utt in utterances
            }
        )
        prompt = prompt_template.format(
            character_map=json.dumps(character_map, sort_keys=True),
            speakers=json.dumps(speakers, sort_keys=True),
            transcript_block=transcript_block,
        )

        client = LLMClient()
        start = time.monotonic()
        try:
            raw_json, usage = client.generate_json_schema(
                prompt,
                schema=session_facts_schema(),
                cached_content=cache_name,
                return_usage=True,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="extract_session_facts",
                    model=settings.gemini_model,
                    prompt_id="extract_session_facts_v1",
                    prompt_version="6",
                    input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                    output_hash=sha256(raw_json.encode("utf-8")).hexdigest(),
                    latency_ms=latency_ms,
                    status="success",
                    created_at=datetime.utcnow(),
                )
            )
            record_llm_usage(
                session,
                run_id=run.id,
                session_id=session_id,
                prompt_id="extract_session_facts_v1",
                prompt_version="6",
                call_kind="extract_session_facts",
                usage=usage,
                cache_name=cache_name,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="extract_session_facts",
                    model=settings.gemini_model,
                    prompt_id="extract_session_facts_v1",
                    prompt_version="6",
                    input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                    output_hash=sha256(b"").hexdigest(),
                    latency_ms=latency_ms,
                    status="error",
                    error=str(exc)[:2000],
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()
            raise

        payload_json = json.loads(raw_json)
        facts = SessionFacts.model_validate(payload_json)
        _ensure_pc_mentions(facts, utterances, character_map)

        if len(facts.quotes) < settings.min_quotes * 2:
            quote_prompt_template = _load_prompt("extract_quotes_v1.txt")
            quote_prompt = quote_prompt_template.format(
                character_map=json.dumps(character_map, sort_keys=True),
                min_quotes=settings.min_quotes,
                max_quotes=settings.max_quotes,
                transcript_block=transcript_block,
            )
            start = time.monotonic()
            try:
                quote_json, usage = client.generate_json_schema(
                    quote_prompt,
                    schema=quotes_schema(),
                    cached_content=cache_name,
                    return_usage=True,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="extract_quotes",
                        model=settings.gemini_model,
                        prompt_id="extract_quotes_v1",
                        prompt_version="4",
                        input_hash=sha256(quote_prompt.encode("utf-8")).hexdigest(),
                        output_hash=sha256(quote_json.encode("utf-8")).hexdigest(),
                        latency_ms=latency_ms,
                        status="success",
                        created_at=datetime.utcnow(),
                    )
                )
                record_llm_usage(
                    session,
                    run_id=run.id,
                    session_id=session_id,
                    prompt_id="extract_quotes_v1",
                    prompt_version="4",
                    call_kind="extract_quotes",
                    usage=usage,
                    cache_name=cache_name,
                )
                quote_payload = json.loads(quote_json)
                quote_facts = QuoteExtraction.model_validate(quote_payload)
                facts.quotes = _merge_quotes(facts.quotes, quote_facts.quotes)
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="extract_quotes",
                        model=settings.gemini_model,
                        prompt_id="extract_quotes_v1",
                        prompt_version="4",
                        input_hash=sha256(quote_prompt.encode("utf-8")).hexdigest(),
                        output_hash=sha256(b"").hexdigest(),
                        latency_ms=latency_ms,
                        status="error",
                        error=str(exc)[:2000],
                        created_at=datetime.utcnow(),
                    )
                )

        if len(facts.events) < settings.min_events:
            event_prompt_template = _load_prompt("extract_events_v1.txt")
            event_prompt = event_prompt_template.format(
                character_map=json.dumps(character_map, sort_keys=True),
                existing_events=json.dumps(
                    [event.summary for event in facts.events], ensure_ascii=True
                ),
                min_events=settings.min_events,
                transcript_block=transcript_block,
            )
            start = time.monotonic()
            try:
                event_json, usage = client.generate_json_schema(
                    event_prompt,
                    schema=events_schema(),
                    cached_content=cache_name,
                    return_usage=True,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="extract_events",
                        model=settings.gemini_model,
                        prompt_id="extract_events_v1",
                        prompt_version="2",
                        input_hash=sha256(event_prompt.encode("utf-8")).hexdigest(),
                        output_hash=sha256(event_json.encode("utf-8")).hexdigest(),
                        latency_ms=latency_ms,
                        status="success",
                        created_at=datetime.utcnow(),
                    )
                )
                record_llm_usage(
                    session,
                    run_id=run.id,
                    session_id=session_id,
                    prompt_id="extract_events_v1",
                    prompt_version="2",
                    call_kind="extract_events",
                    usage=usage,
                    cache_name=cache_name,
                )
                event_payload = json.loads(event_json)
                event_facts = EventExtraction.model_validate(event_payload)
                facts.events = _merge_events(facts.events, event_facts.events)
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="extract_events",
                        model=settings.gemini_model,
                        prompt_id="extract_events_v1",
                        prompt_version="2",
                        input_hash=sha256(event_prompt.encode("utf-8")).hexdigest(),
                        output_hash=sha256(b"").hexdigest(),
                        latency_ms=latency_ms,
                        status="error",
                        error=str(exc)[:2000],
                        created_at=datetime.utcnow(),
                    )
                )

        extraction = SessionExtraction(
            run_id=run.id,
            session_id=session_id,
            kind="session_facts",
            model=settings.gemini_model,
            prompt_id="extract_session_facts_v1",
            prompt_version="6",
            payload=facts.model_dump(mode="json"),
            created_at=datetime.utcnow(),
        )
        session.add(extraction)

    return {
        "run_id": run_id,
        "session_id": session_id,
        "mentions": len(facts.mentions),
        "scenes": len(facts.scenes),
        "events": len(facts.events),
        "threads": len(facts.threads),
        "quotes": len(facts.quotes),
    }
