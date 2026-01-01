from __future__ import annotations

from datetime import datetime

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.models import Run, SessionExtraction, Utterance
from dnd_summary.run_steps import run_step
from dnd_summary.schemas import SessionFacts


def _count_missing_spans(facts: SessionFacts) -> int:
    missing = 0
    for item in facts.mentions + facts.scenes + facts.events + facts.threads:
        for ev in item.evidence or []:
            if ev.char_start is None or ev.char_end is None:
                missing += 1
    for thread in facts.threads:
        for update in thread.updates:
            for ev in update.evidence or []:
                if ev.char_start is None or ev.char_end is None:
                    missing += 1
    return missing


def _repair_span(ev, utterance_lookup: dict[str, str]) -> bool:
    if ev.char_start is not None and ev.char_end is not None:
        return False
    if not ev.utterance_id:
        return False
    text = utterance_lookup.get(ev.utterance_id)
    if text is None:
        return False
    ev.char_start = 0
    ev.char_end = len(text)
    return True


def _repair_facts(facts: SessionFacts, utterance_lookup: dict[str, str]) -> int:
    repaired = 0
    for item in facts.mentions + facts.scenes + facts.events + facts.threads:
        for ev in item.evidence or []:
            repaired += 1 if _repair_span(ev, utterance_lookup) else 0
    for thread in facts.threads:
        for update in thread.updates:
            for ev in update.evidence or []:
                repaired += 1 if _repair_span(ev, utterance_lookup) else 0
    return repaired


@activity.defn
async def repair_evidence_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]

    if not settings.evidence_repair_enabled:
        return {"run_id": run_id, "session_id": session_id, "skipped": True}

    with run_step(run_id, session_id, "repair_evidence"):
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
            missing_spans = _count_missing_spans(facts)
            if missing_spans < settings.evidence_repair_missing_spans_threshold:
                return {
                    "run_id": run_id,
                    "session_id": session_id,
                    "skipped": True,
                    "missing_spans": missing_spans,
                }

            utterances = (
                session.query(Utterance)
                .filter_by(session_id=session_id)
                .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
                .all()
            )
            utterance_lookup = {utt.id: utt.text for utt in utterances}
            repaired = _repair_facts(facts, utterance_lookup)

            session.add(
                SessionExtraction(
                    run_id=run_id,
                    session_id=session_id,
                    kind="session_facts",
                    model="system",
                    prompt_id="evidence_repair_v1",
                    prompt_version="1",
                    payload=facts.model_dump(mode="json"),
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                SessionExtraction(
                    run_id=run_id,
                    session_id=session_id,
                    kind="evidence_repair_report",
                    model="system",
                    prompt_id="evidence_repair_v1",
                    prompt_version="1",
                    payload={
                        "missing_spans": missing_spans,
                        "repaired_spans": repaired,
                    },
                    created_at=datetime.utcnow(),
                )
            )

            return {
                "run_id": run_id,
                "session_id": session_id,
                "missing_spans": missing_spans,
                "repaired_spans": repaired,
                "skipped": repaired == 0,
            }
