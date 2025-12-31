from __future__ import annotations

from temporalio import activity

from dnd_summary.db import ENGINE, get_session
from dnd_summary.models import (
    Base,
    Event,
    Mention,
    Quote,
    Scene,
    SessionExtraction,
    Thread,
    ThreadUpdate,
)
from dnd_summary.schemas import SessionFacts


@activity.defn
async def persist_session_facts_activity(payload: dict) -> dict:
    Base.metadata.create_all(bind=ENGINE)
    run_id = payload["run_id"]
    session_id = payload["session_id"]

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

        for model in (Mention, Scene, Event, Quote, Thread, ThreadUpdate):
            session.query(model).filter_by(run_id=run_id, session_id=session_id).delete()

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
            )
            for quote in facts.quotes
        ]

        session.add_all(mentions)
        session.add_all(scenes)
        session.add_all(events)
        session.add_all(quotes)
        session.flush()

        thread_rows = []
        thread_updates = []
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
                thread_updates.append(
                    ThreadUpdate(
                        run_id=run_id,
                        session_id=session_id,
                        thread_id=thread_row.id,
                        update_type=update.update_type,
                        note=update.note,
                        evidence=[e.model_dump(mode="json") for e in update.evidence],
                    )
                )

        if thread_updates:
            session.add_all(thread_updates)

    return {
        "run_id": run_id,
        "session_id": session_id,
        "mentions": len(facts.mentions),
        "scenes": len(facts.scenes),
        "events": len(facts.events),
        "threads": len(facts.threads),
        "quotes": len(facts.quotes),
    }

