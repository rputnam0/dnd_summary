from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import ENGINE, get_session
from dnd_summary.llm import LLMClient
from dnd_summary.models import Artifact, Base, Run, SessionExtraction, Utterance
from dnd_summary.render import render_summary_docx
from dnd_summary.schema_genai import summary_plan_schema
from dnd_summary.schemas import SessionFacts, SummaryPlan


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(settings.prompts_root) / prompt_name
    return prompt_path.read_text(encoding="utf-8")


def _format_transcript(utterances: list[Utterance]) -> str:
    lines = []
    for utt in utterances:
        lines.append(
            f"[{utt.id}] {utt.participant.display_name} {utt.start_ms}-{utt.end_ms} {utt.text}"
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

    allowed = set(quote_texts)
    invalid = [q for q in quoted if q not in allowed]
    if invalid:
        sample = invalid[0][:120]
        raise ValueError(f"Summary contains quote not in Quote Bank: {sample!r}")


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

        transcript_text = _format_transcript(utterances)
        prompt = _load_prompt("summary_plan_v1.txt").format(
            session_facts=json.dumps(facts.model_dump(mode="json")),
            transcript=transcript_text,
        )

        client = LLMClient()
        raw_json = client.generate_json_schema(prompt, schema=summary_plan_schema())
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
        transcript_text = _format_transcript(utterances)

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
            transcript=transcript_text,
        )

        client = LLMClient()
        summary_text = client.generate_text(prompt)
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
