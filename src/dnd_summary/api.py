from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import func, or_, text

from dnd_summary.db import get_session
from dnd_summary.models import (
    Artifact,
    Campaign,
    Entity,
    Event,
    Quote,
    Scene,
    Session,
    SessionExtraction,
    Thread,
    ThreadUpdate,
    EntityMention,
    Mention,
    Utterance,
)


app = FastAPI(title="DND Summary API", version="0.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/campaigns")
def list_campaigns() -> list[dict]:
    with get_session() as session:
        campaigns = session.query(Campaign).order_by(Campaign.slug.asc()).all()
        return [{"id": c.id, "slug": c.slug, "name": c.name} for c in campaigns]


@app.get("/campaigns/{campaign_slug}/sessions")
def list_sessions(campaign_slug: str) -> list[dict]:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        sessions = (
            session.query(Session)
            .filter_by(campaign_id=campaign.id)
            .order_by(Session.session_number.asc().nulls_last(), Session.slug.asc())
            .all()
        )
        return [
            {
                "id": s.id,
                "slug": s.slug,
                "session_number": s.session_number,
                "title": s.title,
                "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
            }
            for s in sessions
        ]


@app.get("/campaigns/{campaign_slug}/entities")
def list_entities(campaign_slug: str) -> list[dict]:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        entities = (
            session.query(Entity)
            .filter_by(campaign_id=campaign.id)
            .order_by(Entity.entity_type.asc(), Entity.canonical_name.asc())
            .all()
        )
        return [
            {
                "id": e.id,
                "name": e.canonical_name,
                "type": e.entity_type,
                "description": e.description,
            }
            for e in entities
        ]


@app.get("/sessions/{session_id}/entities")
def list_session_entities(session_id: str) -> list[dict]:
    with get_session() as session:
        entities = (
            session.query(Entity)
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .filter(EntityMention.session_id == session_id)
            .order_by(Entity.entity_type.asc(), Entity.canonical_name.asc())
            .distinct()
            .all()
        )
        return [
            {
                "id": e.id,
                "name": e.canonical_name,
                "type": e.entity_type,
                "description": e.description,
            }
            for e in entities
        ]


@app.get("/sessions/{session_id}/mentions")
def list_mentions(session_id: str) -> list[dict]:
    with get_session() as session:
        mentions = (
            session.query(Mention, Entity)
            .outerjoin(EntityMention, EntityMention.mention_id == Mention.id)
            .outerjoin(Entity, Entity.id == EntityMention.entity_id)
            .filter(Mention.session_id == session_id)
            .order_by(Mention.created_at.asc(), Mention.id.asc())
            .all()
        )
        return [
            {
                "id": mention.id,
                "text": mention.text,
                "entity_type": mention.entity_type,
                "description": mention.description,
                "evidence": mention.evidence,
                "confidence": mention.confidence,
                "entity_id": entity.id if entity else None,
                "entity_name": entity.canonical_name if entity else None,
                "entity_type_resolved": entity.entity_type if entity else None,
            }
            for mention, entity in mentions
        ]


@app.get("/sessions/{session_id}/quotes")
def list_quotes(session_id: str) -> list[dict]:
    with get_session() as session:
        quotes = session.query(Quote).filter_by(session_id=session_id).all()
        return [
            {
                "id": q.id,
                "utterance_id": q.utterance_id,
                "char_start": q.char_start,
                "char_end": q.char_end,
                "speaker": q.speaker,
                "note": q.note,
            }
            for q in quotes
        ]


@app.get("/campaigns/{campaign_slug}/search")
def search_campaign(
    campaign_slug: str,
    q: str = Query(..., min_length=2),
) -> dict:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        dialect = session.bind.dialect.name if session.bind else "unknown"
        if dialect == "postgresql":
            mentions = (
                session.query(Mention)
                .join(Session, Session.id == Mention.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(
                    text(
                        "to_tsvector('english', mentions.text || ' ' || "
                        "coalesce(mentions.description, '')) @@ plainto_tsquery(:q)"
                    )
                )
                .params(q=q)
                .limit(50)
                .all()
            )
            utterances = (
                session.query(Utterance)
                .join(Session, Session.id == Utterance.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(
                    text(
                        "to_tsvector('english', utterances.text) "
                        "@@ plainto_tsquery(:q)"
                    )
                )
                .params(q=q)
                .limit(50)
                .all()
            )
        else:
            like = f"%{q.lower()}%"
            mentions = (
                session.query(Mention)
                .join(Session, Session.id == Mention.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(
                    or_(
                        func.lower(Mention.text).like(like),
                        func.lower(func.coalesce(Mention.description, "")).like(like),
                    )
                )
                .limit(50)
                .all()
            )
            utterances = (
                session.query(Utterance)
                .join(Session, Session.id == Utterance.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(func.lower(Utterance.text).like(like))
                .limit(50)
                .all()
            )

        return {
            "mentions": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "text": m.text,
                    "entity_type": m.entity_type,
                    "description": m.description,
                    "evidence": m.evidence,
                }
                for m in mentions
            ],
            "utterances": [
                {
                    "id": u.id,
                    "session_id": u.session_id,
                    "participant_id": u.participant_id,
                    "start_ms": u.start_ms,
                    "end_ms": u.end_ms,
                    "text": u.text,
                }
                for u in utterances
            ],
        }


@app.get("/sessions/{session_id}/scenes")
def list_scenes(session_id: str) -> list[dict]:
    with get_session() as session:
        scenes = (
            session.query(Scene)
            .filter_by(session_id=session_id)
            .order_by(Scene.start_ms.asc(), Scene.id.asc())
            .all()
        )
        return [
            {
                "id": s.id,
                "title": s.title,
                "summary": s.summary,
                "location": s.location,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "participants": s.participants,
                "evidence": s.evidence,
            }
            for s in scenes
        ]


@app.get("/sessions/{session_id}/events")
def list_events(session_id: str) -> list[dict]:
    with get_session() as session:
        events = (
            session.query(Event)
            .filter_by(session_id=session_id)
            .order_by(Event.start_ms.asc(), Event.id.asc())
            .all()
        )
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "summary": e.summary,
                "start_ms": e.start_ms,
                "end_ms": e.end_ms,
                "entities": e.entities,
                "evidence": e.evidence,
                "confidence": e.confidence,
            }
            for e in events
        ]


