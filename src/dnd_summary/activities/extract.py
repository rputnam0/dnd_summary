from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import ENGINE, get_session
from dnd_summary.llm import LLMClient
from dnd_summary.mappings import load_character_map
from dnd_summary.models import Base, Run, SessionExtraction, Utterance
from dnd_summary.schema_genai import session_facts_schema
from dnd_summary.schemas import SessionFacts


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

        prompt_template = _load_prompt("extract_session_facts_v1.txt")
        prompt = prompt_template.format(
            transcript=transcript_text,
            character_map=json.dumps(character_map, sort_keys=True),
        )

        client = LLMClient()
        raw_json = client.generate_json_schema(prompt, schema=session_facts_schema())
        payload_json = json.loads(raw_json)
        facts = SessionFacts.model_validate(payload_json)

        extraction = SessionExtraction(
            run_id=run.id,
            session_id=session_id,
            kind="session_facts",
            model=settings.gemini_model,
            prompt_id="extract_session_facts_v1",
            prompt_version="1",
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
