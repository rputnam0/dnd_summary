from __future__ import annotations

from fastapi import FastAPI, HTTPException

from dnd_summary.db import get_session
from dnd_summary.models import Artifact, Campaign, Entity, Quote, Session, SessionExtraction


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
