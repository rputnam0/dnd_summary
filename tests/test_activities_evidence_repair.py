from __future__ import annotations

import asyncio

from dnd_summary.activities.evidence_repair import repair_evidence_activity
from dnd_summary.models import SessionExtraction
from dnd_summary.schemas import EvidenceSpan, Mention, SessionFacts
from tests.factories import create_campaign, create_participant, create_run, create_session, create_utterance


def test_repair_evidence_activity_fills_missing_spans(db_session, settings_overrides):
    settings_overrides(evidence_repair_enabled=True, evidence_repair_missing_spans_threshold=1)
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign, display_name="DM")
    utterance = create_utterance(
        db_session,
        session_obj=session_obj,
        participant=participant,
        start_ms=0,
        end_ms=1000,
        text="Goblin attacks the party.",
    )
    facts = SessionFacts(
        mentions=[
            Mention(
                text="Goblin",
                entity_type="monster",
                evidence=[EvidenceSpan(utterance_id=utterance.id)],
            )
        ]
    )
    db_session.add(
        SessionExtraction(
            run_id=run.id,
            session_id=session_obj.id,
            kind="session_facts",
            model="system",
            prompt_id="extract_session_facts_v1",
            prompt_version="7",
            payload=facts.model_dump(mode="json"),
        )
    )
    db_session.commit()

    asyncio.run(repair_evidence_activity({"run_id": run.id, "session_id": session_obj.id}))

    db_session.expire_all()
    latest = (
        db_session.query(SessionExtraction)
        .filter_by(run_id=run.id, session_id=session_obj.id, kind="session_facts")
        .order_by(SessionExtraction.created_at.desc())
        .first()
    )
    repaired = latest.payload["mentions"][0]["evidence"][0]
    assert repaired["char_start"] == 0
    assert repaired["char_end"] == len("Goblin attacks the party.")
