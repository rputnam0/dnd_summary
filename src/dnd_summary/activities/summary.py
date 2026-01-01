from __future__ import annotations

import json
import time
import re
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from hashlib import sha256

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.llm import LLMClient
from dnd_summary.llm_cache import (
    CacheRequiredError,
    build_text_metrics,
    cache_hit_from_usage,
    ensure_transcript_cache,
    record_llm_usage,
)
from dnd_summary.mappings import load_character_map
from dnd_summary.models import Artifact, LLMCall, Quote, Run, SessionExtraction, Utterance
from dnd_summary.render import render_summary_docx
from dnd_summary.run_steps import run_step
from dnd_summary.schema_genai import summary_plan_schema
from dnd_summary.schemas import SessionFacts, SummaryPlan
from dnd_summary.transcript_format import format_transcript


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(settings.prompts_root) / prompt_name
    return prompt_path.read_text(encoding="utf-8")


SUMMARY_VARIANTS = [
    {
        "kind": "summary_text",
        "prompt": "write_summary_v1.txt",
        "prompt_version": "3",
        "artifact_prefix": "summary",
        "title": "Session Summary",
    },
    {
        "kind": "summary_player",
        "prompt": "write_summary_player_v1.txt",
        "prompt_version": "1",
        "artifact_prefix": "summary_player",
        "title": "Player Recap",
    },
    {
        "kind": "summary_dm",
        "prompt": "write_summary_dm_v1.txt",
        "prompt_version": "1",
        "artifact_prefix": "summary_dm",
        "title": "DM Prep",
    },
    {
        "kind": "summary_hooks",
        "prompt": "write_summary_hooks_v1.txt",
        "prompt_version": "1",
        "artifact_prefix": "summary_hooks",
        "title": "Next Session Hooks",
    },
    {
        "kind": "summary_npc_changes",
        "prompt": "write_summary_npc_changes_v1.txt",
        "prompt_version": "1",
        "artifact_prefix": "summary_npc_changes",
        "title": "NPC Roster Changes",
    },
]


def _quote_text(utterance: str, quote: Quote) -> str:
    if quote.clean_text:
        return quote.clean_text.strip()
    if quote.char_start is None or quote.char_end is None:
        return utterance.strip()
    return utterance[quote.char_start : quote.char_end].strip()


def _select_best_quote(quotes: list[Quote]) -> Quote:
    with_spans = [quote for quote in quotes if quote.char_start is not None and quote.char_end]
    if with_spans:
        return max(with_spans, key=lambda q: (q.char_end - q.char_start))
    return quotes[0]


def _quote_bank(
    utterances: list[Utterance],
    quotes: list[Quote],
    quote_ids: list[str] | None = None,
) -> str:
    lookup = {utt.id: utt.text for utt in utterances}
    grouped: dict[str, list[Quote]] = {}
    for quote in quotes:
        grouped.setdefault(quote.utterance_id, []).append(quote)

    target_ids = quote_ids or list(grouped.keys())
    lines = []
    for qid in target_ids:
        entries = grouped.get(qid)
        if not entries:
            continue
        utterance_text = lookup.get(qid, "")
        if not utterance_text:
            continue
        quote = _select_best_quote(entries)
        text = _quote_text(utterance_text, quote)
        if text:
            lines.append(f"{qid} ::: {text}")
    return "\n".join(lines)


def _build_quote_lookup(
    utterances: list[Utterance],
    quotes: list[Quote],
    quote_ids: list[str],
) -> dict[str, str]:
    lookup = {utt.id: utt.text for utt in utterances}
    grouped: dict[str, list[Quote]] = {}
    for quote in quotes:
        grouped.setdefault(quote.utterance_id, []).append(quote)

    quote_lookup: dict[str, str] = {}
    for qid in quote_ids:
        entries = grouped.get(qid)
        if not entries:
            continue
        utterance_text = lookup.get(qid, "")
        if not utterance_text:
            continue
        quote = _select_best_quote(entries)
        text = _quote_text(utterance_text, quote)
        if text:
            quote_lookup[qid] = text
    return quote_lookup


