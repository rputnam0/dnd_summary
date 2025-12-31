from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_

from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.llm import LLMClient
from dnd_summary.models import (
    Artifact,
    Campaign,
    Entity,
    EntityAlias,
    Event,
    Quote,
    Run,
    Scene,
    Session,
    SessionExtraction,
    Thread,
    ThreadUpdate,
    EntityMention,
    Mention,
    Utterance,
)
from dnd_summary.schema_genai import semantic_search_schema


app = FastAPI(title="DND Summary API", version="0.0.0")

UI_ROOT = Path(__file__).resolve().parent / "ui"
if UI_ROOT.exists():
    app.mount("/ui", StaticFiles(directory=UI_ROOT, html=True), name="ui")


@app.get("/", include_in_schema=False)
def ui_index() -> HTMLResponse:
    if UI_ROOT.exists():
        return RedirectResponse("/ui/")
    return HTMLResponse("<h1>DND Summary API</h1>")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> FileResponse:
    with get_session() as session:
        artifact = session.query(Artifact).filter_by(id=artifact_id).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        base = Path(settings.artifacts_root).resolve()
        artifact_path = Path(artifact.path)
        if not artifact_path.is_absolute():
            artifact_path = base / artifact.path
        artifact_path = artifact_path.resolve()
        if base != artifact_path and base not in artifact_path.parents:
            raise HTTPException(status_code=400, detail="Invalid artifact path")
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Artifact file missing")
        return FileResponse(artifact_path, filename=artifact_path.name)


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
        payload = []
        for s in sessions:
            latest_run = (
                session.query(Run)
                .filter_by(session_id=s.id)
                .order_by(Run.created_at.desc())
                .first()
            )
            payload.append(
                {
                    "id": s.id,
                    "slug": s.slug,
                    "session_number": s.session_number,
                    "title": s.title,
                    "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
                    "latest_run_id": latest_run.id if latest_run else None,
                    "latest_run_status": latest_run.status if latest_run else None,
                    "latest_run_created_at": (
                        latest_run.created_at.isoformat() if latest_run else None
                    ),
                }
            )
        return payload


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


@app.get("/entities/{entity_id}")
def get_entity(entity_id: str) -> dict:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        aliases = (
            session.query(EntityAlias)
            .filter_by(entity_id=entity.id)
            .order_by(EntityAlias.alias.asc())
            .all()
        )
        return {
            "id": entity.id,
            "name": entity.canonical_name,
            "type": entity.entity_type,
            "description": entity.description,
            "aliases": [alias.alias for alias in aliases],
        }


