from __future__ import annotations

import asyncio

from dnd_summary.activities.persist import persist_session_facts_activity
from dnd_summary.models import Correction, SessionExtraction, Thread
from dnd_summary.schemas import EvidenceSpan, SessionFacts, ThreadCandidate, ThreadUpdate
from tests.factories import (
    create_campaign,
    create_campaign_thread,
    create_participant,
    create_run,
    create_session,
    create_utterance,
)


def test_persist_applies_thread_corrections(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utterance = create_utterance(
        db_session,
        session_obj=session_obj,
        participant=participant,
        text="We must find the relic.",
    )

    campaign_thread = create_campaign_thread(
        db_session,
        campaign=campaign,
        canonical_title="quest",
        status="active",
    )
    prior_thread = Thread(
        run_id=run.id,
        session_id=session_obj.id,
        campaign_thread_id=campaign_thread.id,
        title="Quest",
        kind="quest",
        status="active",
    )
    db_session.add(prior_thread)
    db_session.flush()

    db_session.add(
        Correction(
            campaign_id=campaign.id,
            session_id=None,
            target_type="thread",
            target_id=prior_thread.id,
            action="thread_status",
            payload={"status": "completed"},
            created_by="dm",
        )
    )

    evidence = [
        EvidenceSpan(
            utterance_id=utterance.id,
            char_start=0,
            char_end=4,
            kind="support",
        )
    ]
    facts = SessionFacts(
        threads=[
            ThreadCandidate(
                title="Quest",
                kind="quest",
                status="active",
                summary=None,
                evidence=evidence,
                updates=[
                    ThreadUpdate(
                        update_type="progress",
                        note="Discussed the relic.",
                        evidence=evidence,
                        related_event_indexes=[],
                    )
                ],
            )
        ]
    )
    extraction = SessionExtraction(
        run_id=run.id,
        session_id=session_obj.id,
        kind="session_facts",
        model="test",
        prompt_id="test",
        prompt_version="1",
        payload=facts.model_dump(mode="json"),
    )
    db_session.add(extraction)
    db_session.commit()

    asyncio.run(persist_session_facts_activity({"run_id": run.id, "session_id": session_obj.id}))

    persisted = (
        db_session.query(Thread)
        .filter(Thread.run_id == run.id, Thread.session_id == session_obj.id)
        .order_by(Thread.created_at.desc())
        .first()
    )
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.campaign_thread_id == campaign_thread.id