@app.get("/sessions/{session_id}/threads")
def list_threads(session_id: str) -> list[dict]:
    with get_session() as session:
        threads = (
            session.query(Thread)
            .filter_by(session_id=session_id)
            .order_by(Thread.created_at.asc(), Thread.id.asc())
            .all()
        )
        thread_updates = (
            session.query(ThreadUpdate)
            .filter_by(session_id=session_id)
            .order_by(ThreadUpdate.created_at.asc(), ThreadUpdate.id.asc())
            .all()
        )
        updates_by_thread: dict[str, list[dict]] = {}
        for update in thread_updates:
            updates_by_thread.setdefault(update.thread_id, []).append(
                {
                    "id": update.id,
                    "update_type": update.update_type,
                    "note": update.note,
                    "evidence": update.evidence,
                    "created_at": update.created_at.isoformat(),
                }
            )
        return [
            {
                "id": t.id,
                "title": t.title,
                "kind": t.kind,
                "status": t.status,
                "summary": t.summary,
                "evidence": t.evidence,
                "confidence": t.confidence,
                "created_at": t.created_at.isoformat(),
                "updates": updates_by_thread.get(t.id, []),
            }
            for t in threads
        ]


def _utterance_ids_from_evidence(entries: list[dict] | None) -> set[str]:
    ids: set[str] = set()
    if not entries:
        return ids
    for entry in entries:
        utt_id = entry.get("utterance_id")
        if utt_id:
            ids.add(utt_id)
    return ids


@app.get("/threads/{thread_id}/mentions")
def list_thread_mentions(thread_id: str) -> list[dict]:
    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        updates = session.query(ThreadUpdate).filter_by(thread_id=thread_id).all()

        utterance_ids = set()
        utterance_ids |= _utterance_ids_from_evidence(thread.evidence)
        for update in updates:
            utterance_ids |= _utterance_ids_from_evidence(update.evidence)

        mentions = session.query(Mention).filter_by(session_id=thread.session_id).all()
        results = []
        for mention in mentions:
            evidence = mention.evidence or []
            if not any(ev.get("utterance_id") in utterance_ids for ev in evidence):
                continue
            results.append(
                {
                    "id": mention.id,
                    "text": mention.text,
                    "entity_type": mention.entity_type,
                    "description": mention.description,
                    "evidence": mention.evidence,
                    "confidence": mention.confidence,
                }
            )
        return results


@app.get("/threads/{thread_id}/quotes")
def list_thread_quotes(thread_id: str) -> list[dict]:
    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        updates = session.query(ThreadUpdate).filter_by(thread_id=thread_id).all()

        utterance_ids = set()
        utterance_ids |= _utterance_ids_from_evidence(thread.evidence)
        for update in updates:
            utterance_ids |= _utterance_ids_from_evidence(update.evidence)

        if not utterance_ids:
            return []

        quotes = (
            session.query(Quote)
            .filter(Quote.session_id == thread.session_id)
            .filter(Quote.utterance_id.in_(sorted(utterance_ids)))
            .all()
        )
        return [
            {
                "id": q.id,
                "utterance_id": q.utterance_id,
                "char_start": q.char_start,
                "char_end": q.char_end,
                "speaker": q.speaker,
                "note": q.note,
            }
            for q in quotes
        ]


@app.get("/sessions/{session_id}/artifacts")
def list_artifacts(session_id: str) -> list[dict]:
    with get_session() as session:
        artifacts = session.query(Artifact).filter_by(session_id=session_id).all()
        return [
            {
                "id": a.id,
                "kind": a.kind,
                "path": a.path,
                "meta": a.meta,
            }
            for a in artifacts
        ]


@app.get("/sessions/{session_id}/summary")
def get_summary(session_id: str) -> dict:
    with get_session() as session:
        summary = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, kind="summary_text")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found")
        return {"text": summary.payload.get("text", "")}