@app.get("/entities/{entity_id}/mentions")
def list_entity_mentions(
    entity_id: str,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        run_ids = _resolve_entity_run_ids(session, entity, session_id, run_id)
        query = (
            session.query(Mention)
            .join(EntityMention, EntityMention.mention_id == Mention.id)
            .filter(EntityMention.entity_id == entity.id)
            .filter(Mention.run_id.in_(run_ids))
        )
        if session_id:
            query = query.filter(Mention.session_id == session_id)
        mentions = query.order_by(Mention.created_at.asc()).all()
        return [
            {
                "id": mention.id,
                "session_id": mention.session_id,
                "run_id": mention.run_id,
                "text": mention.text,
                "entity_type": mention.entity_type,
                "description": mention.description,
                "evidence": mention.evidence,
                "confidence": mention.confidence,
            }
            for mention in mentions
        ]


@app.get("/entities/{entity_id}/events")
def list_entity_events(
    entity_id: str,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        run_ids = _resolve_entity_run_ids(session, entity, session_id, run_id)
        query = session.query(Event).filter(Event.run_id.in_(run_ids))
        if session_id:
            query = query.filter(Event.session_id == session_id)
        events = query.order_by(Event.start_ms.asc()).all()
        names = _entity_name_variants(session, entity)
        matched = []
        for event in events:
            entities = event.entities or []
            if any(_name_matches(candidate, names) for candidate in entities):
                matched.append(event)
        return [
            {
                "id": event.id,
                "session_id": event.session_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "summary": event.summary,
                "start_ms": event.start_ms,
                "end_ms": event.end_ms,
                "entities": event.entities,
                "evidence": event.evidence,
                "confidence": event.confidence,
            }
            for event in matched
        ]


@app.get("/entities/{entity_id}/quotes")
def list_entity_quotes(
    entity_id: str,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        run_ids = _resolve_entity_run_ids(session, entity, session_id, run_id)
        mentions = (
            session.query(Mention)
            .join(EntityMention, EntityMention.mention_id == Mention.id)
            .filter(EntityMention.entity_id == entity.id)
            .filter(Mention.run_id.in_(run_ids))
            .all()
        )
        utterance_ids = set()
        for mention in mentions:
            for ev in mention.evidence or []:
                utt_id = ev.get("utterance_id")
                if utt_id:
                    utterance_ids.add(utt_id)
        if not utterance_ids:
            return []
        query = session.query(Quote).filter(
            Quote.run_id.in_(run_ids), Quote.utterance_id.in_(sorted(utterance_ids))
        )
        if session_id:
            query = query.filter(Quote.session_id == session_id)
        quotes = query.all()
        utterance_lookup = _utterance_lookup(
            session,
            {quote.session_id for quote in quotes},
        )
        return [
            {
                "id": q.id,
                "session_id": q.session_id,
                "run_id": q.run_id,
                "utterance_id": q.utterance_id,
                "char_start": q.char_start,
                "char_end": q.char_end,
                "speaker": q.speaker,
                "note": q.note,
                "clean_text": q.clean_text,
                "display_text": _quote_display_text(q, utterance_lookup),
            }
            for q in quotes
        ]


@app.get("/sessions/{session_id}/entities")
def list_session_entities(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        entities = (
            session.query(Entity)
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .filter(EntityMention.session_id == session_id, EntityMention.run_id == resolved_run_id)
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
def list_mentions(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        mentions = (
            session.query(Mention, Entity)
            .outerjoin(EntityMention, EntityMention.mention_id == Mention.id)
            .outerjoin(Entity, Entity.id == EntityMention.entity_id)
            .filter(Mention.session_id == session_id, Mention.run_id == resolved_run_id)
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
def list_quotes(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        quotes = (
            session.query(Quote)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .all()
        )
        utterance_lookup = _utterance_lookup(session, {session_id})
        return [
            {
                "id": q.id,
                "utterance_id": q.utterance_id,
                "char_start": q.char_start,
                "char_end": q.char_end,
                "speaker": q.speaker,
                "note": q.note,
                "clean_text": q.clean_text,
                "display_text": _quote_display_text(q, utterance_lookup),
            }
            for q in quotes
        ]


@app.get("/campaigns/{campaign_slug}/search")
def search_campaign(
    campaign_slug: str,
    q: str = Query(..., min_length=2),
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        run_ids = None
        if not include_all_runs:
            run_ids = _latest_run_ids_for_campaign(session, campaign.id)

        dialect = session.bind.dialect.name if session.bind else "unknown"
        if dialect == "postgresql":
            mention_vector = func.to_tsvector(
                "english",
                Mention.text + " " + func.coalesce(Mention.description, ""),
            )
            mention_query = func.plainto_tsquery("english", q)
            mention_rank = func.ts_rank_cd(mention_vector, mention_query).label("rank")
            mentions_query = (
                session.query(Mention, mention_rank)
                .join(Session, Session.id == Mention.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(mention_vector.op("@@")(mention_query))
            )
            if session_id:
                mentions_query = mentions_query.filter(Mention.session_id == session_id)
            if run_ids is not None:
                mentions_query = mentions_query.filter(Mention.run_id.in_(run_ids))
            mentions = mentions_query.order_by(mention_rank.desc()).limit(50).all()

            utterance_vector = func.to_tsvector("english", Utterance.text)
            utterance_query = func.plainto_tsquery("english", q)
            utterance_rank = func.ts_rank_cd(utterance_vector, utterance_query).label("rank")
            utterances_query = (
                session.query(Utterance, utterance_rank)
                .join(Session, Session.id == Utterance.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(utterance_vector.op("@@")(utterance_query))
            )
            if session_id:
                utterances_query = utterances_query.filter(Utterance.session_id == session_id)
            utterances = utterances_query.order_by(utterance_rank.desc()).limit(50).all()
        else:
            like = f"%{q.lower()}%"
            mentions_query = (
                session.query(Mention)
                .join(Session, Session.id == Mention.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(
                    or_(
                        func.lower(Mention.text).like(like),
                        func.lower(func.coalesce(Mention.description, "")).like(like),
                    )
                )
            )
            if session_id:
                mentions_query = mentions_query.filter(Mention.session_id == session_id)
            if run_ids is not None:
                mentions_query = mentions_query.filter(Mention.run_id.in_(run_ids))
            mentions_raw = mentions_query.limit(50).all()

            utterances_query = (
                session.query(Utterance)
                .join(Session, Session.id == Utterance.session_id)
                .filter(Session.campaign_id == campaign.id)
                .filter(func.lower(Utterance.text).like(like))
            )
            if session_id:
                utterances_query = utterances_query.filter(Utterance.session_id == session_id)
            utterances_raw = utterances_query.limit(50).all()
            mentions = [
                (
                    m,
                    _simple_score(f"{m.text} {m.description or ''}", q),
                )
                for m in mentions_raw
            ]
            utterances = [
                (
                    u,
                    _simple_score(u.text, q),
                )
                for u in utterances_raw
            ]
            mentions.sort(key=lambda item: item[1], reverse=True)
            utterances.sort(key=lambda item: item[1], reverse=True)

        return {
            "mentions": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "text": m.text,
                    "entity_type": m.entity_type,
                    "description": m.description,
                    "evidence": m.evidence,
                    "score": float(rank) if rank is not None else None,
                }
                for m, rank in mentions
            ],
            "utterances": [
                {
                    "id": u.id,
                    "session_id": u.session_id,
                    "participant_id": u.participant_id,
                    "start_ms": u.start_ms,
                    "end_ms": u.end_ms,
                    "text": u.text,
                    "score": float(rank) if rank is not None else None,
                }
                for u, rank in utterances
            ],
        }


@app.get("/campaigns/{campaign_slug}/semantic_search")
def semantic_search_campaign(
    campaign_slug: str,
    q: str = Query(..., min_length=2),
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        run_ids = None
        if not include_all_runs:
            run_ids = _latest_run_ids_for_campaign(session, campaign.id)

        terms = _semantic_terms(q)
        likes = [f"%{term}%" for term in terms]

        mention_filters = [
            or_(
                func.lower(Mention.text).like(like),
                func.lower(func.coalesce(Mention.description, "")).like(like),
            )
            for like in likes
        ]
        mention_query = (
            session.query(Mention)
            .join(Session, Session.id == Mention.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            mention_query = mention_query.filter(Mention.session_id == session_id)
        if run_ids is not None:
            mention_query = mention_query.filter(Mention.run_id.in_(run_ids))
        if mention_filters:
            mention_query = mention_query.filter(or_(*mention_filters))
        mentions_raw = mention_query.limit(80).all()

        event_filters = [func.lower(Event.summary).like(like) for like in likes]
        event_query = (
            session.query(Event)
            .join(Session, Session.id == Event.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            event_query = event_query.filter(Event.session_id == session_id)
        if run_ids is not None:
            event_query = event_query.filter(Event.run_id.in_(run_ids))
        if event_filters:
            event_query = event_query.filter(or_(*event_filters))
        events_raw = event_query.limit(80).all()

        scene_filters = [
            or_(
                func.lower(Scene.summary).like(like),
                func.lower(func.coalesce(Scene.title, "")).like(like),
            )
            for like in likes
        ]
        scene_query = (
            session.query(Scene)
            .join(Session, Session.id == Scene.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            scene_query = scene_query.filter(Scene.session_id == session_id)
        if run_ids is not None:
            scene_query = scene_query.filter(Scene.run_id.in_(run_ids))
        if scene_filters:
            scene_query = scene_query.filter(or_(*scene_filters))
        scenes_raw = scene_query.limit(60).all()

        thread_filters = [
            or_(
                func.lower(Thread.title).like(like),
                func.lower(func.coalesce(Thread.summary, "")).like(like),
            )
            for like in likes
        ]
        thread_query = (
            session.query(Thread)
            .join(Session, Session.id == Thread.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            thread_query = thread_query.filter(Thread.session_id == session_id)
        if run_ids is not None:
            thread_query = thread_query.filter(Thread.run_id.in_(run_ids))
        if thread_filters:
            thread_query = thread_query.filter(or_(*thread_filters))
        threads_raw = thread_query.limit(40).all()

        update_filters = [func.lower(ThreadUpdate.note).like(like) for like in likes]
        update_query = (
            session.query(ThreadUpdate)
            .join(Thread, Thread.id == ThreadUpdate.thread_id)
            .join(Session, Session.id == ThreadUpdate.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            update_query = update_query.filter(ThreadUpdate.session_id == session_id)
        if run_ids is not None:
            update_query = update_query.filter(ThreadUpdate.run_id.in_(run_ids))
        if update_filters:
            update_query = update_query.filter(or_(*update_filters))
        updates_raw = update_query.limit(60).all()

        quote_filters = [
            or_(
                func.lower(func.coalesce(Quote.clean_text, "")).like(like),
                func.lower(func.coalesce(Quote.note, "")).like(like),
                func.lower(func.coalesce(Quote.speaker, "")).like(like),
            )
            for like in likes
        ]
        quote_query = (
            session.query(Quote)
            .join(Session, Session.id == Quote.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            quote_query = quote_query.filter(Quote.session_id == session_id)
        if run_ids is not None:
            quote_query = quote_query.filter(Quote.run_id.in_(run_ids))
        if quote_filters:
            quote_query = quote_query.filter(or_(*quote_filters))
        quotes_raw = quote_query.limit(60).all()

        utterance_filters = [func.lower(Utterance.text).like(like) for like in likes]
        utterance_query = (
            session.query(Utterance)
            .join(Session, Session.id == Utterance.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if session_id:
            utterance_query = utterance_query.filter(Utterance.session_id == session_id)
        if utterance_filters:
            utterance_query = utterance_query.filter(or_(*utterance_filters))
        utterances_raw = utterance_query.limit(80).all()

        utterance_lookup = _utterance_lookup(session, {u.session_id for u in quotes_raw})

        mentions = [
            {
                "id": m.id,
                "session_id": m.session_id,
                "text": m.text,
                "entity_type": m.entity_type,
                "description": m.description,
                "evidence": m.evidence,
                "score": _score_terms(f"{m.text} {m.description or ''}", terms),
            }
            for m in mentions_raw
        ]
        events = [
            {
                "id": e.id,
                "session_id": e.session_id,
                "event_type": e.event_type,
                "summary": e.summary,
                "start_ms": e.start_ms,
                "end_ms": e.end_ms,
                "entities": e.entities,
                "evidence": e.evidence,
                "score": _score_terms(e.summary, terms),
            }
            for e in events_raw
        ]
        scenes = [
            {
                "id": s.id,
                "session_id": s.session_id,
                "title": s.title,
                "summary": s.summary,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "location": s.location,
                "score": _score_terms(f"{s.title or ''} {s.summary}", terms),
            }
            for s in scenes_raw
        ]
        threads = [
            {
                "id": t.id,
                "session_id": t.session_id,
                "title": t.title,
                "summary": t.summary,
                "status": t.status,
                "score": _score_terms(f"{t.title} {t.summary or ''}", terms),
            }
            for t in threads_raw
        ]
        updates = [
            {
                "id": u.id,
                "session_id": u.session_id,
                "thread_id": u.thread_id,
                "note": u.note,
                "score": _score_terms(u.note or "", terms),
            }
            for u in updates_raw
        ]
        quotes = [
            {
                "id": q.id,
                "session_id": q.session_id,
                "speaker": q.speaker,
                "note": q.note,
                "clean_text": q.clean_text,
                "display_text": _quote_display_text(q, utterance_lookup),
                "score": _score_terms(f"{q.clean_text or ''} {q.note or ''}", terms),
            }
            for q in quotes_raw
        ]
        utterances = [
            {
                "id": u.id,
                "session_id": u.session_id,
                "participant_id": u.participant_id,
                "start_ms": u.start_ms,
                "end_ms": u.end_ms,
                "text": u.text,
                "score": _score_terms(u.text, terms),
            }
            for u in utterances_raw
        ]

        mentions.sort(key=lambda item: item["score"], reverse=True)
        events.sort(key=lambda item: item["score"], reverse=True)
        scenes.sort(key=lambda item: item["score"], reverse=True)
        threads.sort(key=lambda item: item["score"], reverse=True)
        updates.sort(key=lambda item: item["score"], reverse=True)
        quotes.sort(key=lambda item: item["score"], reverse=True)
        utterances.sort(key=lambda item: item["score"], reverse=True)

        return {
            "terms": terms,
            "mentions": mentions,
            "events": events,
            "threads": threads,
            "thread_updates": updates,
            "scenes": scenes,
            "quotes": quotes,
            "utterances": utterances,
        }


@app.get("/sessions/{session_id}/scenes")
def list_scenes(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        scenes = (
            session.query(Scene)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
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
def list_events(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        events = (
            session.query(Event)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
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
def list_threads(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        threads = (
            session.query(Thread)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(Thread.created_at.asc(), Thread.id.asc())
            .all()
        )
        thread_updates = (
            session.query(ThreadUpdate)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
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
                    "related_event_ids": update.related_event_ids,
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


def _utterance_lookup(session, session_ids: set[str]) -> dict[str, str]:
    if not session_ids:
        return {}
    utterances = (
        session.query(Utterance)
        .filter(Utterance.session_id.in_(sorted(session_ids)))
        .all()
    )
    return {utt.id: utt.text for utt in utterances}


def _quote_display_text(quote: Quote, utterance_lookup: dict[str, str]) -> str | None:
    if quote.clean_text:
        return quote.clean_text
    utterance_text = utterance_lookup.get(quote.utterance_id)
    if not utterance_text:
        return None
    if quote.char_start is None or quote.char_end is None:
        return utterance_text.strip()
    return utterance_text[quote.char_start : quote.char_end].strip()


def _resolve_run_id(session, session_id: str, run_id: str | None) -> str:
    if run_id:
        run = session.query(Run).filter_by(id=run_id, session_id=session_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found for session")
        return run.id
    runs = (
        session.query(Run)
        .filter_by(session_id=session_id)
        .order_by(Run.created_at.desc())
        .all()
    )
    if not runs:
        raise HTTPException(status_code=404, detail="Run not found for session")
    for run in runs:
        if run.status == "completed":
            return run.id
    return runs[0].id


def _latest_run_ids_for_campaign(session, campaign_id: str) -> set[str]:
    runs = (
        session.query(Run)
        .filter_by(campaign_id=campaign_id)
        .order_by(Run.created_at.desc())
        .all()
    )
    latest_by_session: dict[str, str] = {}
    fallback_by_session: dict[str, str] = {}
    for run in runs:
        if run.session_id not in fallback_by_session:
            fallback_by_session[run.session_id] = run.id
        if run.status != "completed":
            continue
        if run.session_id not in latest_by_session:
            latest_by_session[run.session_id] = run.id
    for session_id, run_id in fallback_by_session.items():
        if session_id not in latest_by_session:
            latest_by_session[session_id] = run_id
    return set(latest_by_session.values())


def _simple_score(text: str, query: str) -> float:
    hay = text.lower()
    needle = query.lower()
    if not hay or not needle:
        return 0.0
    return float(hay.count(needle))


def _score_terms(text: str, terms: list[str]) -> float:
    if not text:
        return 0.0
    return float(sum(_simple_score(text, term) for term in terms))


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(settings.prompts_root) / prompt_name
    return prompt_path.read_text(encoding="utf-8")


def _normalize_terms(terms: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for term in terms:
        if not term:
            continue
        normalized = re.sub(r"\\s+", " ", term.strip().lower())
        if len(normalized) < 2:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _semantic_terms(query: str) -> list[str]:
    try:
        prompt = _load_prompt("semantic_search_v1.txt").format(query=query)
        client = LLMClient()
        raw = client.generate_json_schema(prompt, schema=semantic_search_schema())
        payload = json.loads(raw)
        keywords = payload.get("keywords", [])
        entities = payload.get("entities", [])
        terms = [query] + keywords + entities
        return _normalize_terms(terms)
    except Exception:
        return _normalize_terms([query])


def _resolve_entity_run_ids(
    session,
    entity: Entity,
    session_id: str | None,
    run_id: str | None,
) -> set[str]:
    if run_id:
        run = session.query(Run).filter_by(id=run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if session_id and run.session_id != session_id:
            raise HTTPException(status_code=400, detail="Run does not match session")
        return {run.id}
    if session_id:
        return {_resolve_run_id(session, session_id, None)}
    return _latest_run_ids_for_campaign(session, entity.campaign_id)


def _entity_name_variants(session, entity: Entity) -> set[str]:
    aliases = (
        session.query(EntityAlias)
        .filter_by(entity_id=entity.id)
        .all()
    )
    names = {entity.canonical_name.lower()}
    names.update(alias.alias.lower() for alias in aliases)
    return names


def _name_matches(candidate: str, names: set[str]) -> bool:
    cand = candidate.strip().lower()
    if not cand:
        return False
    for name in names:
        if cand == name or cand in name or name in cand:
            return True
    return False


@app.get("/threads/{thread_id}/mentions")
def list_thread_mentions(thread_id: str) -> list[dict]:
    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        updates = session.query(ThreadUpdate).filter_by(thread_id=thread_id).all()

        utterance_ids = set()
        utterance_ids |= _utterance_ids_from_evidence(thread.evidence)
        related_event_ids: list[str] = []
        for update in updates:
            utterance_ids |= _utterance_ids_from_evidence(update.evidence)
            related_event_ids.extend(update.related_event_ids or [])
        utterance_ids |= _thread_event_utterance_ids(session, thread, related_event_ids)

        mentions = (
            session.query(Mention)
            .filter_by(session_id=thread.session_id, run_id=thread.run_id)
            .all()
        )
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
        if results:
            return results

        tokens = _thread_title_tokens(thread.title)
        if not tokens:
            return results
        for mention in mentions:
            haystack = f"{mention.text} {mention.description or ''}".lower()
            if any(token in haystack for token in tokens):
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
        related_event_ids: list[str] = []
        for update in updates:
            utterance_ids |= _utterance_ids_from_evidence(update.evidence)
            related_event_ids.extend(update.related_event_ids or [])
        utterance_ids |= _thread_event_utterance_ids(session, thread, related_event_ids)

        if not utterance_ids:
            tokens = _thread_title_tokens(thread.title)
            if not tokens:
                return []
            utterances = (
                session.query(Utterance)
                .filter_by(session_id=thread.session_id)
                .all()
            )
            candidate_ids = [
                u.id
                for u in utterances
                if any(token in u.text.lower() for token in tokens)
            ]
            if not candidate_ids:
                return []
            utterance_ids = set(candidate_ids)

        quotes = (
            session.query(Quote)
            .filter(
                Quote.session_id == thread.session_id,
                Quote.run_id == thread.run_id,
            )
            .filter(Quote.utterance_id.in_(sorted(utterance_ids)))
            .all()
        )
        if not quotes:
            tokens = _thread_title_tokens(thread.title)
            if tokens:
                utterances = (
                    session.query(Utterance)
                    .filter_by(session_id=thread.session_id)
                    .all()
                )
                candidate_ids = [
                    u.id
                    for u in utterances
                    if any(token in u.text.lower() for token in tokens)
                ]
                if candidate_ids:
                    quotes = (
                        session.query(Quote)
                        .filter(
                            Quote.session_id == thread.session_id,
                            Quote.run_id == thread.run_id,
                        )
                        .filter(Quote.utterance_id.in_(sorted(set(candidate_ids))))
                        .all()
                    )
        utterance_lookup = _utterance_lookup(session, {thread.session_id})
        return [
            {
                "id": q.id,
                "utterance_id": q.utterance_id,
                "char_start": q.char_start,
                "char_end": q.char_end,
                "speaker": q.speaker,
                "note": q.note,
                "clean_text": q.clean_text,
                "display_text": _quote_display_text(q, utterance_lookup),
            }
            for q in quotes
        ]


@app.get("/sessions/{session_id}/artifacts")
def list_artifacts(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        artifacts = (
            session.query(Artifact)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .all()
        )
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
def get_summary(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        summary = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="summary_text")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        persist_metrics = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="persist_metrics")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        quality_report = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="quality_report")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found")
        return {"text": summary.payload.get("text", "")}


@app.get("/sessions/{session_id}/runs")
def list_runs(session_id: str) -> list[dict]:
    with get_session() as session:
        runs = (
            session.query(Run)
            .filter_by(session_id=session_id)
            .order_by(Run.created_at.desc())
            .all()
        )
        return [
            {
                "id": run.id,
                "transcript_hash": run.transcript_hash,
                "pipeline_version": run.pipeline_version,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ]


@app.get("/utterances")
def list_utterances(
    ids: Annotated[list[str] | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        if not ids and not session_id:
            raise HTTPException(
                status_code=400, detail="Provide ids or session_id to fetch utterances"
            )
        query = session.query(Utterance)
        if session_id:
            query = query.filter(Utterance.session_id == session_id)
        if ids:
            query = query.filter(Utterance.id.in_(ids))
        utterances = query.all()
        return [
            {
                "id": utt.id,
                "session_id": utt.session_id,
                "participant_id": utt.participant_id,
                "start_ms": utt.start_ms,
                "end_ms": utt.end_ms,
                "text": utt.text,
            }
            for utt in utterances
        ]


@app.get("/utterances/{utterance_id}")
def get_utterance(utterance_id: str) -> dict:
    with get_session() as session:
        utterance = session.query(Utterance).filter_by(id=utterance_id).first()
        if not utterance:
            raise HTTPException(status_code=404, detail="Utterance not found")
        return {
            "id": utterance.id,
            "session_id": utterance.session_id,
            "participant_id": utterance.participant_id,
            "start_ms": utterance.start_ms,
            "end_ms": utterance.end_ms,
            "text": utterance.text,
        }


@app.get("/campaigns/{campaign_slug}/threads")
def list_campaign_threads(
    campaign_slug: str,
    status: Annotated[str | None, Query()] = None,
    include_all_runs: Annotated[bool, Query()] = False,
) -> list[dict]:
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        run_ids = None
        if not include_all_runs:
            run_ids = _latest_run_ids_for_campaign(session, campaign.id)

        query = (
            session.query(Thread, Session)
            .join(Session, Session.id == Thread.session_id)
            .filter(Session.campaign_id == campaign.id)
        )
        if run_ids is not None:
            query = query.filter(Thread.run_id.in_(run_ids))
        if status:
            query = query.filter(Thread.status == status)
        threads = query.order_by(Session.session_number.asc().nulls_last(), Thread.created_at.asc()).all()

        updates = (
            session.query(ThreadUpdate)
            .join(Thread, Thread.id == ThreadUpdate.thread_id)
            .filter(Thread.session_id.in_([session.id for _, session in threads]))
        )
        if run_ids is not None:
            updates = updates.filter(ThreadUpdate.run_id.in_(run_ids))
        updates = updates.all()

        updates_by_thread: dict[str, list[ThreadUpdate]] = {}
        for update in updates:
            updates_by_thread.setdefault(update.thread_id, []).append(update)

        latest_by_title: dict[str, dict] = {}
        for thread, sess in threads:
            key = (thread.title or "").strip().lower()
            if not key:
                continue
            entry = {
                "id": thread.id,
                "title": thread.title,
                "kind": thread.kind,
                "status": thread.status,
                "summary": thread.summary,
                "session_id": thread.session_id,
                "session_slug": sess.slug,
                "session_number": sess.session_number,
                "created_at": thread.created_at.isoformat(),
                "updates": [
                    {
                        "id": update.id,
                        "note": update.note,
                        "update_type": update.update_type,
                        "created_at": update.created_at.isoformat(),
                    }
                    for update in updates_by_thread.get(thread.id, [])
                ],
            }
            existing = latest_by_title.get(key)
            if not existing:
                latest_by_title[key] = entry
                continue
            existing_number = existing.get("session_number") or 0
            current_number = sess.session_number or 0
            if current_number >= existing_number:
                latest_by_title[key] = entry

        return list(latest_by_title.values())


@app.get("/sessions/{session_id}/bundle")
def get_session_bundle(
    session_id: str,
    run_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        run = session.query(Run).filter_by(id=resolved_run_id).first()

        summary = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="summary_text")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )
        artifacts = (
            session.query(Artifact)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .all()
        )
        quotes = (
            session.query(Quote)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .all()
        )
        utterance_lookup = _utterance_lookup(session, {session_id})

        scenes = (
            session.query(Scene)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(Scene.start_ms.asc(), Scene.id.asc())
            .all()
        )
        events = (
            session.query(Event)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(Event.start_ms.asc(), Event.id.asc())
            .all()
        )
        threads = (
            session.query(Thread)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(Thread.created_at.asc(), Thread.id.asc())
            .all()
        )
        thread_updates = (
            session.query(ThreadUpdate)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
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
                    "related_event_ids": update.related_event_ids,
                    "created_at": update.created_at.isoformat(),
                }
            )

        entities = (
            session.query(Entity)
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .filter(
                EntityMention.session_id == session_id,
                EntityMention.run_id == resolved_run_id,
            )
            .order_by(Entity.entity_type.asc(), Entity.canonical_name.asc())
            .distinct()
            .all()
        )

        return {
            "session_id": session_id,
            "run_id": resolved_run_id,
            "run_status": run.status if run else None,
            "run_created_at": run.created_at.isoformat() if run else None,
            "summary": summary.payload.get("text", "") if summary else "",
            "metrics": persist_metrics.payload if persist_metrics else None,
            "quality": quality_report.payload if quality_report else None,
            "artifacts": [
                {
                    "id": a.id,
                    "kind": a.kind,
                    "path": a.path,
                    "meta": a.meta,
                }
                for a in artifacts
            ],
            "quotes": [
                {
                    "id": q.id,
                    "utterance_id": q.utterance_id,
                    "char_start": q.char_start,
                    "char_end": q.char_end,
                    "speaker": q.speaker,
                    "note": q.note,
                    "clean_text": q.clean_text,
                    "display_text": _quote_display_text(q, utterance_lookup),
                }
                for q in quotes
            ],
            "scenes": [
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
            ],
            "events": [
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
            ],
            "threads": [
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
            ],
            "entities": [
                {
                    "id": e.id,
                    "name": e.canonical_name,
                    "type": e.entity_type,
                    "description": e.description,
                }
                for e in entities
            ],
        }


def _thread_event_utterance_ids(
    session,
    thread: Thread,
    related_event_ids: list[str] | None = None,
) -> set[str]:
    ids: set[str] = set()
    if related_event_ids:
        events = session.query(Event).filter(Event.id.in_(related_event_ids)).all()
        for event in events:
            ids |= _utterance_ids_from_evidence(event.evidence)
        if ids:
            return ids

    events = (
        session.query(Event)
        .filter_by(session_id=thread.session_id, run_id=thread.run_id)
        .all()
    )
    tokens = _thread_title_tokens(thread.title)
    for event in events:
        summary = (event.summary or "").lower()
        if event.event_type == "thread_update" or any(token in summary for token in tokens):
            ids |= _utterance_ids_from_evidence(event.evidence)
    return ids


def _thread_title_tokens(title: str | None) -> list[str]:
    if not title:
        return []
    tokens = [token for token in re.split(r"\W+", title.lower()) if len(token) > 3]
    return tokens