def _normalize_quote(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _quote_allowed(quote: str, allowed: list[str]) -> bool:
    cleaned = _normalize_quote(quote)
    if not cleaned:
        return True
    if cleaned in allowed:
        return True
    tokens = cleaned.split()
    if len(tokens) >= 3:
        for candidate in allowed:
            if cleaned in candidate or candidate in cleaned:
                return True
    if len(tokens) >= 4:
        for candidate in allowed:
            if SequenceMatcher(None, cleaned, candidate).ratio() >= 0.85:
                return True
    return False


def _validate_summary_quotes(summary_text: str, quote_texts: list[str]) -> None:
    if "[" in summary_text and "]" in summary_text:
        raise ValueError("Summary appears to contain utterance IDs.")

    if not quote_texts:
        return

    quoted = re.findall(r'"([^"]+)"', summary_text)
    if not quoted:
        return

    allowed_set = {_normalize_quote(q) for q in quote_texts if q}
    allowed_list = [q for q in allowed_set if q]
    missing = []
    for q in quoted:
        if not _quote_allowed(q, allowed_list):
            missing.append(q)
    if missing:
        raise ValueError("Summary contains quotes not in quote bank.")


def _strip_unapproved_quotes(summary_text: str, quote_texts: list[str]) -> str:
    allowed_set = {_normalize_quote(q) for q in quote_texts if q}
    allowed_list = [q for q in allowed_set if q]

    def _replace(match: re.Match[str]) -> str:
        quote = match.group(1)
        if _quote_allowed(quote, allowed_list):
            return match.group(0)
        return quote

    return re.sub(r'"([^"]+)"', _replace, summary_text)


@activity.defn
async def plan_summary_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]
    with run_step(run_id, session_id, "summary_plan"):

        with get_session() as session:
            run = session.query(Run).filter_by(id=run_id).one()
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
            quotes = (
                session.query(Quote)
                .filter_by(session_id=session_id, run_id=run_id)
                .all()
            )

            character_map = load_character_map(session, run.campaign_id)
            transcript_text, _ = format_transcript(utterances, character_map)
            transcript_stats = build_text_metrics("transcript", transcript_text)
            base_usage = {
                "utterance_count": len(utterances),
                "character_count": len(character_map),
                "quote_count": len(quotes),
            }
            try:
                cache_name, transcript_block = ensure_transcript_cache(
                    session, run, transcript_text
                )
            except CacheRequiredError:
                session.commit()
                raise
            quote_bank = _quote_bank(utterances, quotes)
            quote_bank_stats = build_text_metrics("quote_bank", quote_bank)
            facts_json = json.dumps(facts.model_dump(mode="json"))
            facts_stats = build_text_metrics("session_facts", facts_json)
            prompt = _load_prompt("summary_plan_v1.txt").format(
                session_facts=facts_json,
                quote_bank=quote_bank or "[none]",
                character_map=json.dumps(character_map, sort_keys=True),
                transcript_block=transcript_block,
            )
            prompt_stats = build_text_metrics("prompt", prompt)
            usage_meta = {
                **transcript_stats,
                **quote_bank_stats,
                **facts_stats,
                **prompt_stats,
                **base_usage,
            }

            client = LLMClient()
            start = time.monotonic()
            try:
                raw_json, usage = client.generate_json_schema(
                    prompt,
                    schema=summary_plan_schema(),
                    cached_content=cache_name,
                    return_usage=True,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                cache_hit = cache_hit_from_usage(usage, cache_name)
                if settings.require_transcript_cache and not cache_hit:
                    session.add(
                        LLMCall(
                            run_id=run.id,
                            session_id=session_id,
                            kind="summary_plan",
                            model=settings.gemini_model,
                            prompt_id="summary_plan_v1",
                            prompt_version="3",
                            input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                            output_hash=sha256(b"").hexdigest(),
                            latency_ms=latency_ms,
                            status="error",
                            error="Transcript cache miss for summary_plan.",
                            created_at=datetime.utcnow(),
                        )
                    )
                    record_llm_usage(
                        session,
                        run_id=run.id,
                        session_id=session_id,
                        prompt_id="summary_plan_v1",
                        prompt_version="3",
                        call_kind="summary_plan",
                        usage=usage,
                        cache_name=cache_name,
                        metadata=usage_meta,
                    )
                    raise CacheRequiredError("Transcript cache miss for summary_plan.")
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="summary_plan",
                        model=settings.gemini_model,
                        prompt_id="summary_plan_v1",
                        prompt_version="3",
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
                    prompt_id="summary_plan_v1",
                    prompt_version="3",
                    call_kind="summary_plan",
                    usage=usage,
                    cache_name=cache_name,
                    metadata=usage_meta,
                )
            except CacheRequiredError:
                session.commit()
                raise
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                session.add(
                    LLMCall(
                        run_id=run.id,
                        session_id=session_id,
                        kind="summary_plan",
                        model=settings.gemini_model,
                        prompt_id="summary_plan_v1",
                        prompt_version="3",
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
            plan_payload = json.loads(raw_json)
            plan = SummaryPlan.model_validate(plan_payload)

            plan_record = SessionExtraction(
                run_id=run.id,
                session_id=session_id,
                kind="summary_plan",
                model=settings.gemini_model,
                prompt_id="summary_plan_v1",
                prompt_version="3",
                payload=plan.model_dump(mode="json"),
                created_at=datetime.utcnow(),
            )
            session.add(plan_record)

        return {
            "run_id": run_id,
            "session_id": session_id,
            "beats": len(plan.beats),
        }


@activity.defn
async def write_summary_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]
    with run_step(run_id, session_id, "summary_text"):

        with get_session() as session:
            run = session.query(Run).filter_by(id=run_id).one()
            facts_record = (
                session.query(SessionExtraction)
                .filter_by(run_id=run_id, session_id=session_id, kind="session_facts")
                .order_by(SessionExtraction.created_at.desc())
                .first()
            )
            plan_record = (
                session.query(SessionExtraction)
                .filter_by(run_id=run_id, session_id=session_id, kind="summary_plan")
                .order_by(SessionExtraction.created_at.desc())
                .first()
            )
            if not facts_record or not plan_record:
                raise ValueError("Missing session_facts or summary_plan extraction")

            facts = SessionFacts.model_validate(facts_record.payload)
            plan = SummaryPlan.model_validate(plan_record.payload)

            utterances = (
                session.query(Utterance)
                .filter_by(session_id=session_id)
                .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
                .all()
            )
            quotes = (
                session.query(Quote)
                .filter_by(session_id=session_id, run_id=run_id)
                .all()
            )
            character_map = load_character_map(session, run.campaign_id)
            transcript_text, _ = format_transcript(utterances, character_map)
            transcript_stats = build_text_metrics("transcript", transcript_text)
            base_usage = {
                "utterance_count": len(utterances),
                "character_count": len(character_map),
                "quote_count": len(quotes),
            }
            try:
                cache_name, transcript_block = ensure_transcript_cache(
                    session, run, transcript_text
                )
            except CacheRequiredError:
                session.commit()
                raise

            quote_ids: list[str] = []
            for beat in plan.beats:
                for qid in beat.quote_utterance_ids:
                    if qid not in quote_ids:
                        quote_ids.append(qid)
            quote_bank = _quote_bank(utterances, quotes, quote_ids)
            quote_lookup = _build_quote_lookup(utterances, quotes, quote_ids)
            quote_bank_stats = build_text_metrics("quote_bank", quote_bank)
            facts_json = json.dumps(facts.model_dump(mode="json"))
            plan_json = json.dumps(plan.model_dump(mode="json"))
            facts_stats = build_text_metrics("session_facts", facts_json)
            plan_stats = build_text_metrics("summary_plan", plan_json)
            base_usage["quote_ids_count"] = len(quote_ids)

            client = LLMClient()
            summaries: dict[str, str] = {}

            for variant in SUMMARY_VARIANTS:
                prompt = _load_prompt(variant["prompt"]).format(
                    summary_plan=plan_json,
                    session_facts=facts_json,
                    quote_bank=quote_bank or "[none]",
                    character_map=json.dumps(character_map, sort_keys=True),
                    transcript_block=transcript_block,
                )
                prompt_stats = build_text_metrics("prompt", prompt)
                usage_meta = {
                    **transcript_stats,
                    **quote_bank_stats,
                    **facts_stats,
                    **plan_stats,
                    **prompt_stats,
                    **base_usage,
                    "summary_variant": variant["kind"],
                }

                start = time.monotonic()
                try:
                    summary_text, usage = client.generate_text(
                        prompt,
                        cached_content=cache_name,
                        return_usage=True,
                    )
                    latency_ms = int((time.monotonic() - start) * 1000)
                    cache_hit = cache_hit_from_usage(usage, cache_name)
                    if settings.require_transcript_cache and not cache_hit:
                        session.add(
                            LLMCall(
                                run_id=run.id,
                                session_id=session_id,
                                kind=variant["kind"],
                                model=settings.gemini_model,
                                prompt_id=variant["prompt"],
                                prompt_version=variant["prompt_version"],
                                input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                                output_hash=sha256(b"").hexdigest(),
                                latency_ms=latency_ms,
                                status="error",
                                error=f"Transcript cache miss for {variant['kind']}.",
                                created_at=datetime.utcnow(),
                            )
                        )
                        record_llm_usage(
                            session,
                            run_id=run.id,
                            session_id=session_id,
                            prompt_id=variant["prompt"],
                            prompt_version=variant["prompt_version"],
                            call_kind=variant["kind"],
                            usage=usage,
                            cache_name=cache_name,
                            metadata=usage_meta,
                        )
                        raise CacheRequiredError(
                            f"Transcript cache miss for {variant['kind']}."
                        )
                    session.add(
                        LLMCall(
                            run_id=run.id,
                            session_id=session_id,
                            kind=variant["kind"],
                            model=settings.gemini_model,
                            prompt_id=variant["prompt"],
                            prompt_version=variant["prompt_version"],
                            input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                            output_hash=sha256(summary_text.encode("utf-8")).hexdigest(),
                            latency_ms=latency_ms,
                            status="success",
                            created_at=datetime.utcnow(),
                        )
                    )
                    record_llm_usage(
                        session,
                        run_id=run.id,
                        session_id=session_id,
                        prompt_id=variant["prompt"],
                        prompt_version=variant["prompt_version"],
                        call_kind=variant["kind"],
                        usage=usage,
                        cache_name=cache_name,
                        metadata=usage_meta,
                    )
                except CacheRequiredError:
                    session.commit()
                    raise
                except Exception as exc:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    session.add(
                        LLMCall(
                            run_id=run.id,
                            session_id=session_id,
                            kind=variant["kind"],
                            model=settings.gemini_model,
                            prompt_id=variant["prompt"],
                            prompt_version=variant["prompt_version"],
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

                try:
                    _validate_summary_quotes(summary_text, list(quote_lookup.values()))
                except ValueError:
                    summary_text = _strip_unapproved_quotes(
                        summary_text,
                        list(quote_lookup.values()),
                    )
                    _validate_summary_quotes(summary_text, list(quote_lookup.values()))

                summary_record = SessionExtraction(
                    run_id=run.id,
                    session_id=session_id,
                    kind=variant["kind"],
                    model=settings.gemini_model,
                    prompt_id=variant["prompt"],
                    prompt_version=variant["prompt_version"],
                    payload={"text": summary_text},
                    created_at=datetime.utcnow(),
                )
                session.add(summary_record)
                summaries[variant["kind"]] = summary_text

        chars = sum(len(text) for text in summaries.values())
        return {"run_id": run_id, "session_id": session_id, "chars": chars}


@activity.defn
async def render_summary_docx_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]
    with run_step(run_id, session_id, "render_summary_docx"):

        with get_session() as session:
            summary_records = (
                session.query(SessionExtraction)
                .filter(
                    SessionExtraction.run_id == run_id,
                    SessionExtraction.session_id == session_id,
                    SessionExtraction.kind.in_([variant["kind"] for variant in SUMMARY_VARIANTS]),
                )
                .order_by(SessionExtraction.created_at.desc())
                .all()
            )
            if not summary_records:
                raise ValueError("Missing summary_text extraction")

            summary_by_kind = {}
            for record in summary_records:
                if record.kind in summary_by_kind:
                    continue
                summary_by_kind[record.kind] = record

            output_dir = Path(settings.artifacts_root) / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            artifacts: list[Artifact] = []
            for variant in SUMMARY_VARIANTS:
                record = summary_by_kind.get(variant["kind"])
                if not record:
                    continue
                summary_text = record.payload["text"]
                txt_path = output_dir / f"{variant['artifact_prefix']}.txt"
                txt_path.write_text(summary_text, encoding="utf-8")
                output_path = output_dir / f"{variant['artifact_prefix']}.docx"
                render_summary_docx(summary_text, output_path, title=variant["title"])
                artifacts.append(
                    Artifact(
                        run_id=run_id,
                        session_id=session_id,
                        kind=f"{variant['artifact_prefix']}_docx",
                        path=str(output_path),
                        meta={"bytes": output_path.stat().st_size},
                        created_at=datetime.utcnow(),
                    )
                )
                artifacts.append(
                    Artifact(
                        run_id=run_id,
                        session_id=session_id,
                        kind=f"{variant['artifact_prefix']}_txt",
                        path=str(txt_path),
                        meta={"bytes": txt_path.stat().st_size},
                        created_at=datetime.utcnow(),
                    )
                )
            session.add_all(artifacts)

        return {
            "run_id": run_id,
            "session_id": session_id,
            "variants": list(summary_by_kind.keys()),
        }
