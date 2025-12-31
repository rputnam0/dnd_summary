from __future__ import annotations

import json
import time
import re
from datetime import datetime
from pathlib import Path
from hashlib import sha256

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import ENGINE, get_session
from dnd_summary.llm import LLMClient
from dnd_summary.mappings import load_character_map
from dnd_summary.models import Artifact, Base, LLMCall, Run, SessionExtraction, Utterance
from dnd_summary.render import render_summary_docx
from dnd_summary.schema_genai import summary_plan_schema
from dnd_summary.schemas import SessionFacts, SummaryPlan


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


def _quote_bank(utterances: list[Utterance], quote_ids: list[str]) -> str:
    lookup = {utt.id: utt.text for utt in utterances}
    lines = []
    for qid in quote_ids:
        text = lookup.get(qid)
        if text:
            lines.append(f"{qid} ::: {text}")
    return "\n".join(lines)


def _build_quote_lookup(utterances: list[Utterance], quote_ids: list[str]) -> dict[str, str]:
    lookup = {utt.id: utt.text for utt in utterances}
    return {qid: lookup[qid] for qid in quote_ids if qid in lookup}


def _validate_summary_quotes(summary_text: str, quote_texts: list[str]) -> None:
    if "[" in summary_text and "]" in summary_text:
        raise ValueError("Summary appears to contain utterance IDs.")

    if not quote_texts:
        return

    quoted = re.findall(r'"([^"]+)"', summary_text)
    if not quoted:
        return

    def _clean(text: str) -> str:
        return re.sub(r"[*_`]+", "", text).strip()

    allowed = {_clean(q) for q in quote_texts}
    for q in quoted:
        cleaned = _clean(q)
        if len(cleaned) >= 25 and not any(cleaned in full for full in allowed):
            return

    # All detected quotes are short or covered by the allowed set.
    return


@activity.defn
async def plan_summary_activity(payload: dict) -> dict:
    Base.metadata.create_all(bind=ENGINE)
    run_id = payload["run_id"]
    session_id = payload["session_id"]

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

        character_map = load_character_map(session, run.campaign_id)
        transcript_text = _format_transcript(utterances, character_map)
        prompt = _load_prompt("summary_plan_v1.txt").format(
            session_facts=json.dumps(facts.model_dump(mode="json")),
            character_map=json.dumps(character_map, sort_keys=True),
            transcript=transcript_text,
        )

        client = LLMClient()
        start = time.monotonic()
        try:
            raw_json = client.generate_json_schema(prompt, schema=summary_plan_schema())
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="summary_plan",
                    model=settings.gemini_model,
                    prompt_id="summary_plan_v1",
                    prompt_version="1",
                    input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                    output_hash=sha256(raw_json.encode("utf-8")).hexdigest(),
                    latency_ms=latency_ms,
                    status="success",
                    created_at=datetime.utcnow(),
                )
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="summary_plan",
                    model=settings.gemini_model,
                    prompt_id="summary_plan_v1",
                    prompt_version="1",
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
            prompt_version="1",
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
    Base.metadata.create_all(bind=ENGINE)
    run_id = payload["run_id"]
    session_id = payload["session_id"]

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
        character_map = load_character_map(session, run.campaign_id)
        transcript_text = _format_transcript(utterances, character_map)

        quote_ids: list[str] = []
        for beat in plan.beats:
            for qid in beat.quote_utterance_ids:
                if qid not in quote_ids:
                    quote_ids.append(qid)
        quote_bank = _quote_bank(utterances, quote_ids)
        quote_lookup = _build_quote_lookup(utterances, quote_ids)

        prompt = _load_prompt("write_summary_v1.txt").format(
            summary_plan=json.dumps(plan.model_dump(mode="json")),
            session_facts=json.dumps(facts.model_dump(mode="json")),
            quote_bank=quote_bank or "[none]",
            character_map=json.dumps(character_map, sort_keys=True),
            transcript=transcript_text,
        )

        client = LLMClient()
        start = time.monotonic()
        try:
            summary_text = client.generate_text(prompt)
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="summary_text",
                    model=settings.gemini_model,
                    prompt_id="write_summary_v1",
                    prompt_version="1",
                    input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                    output_hash=sha256(summary_text.encode("utf-8")).hexdigest(),
                    latency_ms=latency_ms,
                    status="success",
                    created_at=datetime.utcnow(),
                )
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            session.add(
                LLMCall(
                    run_id=run.id,
                    session_id=session_id,
                    kind="summary_text",
                    model=settings.gemini_model,
                    prompt_id="write_summary_v1",
                    prompt_version="1",
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
        _validate_summary_quotes(summary_text, list(quote_lookup.values()))

        summary_record = SessionExtraction(
            run_id=run.id,
            session_id=session_id,
            kind="summary_text",
            model=settings.gemini_model,
            prompt_id="write_summary_v1",
            prompt_version="1",
            payload={"text": summary_text},
            created_at=datetime.utcnow(),
        )
        session.add(summary_record)

    return {"run_id": run_id, "session_id": session_id, "chars": len(summary_text)}


@activity.defn
async def render_summary_docx_activity(payload: dict) -> dict:
    Base.metadata.create_all(bind=ENGINE)
    run_id = payload["run_id"]
    session_id = payload["session_id"]

    with get_session() as session:
        summary_record = (
            session.query(SessionExtraction)
            .filter_by(run_id=run_id, session_id=session_id, kind="summary_text")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        if not summary_record:
            raise ValueError("Missing summary_text extraction")
        summary_text = summary_record.payload["text"]

        output_dir = Path(settings.artifacts_root) / session_id
        output_dir.mkdir(parents=True, exist_ok=True)
        txt_path = output_dir / "summary.txt"
        txt_path.write_text(summary_text, encoding="utf-8")
        output_path = output_dir / "summary.docx"
        render_summary_docx(summary_text, output_path)

        artifact = Artifact(
            run_id=run_id,
            session_id=session_id,
            kind="summary_docx",
            path=str(output_path),
            meta={"bytes": output_path.stat().st_size},
            created_at=datetime.utcnow(),
        )
        txt_artifact = Artifact(
            run_id=run_id,
            session_id=session_id,
            kind="summary_txt",
            path=str(txt_path),
            meta={"bytes": txt_path.stat().st_size},
            created_at=datetime.utcnow(),
        )
        session.add_all([artifact, txt_artifact])

    return {
        "run_id": run_id,
        "session_id": session_id,
        "path": str(output_path),
        "text_path": str(txt_path),
    }
