from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
import tempfile
import zipfile

from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.embeddings import cosine_similarity, embed_texts
from dnd_summary.llm import LLMClient
from dnd_summary.mappings import load_character_map
from dnd_summary.rerank import RerankCandidate, rerank
from dnd_summary.models import (
    Artifact,
    Campaign,
    CampaignMembership,
    CharacterSheetSnapshot,
    Correction,
    Bookmark,
    DiceRoll,
    Embedding,
    Entity,
    EntityAlias,
    EntityMention,
    Event,
    Quote,
    Run,
    RunStep,
    Scene,
    Session,
    SessionExtraction,
    SpoilerTag,
    Thread,
    ThreadUpdate,
    EntityMention,
    Mention,
    LLMCall,
    Note,
    Utterance,
    User,
)
from dnd_summary.schema_genai import ask_campaign_schema, semantic_search_schema
from dnd_summary.transcript_format import format_transcript
from dnd_summary.workflows.process_session import ProcessSessionWorkflow


app = FastAPI(title="DND Summary API", version="0.0.0")

UI_ROOT = Path(__file__).resolve().parent / "ui"
if UI_ROOT.exists():
    app.mount("/ui", StaticFiles(directory=UI_ROOT, html=True), name="ui")


def _validate_slug(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} slug")


def _load_corrections(
    session,
    campaign_id: str,
    session_id: str | None = None,
    target_type: str | None = None,
) -> list[Correction]:
    query = session.query(Correction).filter(Correction.campaign_id == campaign_id)
    if session_id is not None:
        query = query.filter(or_(Correction.session_id.is_(None), Correction.session_id == session_id))
    else:
        query = query.filter(Correction.session_id.is_(None))
    if target_type:
        query = query.filter(Correction.target_type == target_type)
    return query.order_by(Correction.created_at.asc(), Correction.id.asc()).all()


def _entity_correction_maps(corrections: list[Correction]) -> tuple[set[str], dict[str, str], dict[str, str]]:
    hidden_ids: set[str] = set()
    merge_map: dict[str, str] = {}
    rename_map: dict[str, str] = {}
    for correction in corrections:
        payload = correction.payload or {}
        if correction.action in ("hide", "entity_hide"):
            hidden_ids.add(correction.target_id)
            continue
        if correction.action in ("merge", "entity_merge"):
            merge_target = payload.get("into_id") or payload.get("target_id")
            if merge_target:
                merge_map[correction.target_id] = merge_target
            hidden_ids.add(correction.target_id)
            continue
        if correction.action in ("rename", "entity_rename"):
            new_name = payload.get("name") or payload.get("canonical_name")
            if new_name:
                rename_map[correction.target_id] = new_name
    return hidden_ids, merge_map, rename_map


def _entity_alias_changes(
    corrections: list[Correction],
    entity_id: str,
) -> tuple[set[str], set[str]]:
    adds: set[str] = set()
    removes: set[str] = set()
    for correction in corrections:
        if correction.target_id != entity_id:
            continue
        payload = correction.payload or {}
        if correction.action in ("alias_add", "entity_alias_add"):
            alias = payload.get("alias")
            if alias:
                adds.add(alias)
        if correction.action in ("alias_remove", "entity_alias_remove"):
            alias = payload.get("alias")
            if alias:
                removes.add(alias)
    return adds, removes


def _thread_correction_maps(
    corrections: list[Correction],
) -> tuple[set[str], dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    hidden_ids: set[str] = set()
    merge_map: dict[str, str] = {}
    title_map: dict[str, str] = {}
    status_map: dict[str, str] = {}
    summary_map: dict[str, str] = {}
    for correction in corrections:
        payload = correction.payload or {}
        if correction.action in ("hide", "thread_hide"):
            hidden_ids.add(correction.target_id)
            continue
        if correction.action in ("merge", "thread_merge"):
            merge_target = payload.get("into_id") or payload.get("target_id")
            if merge_target:
                merge_map[correction.target_id] = merge_target
            hidden_ids.add(correction.target_id)
            continue
        if correction.action in ("rename", "thread_rename", "thread_title", "title_update"):
            new_title = payload.get("title") or payload.get("name")
            if new_title:
                title_map[correction.target_id] = new_title
            continue
        if correction.action in ("status_update", "thread_status"):
            new_status = payload.get("status")
            if new_status:
                status_map[correction.target_id] = new_status
            continue
        if correction.action in ("summary_update", "thread_summary"):
            if "summary" in payload:
                summary_map[correction.target_id] = payload.get("summary")
    return hidden_ids, merge_map, title_map, status_map, summary_map


def _redacted_ids(corrections: list[Correction]) -> set[str]:
    redacted: set[str] = set()
    for correction in corrections:
        if correction.action in ("redact", "redaction", "redact_text"):
            redacted.add(correction.target_id)
    return redacted


def _auth_user_id(request: Request) -> str | None:
    if not settings.auth_enabled:
        return None
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")
    return user_id


def _require_campaign_role(
    session,
    campaign_id: str,
    user_id: str,
    role: str | None = None,
) -> CampaignMembership:
    membership = (
        session.query(CampaignMembership)
        .filter_by(campaign_id=campaign_id, user_id=user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Missing campaign access")
    if role and membership.role != role:
        raise HTTPException(status_code=403, detail="Insufficient campaign role")
    return membership


def _require_dm(session, campaign_id: str, request: Request) -> None:
    user_id = _auth_user_id(request)
    if not user_id:
        return
    _require_campaign_role(session, campaign_id, user_id, "dm")


def _require_campaign_access(session, campaign_id: str, request: Request) -> None:
    user_id = _auth_user_id(request)
    if not user_id:
        return
    _require_campaign_role(session, campaign_id, user_id)


def _campaign_for_slug(session, campaign_slug: str, request: Request) -> Campaign:
    campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _require_campaign_access(session, campaign.id, request)
    return campaign


def _session_for_id(session, session_id: str, request: Request) -> Session:
    session_obj = session.query(Session).filter_by(id=session_id).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_campaign_access(session, session_obj.campaign_id, request)
    return session_obj


def _campaign_role(session, campaign_id: str, request: Request) -> str:
    if not settings.auth_enabled:
        return "dm"
    user_id = _auth_user_id(request)
    membership = (
        session.query(CampaignMembership)
        .filter_by(campaign_id=campaign_id, user_id=user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Missing campaign access")
    return membership.role


def _spoiler_cutoff(
    session,
    campaign_id: str,
    request: Request,
    session_id: str | None = None,
) -> int | None:
    role = _campaign_role(session, campaign_id, request)
    if role == "dm":
        return None
    if session_id:
        session_obj = session.query(Session).filter_by(id=session_id).first()
        if session_obj and session_obj.session_number:
            return session_obj.session_number
    latest_number = (
        session.query(Session.session_number)
        .filter(Session.campaign_id == campaign_id, Session.session_number.is_not(None))
        .order_by(Session.session_number.desc())
        .limit(1)
        .scalar()
    )
    return latest_number


def _spoiler_map(session, campaign_id: str) -> dict[tuple[str, str], int]:
    tags = session.query(SpoilerTag).filter_by(campaign_id=campaign_id).all()
    return {(tag.target_type, tag.target_id): tag.reveal_session_number for tag in tags}


@app.get("/", include_in_schema=False)
def ui_index() -> HTMLResponse:
    if UI_ROOT.exists():
        return RedirectResponse("/ui/")
    return HTMLResponse("<h1>DND Summary API</h1>")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str, request: Request) -> FileResponse:
    with get_session() as session:
        artifact = session.query(Artifact).filter_by(id=artifact_id).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        session_obj = session.query(Session).filter_by(id=artifact.session_id).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_campaign_access(session, session_obj.campaign_id, request)
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
def list_campaigns(request: Request) -> list[dict]:
    with get_session() as session:
        user_id = _auth_user_id(request)
        if user_id:
            campaigns = (
                session.query(Campaign)
                .join(CampaignMembership, CampaignMembership.campaign_id == Campaign.id)
                .filter(CampaignMembership.user_id == user_id)
                .order_by(Campaign.slug.asc())
                .all()
            )
        else:
            campaigns = session.query(Campaign).order_by(Campaign.slug.asc()).all()
        return [{"id": c.id, "slug": c.slug, "name": c.name} for c in campaigns]


@app.post("/users")
def create_user(payload: dict) -> dict:
    display_name = (payload.get("display_name") or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Missing display_name")
    with get_session() as session:
        user = User(display_name=display_name)
        session.add(user)
        session.flush()
        return {"id": user.id, "display_name": user.display_name}


@app.post("/campaigns/{campaign_slug}/memberships")
def create_membership(campaign_slug: str, payload: dict, request: Request) -> dict:
    user_id = payload.get("user_id")
    role = payload.get("role", "player")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")
    if role not in {"dm", "player"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if settings.auth_enabled:
            requester_id = _auth_user_id(request)
            existing = (
                session.query(CampaignMembership)
                .filter_by(campaign_id=campaign.id)
                .first()
            )
            if existing:
                if not requester_id:
                    raise HTTPException(status_code=401, detail="Missing X-User-Id header")
                _require_campaign_role(session, campaign.id, requester_id, "dm")
        existing_membership = (
            session.query(CampaignMembership)
            .filter_by(campaign_id=campaign.id, user_id=user_id)
            .first()
        )
        if existing_membership:
            return {
                "id": existing_membership.id,
                "campaign_id": existing_membership.campaign_id,
                "user_id": existing_membership.user_id,
                "role": existing_membership.role,
            }
        membership = CampaignMembership(
            campaign_id=campaign.id,
            user_id=user_id,
            role=role,
        )
        session.add(membership)
        session.flush()
        return {
            "id": membership.id,
            "campaign_id": membership.campaign_id,
            "user_id": membership.user_id,
            "role": membership.role,
        }


@app.post("/notes")
def create_note(payload: dict, request: Request) -> dict:
    campaign_slug = payload.get("campaign_slug")
    session_id = payload.get("session_id")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    body = (payload.get("body") or "").strip()
    if not campaign_slug or not target_type or not target_id or not body:
        raise HTTPException(status_code=400, detail="Missing note fields")
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        if session_id:
            session_obj = session.query(Session).filter_by(id=session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            if session_obj.campaign_id != campaign.id:
                raise HTTPException(status_code=400, detail="Session does not match campaign")
        created_by = _auth_user_id(request) if settings.auth_enabled else None
        note = Note(
            campaign_id=campaign.id,
            session_id=session_id,
            target_type=target_type,
            target_id=target_id,
            body=body,
            created_by=created_by,
        )
        session.add(note)
        session.flush()
        return {
            "id": note.id,
            "target_type": note.target_type,
            "target_id": note.target_id,
            "body": note.body,
            "created_at": note.created_at.isoformat(),
        }


@app.get("/notes")
def list_notes(
    campaign_slug: str,
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        query = session.query(Note).filter(Note.campaign_id == campaign.id)
        if settings.auth_enabled:
            requester_id = _auth_user_id(request)
            membership = _require_campaign_role(session, campaign.id, requester_id)
            if membership.role != "dm":
                query = query.filter(Note.created_by == requester_id)
        if session_id:
            query = query.filter(Note.session_id == session_id)
        if target_type:
            query = query.filter(Note.target_type == target_type)
        if target_id:
            query = query.filter(Note.target_id == target_id)
        notes = query.order_by(Note.created_at.desc(), Note.id.desc()).all()
        return [
            {
                "id": note.id,
                "session_id": note.session_id,
                "target_type": note.target_type,
                "target_id": note.target_id,
                "body": note.body,
                "created_by": note.created_by,
                "created_at": note.created_at.isoformat(),
            }
            for note in notes
        ]


@app.post("/bookmarks")
def create_bookmark(payload: dict, request: Request) -> dict:
    campaign_slug = payload.get("campaign_slug")
    session_id = payload.get("session_id")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    if not campaign_slug or not target_type or not target_id:
        raise HTTPException(status_code=400, detail="Missing bookmark fields")
    if target_type not in {"event", "quote"}:
        raise HTTPException(status_code=400, detail="Unsupported bookmark target type")
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        if session_id:
            session_obj = session.query(Session).filter_by(id=session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            if session_obj.campaign_id != campaign.id:
                raise HTTPException(status_code=400, detail="Session does not match campaign")
        created_by = _auth_user_id(request) if settings.auth_enabled else None
        existing = (
            session.query(Bookmark)
            .filter_by(
                campaign_id=campaign.id,
                target_type=target_type,
                target_id=target_id,
                created_by=created_by,
            )
            .first()
        )
        if existing:
            return {
                "id": existing.id,
                "target_type": existing.target_type,
                "target_id": existing.target_id,
                "created_at": existing.created_at.isoformat(),
            }
        bookmark = Bookmark(
            campaign_id=campaign.id,
            session_id=session_id,
            target_type=target_type,
            target_id=target_id,
            created_by=created_by,
        )
        session.add(bookmark)
        session.flush()
        return {
            "id": bookmark.id,
            "target_type": bookmark.target_type,
            "target_id": bookmark.target_id,
            "created_at": bookmark.created_at.isoformat(),
        }


@app.get("/bookmarks")
def list_bookmarks(
    campaign_slug: str,
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        query = session.query(Bookmark).filter(Bookmark.campaign_id == campaign.id)
        if settings.auth_enabled:
            requester_id = _auth_user_id(request)
            membership = _require_campaign_role(session, campaign.id, requester_id)
            if membership.role != "dm":
                query = query.filter(Bookmark.created_by == requester_id)
        if session_id:
            query = query.filter(Bookmark.session_id == session_id)
        bookmarks = query.order_by(Bookmark.created_at.desc(), Bookmark.id.desc()).all()
        return [
            {
                "id": bookmark.id,
                "session_id": bookmark.session_id,
                "target_type": bookmark.target_type,
                "target_id": bookmark.target_id,
                "created_by": bookmark.created_by,
                "created_at": bookmark.created_at.isoformat(),
            }
            for bookmark in bookmarks
        ]


@app.post("/spoilers")
def create_spoiler(payload: dict, request: Request) -> dict:
    campaign_slug = payload.get("campaign_slug")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    reveal_session_number = payload.get("reveal_session_number")
    if not campaign_slug or not target_type or not target_id or reveal_session_number is None:
        raise HTTPException(status_code=400, detail="Missing spoiler fields")
    if target_type not in {"entity", "thread", "event"}:
        raise HTTPException(status_code=400, detail="Unsupported spoiler target type")
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        _require_dm(session, campaign.id, request)
        created_by = _auth_user_id(request) if settings.auth_enabled else None
        existing = (
            session.query(SpoilerTag)
            .filter_by(
                campaign_id=campaign.id,
                target_type=target_type,
                target_id=target_id,
            )
            .first()
        )
        if existing:
            existing.reveal_session_number = int(reveal_session_number)
            existing.created_by = created_by
            session.flush()
            return {
                "id": existing.id,
                "target_type": existing.target_type,
                "target_id": existing.target_id,
                "reveal_session_number": existing.reveal_session_number,
            }
        tag = SpoilerTag(
            campaign_id=campaign.id,
            target_type=target_type,
            target_id=target_id,
            reveal_session_number=int(reveal_session_number),
            created_by=created_by,
        )
        session.add(tag)
        session.flush()
        return {
            "id": tag.id,
            "target_type": tag.target_type,
            "target_id": tag.target_id,
            "reveal_session_number": tag.reveal_session_number,
        }


@app.get("/campaigns/{campaign_slug}/me")
def get_campaign_membership(campaign_slug: str, request: Request) -> dict:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if not settings.auth_enabled:
            return {"auth_enabled": False, "role": "dm", "user_id": None}
        user_id = _auth_user_id(request)
        membership = (
            session.query(CampaignMembership)
            .filter_by(campaign_id=campaign.id, user_id=user_id)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Missing campaign access")
        return {
            "auth_enabled": True,
            "user_id": membership.user_id,
            "role": membership.role,
        }


@app.get("/campaigns/{campaign_slug}/sessions")
def list_sessions(campaign_slug: str, request: Request) -> list[dict]:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
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


@app.get("/campaigns/{campaign_slug}/admin/metrics")
def get_admin_metrics(campaign_slug: str, request: Request) -> dict:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        _require_dm(session, campaign.id, request)
        sessions_count = session.query(Session).filter_by(campaign_id=campaign.id).count()
        runs_query = session.query(Run).filter_by(campaign_id=campaign.id)
        runs_total = runs_query.count()
        runs_by_status = {
            status: count
            for status, count in runs_query.group_by(Run.status).with_entities(
                Run.status, func.count(Run.id)
            )
        }
        utterances_count = (
            session.query(Utterance)
            .join(Session, Session.id == Utterance.session_id)
            .filter(Session.campaign_id == campaign.id)
            .count()
        )
        latest_run = (
            session.query(Run)
            .filter_by(campaign_id=campaign.id)
            .order_by(Run.created_at.desc())
            .first()
        )
        return {
            "campaign_id": campaign.id,
            "sessions": sessions_count,
            "runs": runs_total,
            "runs_by_status": runs_by_status,
            "utterances": utterances_count,
            "latest_run_id": latest_run.id if latest_run else None,
            "latest_run_status": latest_run.status if latest_run else None,
        }


@app.get("/campaigns/{campaign_slug}/admin/runs")
def list_admin_runs(campaign_slug: str, request: Request) -> list[dict]:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        _require_dm(session, campaign.id, request)
        runs = (
            session.query(Run, Session)
            .join(Session, Session.id == Run.session_id)
            .filter(Run.campaign_id == campaign.id)
            .order_by(Run.created_at.desc())
            .all()
        )
        return [
            {
                "id": run.id,
                "session_id": run.session_id,
                "session_slug": session_obj.slug,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run, session_obj in runs
        ]


@app.get("/campaigns/{campaign_slug}/entities")
def list_entities(
    campaign_slug: str,
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    _validate_slug(campaign_slug, "campaign")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        corrections = _load_corrections(session, campaign.id, None, "entity")
        hidden_ids, merge_map, rename_map = _entity_correction_maps(corrections)
        spoiler_cutoff = _spoiler_cutoff(session, campaign.id, request, session_id)
        spoiler_map = _spoiler_map(session, campaign.id)
        entities = (
            session.query(Entity)
            .filter_by(campaign_id=campaign.id)
            .order_by(Entity.entity_type.asc(), Entity.canonical_name.asc())
            .all()
        )
        return [
            {
                "id": e.id,
                "name": rename_map.get(e.id, e.canonical_name),
                "type": e.entity_type,
                "description": e.description,
            }
            for e in entities
            if e.id not in hidden_ids and e.id not in merge_map
            and (
                spoiler_cutoff is None
                or spoiler_map.get(("entity", e.id), 0) <= spoiler_cutoff
            )
        ]


@app.post("/campaigns/{campaign_slug}/sessions/{session_slug}/transcript")
async def upload_transcript(
    campaign_slug: str,
    session_slug: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    _validate_slug(campaign_slug, "campaign")
    _validate_slug(session_slug, "session")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".jsonl", ".txt", ".srt"}:
        raise HTTPException(status_code=400, detail="Unsupported transcript format")
    dest_dir = (
        Path(settings.transcripts_root)
        / "campaigns"
        / campaign_slug
        / "sessions"
        / session_slug
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"transcript{suffix}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty transcript")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        _require_dm(session, campaign.id, request)
    dest_path.write_bytes(content)
    return {"path": str(dest_path), "bytes": len(content)}


@app.post("/campaigns/{campaign_slug}/sessions/{session_slug}/runs")
async def start_session_run(campaign_slug: str, session_slug: str, request: Request) -> dict:
    _validate_slug(campaign_slug, "campaign")
    _validate_slug(session_slug, "session")
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        _require_dm(session, campaign.id, request)
    from temporalio.client import Client

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    workflow_id = f"process-session:{campaign_slug}:{session_slug}:{uuid.uuid4().hex}"
    handle = await client.start_workflow(
        ProcessSessionWorkflow.run,
        {"campaign_slug": campaign_slug, "session_slug": session_slug},
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    return {"workflow_id": handle.id, "run_id": handle.run_id}


@app.get("/entities/{entity_id}")
def get_entity(entity_id: str, request: Request) -> dict:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        _require_campaign_access(session, entity.campaign_id, request)
        corrections = _load_corrections(session, entity.campaign_id, None, "entity")
        hidden_ids, merge_map, rename_map = _entity_correction_maps(corrections)
        if entity.id in hidden_ids or entity.id in merge_map:
            raise HTTPException(status_code=404, detail="Entity not found")
        aliases = (
            session.query(EntityAlias)
            .filter_by(entity_id=entity.id)
            .order_by(EntityAlias.alias.asc())
            .all()
        )
        alias_adds, alias_removes = _entity_alias_changes(corrections, entity.id)
        alias_list = [alias.alias for alias in aliases if alias.alias not in alias_removes]
        alias_list.extend(sorted(alias_adds))
        return {
            "id": entity.id,
            "name": rename_map.get(entity.id, entity.canonical_name),
            "type": entity.entity_type,
            "description": entity.description,
            "aliases": alias_list,
        }


@app.post("/entities/{entity_id}/corrections")
def create_entity_correction(entity_id: str, payload: dict, request: Request) -> dict:
    action = payload.get("action")
    correction_payload = payload.get("payload") or {}
    session_id = payload.get("session_id")
    created_by = payload.get("created_by")
    allowed_actions = {
        "entity_rename",
        "entity_alias_add",
        "entity_alias_remove",
        "entity_merge",
        "entity_hide",
    }
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Unsupported correction action")
    if action == "entity_rename" and not correction_payload.get("name"):
        raise HTTPException(status_code=400, detail="Missing name for rename correction")
    if action in ("entity_alias_add", "entity_alias_remove") and not correction_payload.get(
        "alias"
    ):
        raise HTTPException(status_code=400, detail="Missing alias for correction")
    if action == "entity_merge" and not correction_payload.get("into_id"):
        raise HTTPException(status_code=400, detail="Missing merge target id")

    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        _require_dm(session, entity.campaign_id, request)
        if session_id:
            session_obj = session.query(Session).filter_by(id=session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            if session_obj.campaign_id != entity.campaign_id:
                raise HTTPException(status_code=400, detail="Session does not match campaign")
        correction = Correction(
            campaign_id=entity.campaign_id,
            session_id=session_id,
            target_type="entity",
            target_id=entity.id,
            action=action,
            payload=correction_payload,
            created_by=created_by,
        )
        session.add(correction)
        session.flush()
        return {
            "id": correction.id,
            "action": correction.action,
            "target_id": correction.target_id,
        }


@app.get("/entities/{entity_id}/mentions")
def list_entity_mentions(
    entity_id: str,
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        _require_campaign_access(session, entity.campaign_id, request)
        corrections = _load_corrections(session, entity.campaign_id, None, "entity")
        hidden_ids, merge_map, _ = _entity_correction_maps(corrections)
        if entity.id in hidden_ids or entity.id in merge_map:
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
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        _require_campaign_access(session, entity.campaign_id, request)
        corrections = _load_corrections(session, entity.campaign_id, None, "entity")
        hidden_ids, merge_map, _ = _entity_correction_maps(corrections)
        if entity.id in hidden_ids or entity.id in merge_map:
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
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        entity = session.query(Entity).filter_by(id=entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        _require_campaign_access(session, entity.campaign_id, request)
        corrections = _load_corrections(session, entity.campaign_id, None, "entity")
        hidden_ids, merge_map, _ = _entity_correction_maps(corrections)
        if entity.id in hidden_ids or entity.id in merge_map:
            raise HTTPException(status_code=404, detail="Entity not found")
        quote_corrections = _load_corrections(session, entity.campaign_id, session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            entity.campaign_id,
            session_id,
            "utterance",
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)
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
            if q.id not in redacted_quotes and q.utterance_id not in redacted_utterances
        ]


@app.get("/sessions/{session_id}/entities")
def list_session_entities(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        session_obj = _session_for_id(session, session_id, request)
        corrections = _load_corrections(session, session_obj.campaign_id, session_id, "entity")
        hidden_ids, merge_map, rename_map = _entity_correction_maps(corrections)
        spoiler_cutoff = _spoiler_cutoff(session, session_obj.campaign_id, request, session_id)
        spoiler_map = _spoiler_map(session, session_obj.campaign_id)
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
                "name": rename_map.get(e.id, e.canonical_name),
                "type": e.entity_type,
                "description": e.description,
            }
            for e in entities
            if e.id not in hidden_ids and e.id not in merge_map
            and (
                spoiler_cutoff is None
                or spoiler_map.get(("entity", e.id), 0) <= spoiler_cutoff
            )
        ]


@app.get("/sessions/{session_id}/mentions")
def list_mentions(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        session_obj = _session_for_id(session, session_id, request)
        corrections = _load_corrections(session, session_obj.campaign_id, session_id, "entity")
        hidden_ids, merge_map, rename_map = _entity_correction_maps(corrections)
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
                "entity_id": (
                    entity.id if entity and entity.id not in hidden_ids and entity.id not in merge_map else None
                ),
                "entity_name": (
                    rename_map.get(entity.id, entity.canonical_name)
                    if entity and entity.id not in hidden_ids and entity.id not in merge_map
                    else None
                ),
                "entity_type_resolved": (
                    entity.entity_type
                    if entity and entity.id not in hidden_ids and entity.id not in merge_map
                    else None
                ),
            }
            for mention, entity in mentions
        ]


@app.get("/sessions/{session_id}/quotes")
def list_quotes(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        session_obj = _session_for_id(session, session_id, request)
        quote_corrections = _load_corrections(session, session_obj.campaign_id, session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            session_obj.campaign_id,
            session_id,
            "utterance",
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)
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
            if q.id not in redacted_quotes and q.utterance_id not in redacted_utterances
        ]


@app.post("/redactions")
def create_redaction(payload: dict, request: Request) -> dict:
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    reason = payload.get("reason")
    created_by = payload.get("created_by")
    if target_type not in {"utterance", "quote"}:
        raise HTTPException(status_code=400, detail="Unsupported redaction target type")
    if not target_id:
        raise HTTPException(status_code=400, detail="Missing redaction target id")
    with get_session() as session:
        if target_type == "utterance":
            utterance = session.query(Utterance).filter_by(id=target_id).first()
            if not utterance:
                raise HTTPException(status_code=404, detail="Utterance not found")
            session_obj = session.query(Session).filter_by(id=utterance.session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            campaign_id = session_obj.campaign_id
            session_id = utterance.session_id
        else:
            quote = session.query(Quote).filter_by(id=target_id).first()
            if not quote:
                raise HTTPException(status_code=404, detail="Quote not found")
            session_obj = session.query(Session).filter_by(id=quote.session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            campaign_id = session_obj.campaign_id
            session_id = quote.session_id
        _require_dm(session, campaign_id, request)
        correction = Correction(
            campaign_id=campaign_id,
            session_id=session_id,
            target_type=target_type,
            target_id=target_id,
            action="redact",
            payload={"reason": reason} if reason else None,
            created_by=created_by,
        )
        session.add(correction)
        session.flush()
        return {"id": correction.id, "target_id": correction.target_id}


@app.get("/campaigns/{campaign_slug}/search")
def search_campaign(
    campaign_slug: str,
    request: Request,
    q: str = Query(..., min_length=2),
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)

        run_ids = None
        if not include_all_runs:
            run_ids = _latest_run_ids_for_campaign(session, campaign.id)
        thread_corrections = _load_corrections(session, campaign.id, session_id, "thread")
        hidden_threads, merge_threads, title_map, status_map, summary_map = _thread_correction_maps(
            thread_corrections
        )
        spoiler_cutoff = _spoiler_cutoff(session, campaign.id, request, session_id)
        spoiler_map = _spoiler_map(session, campaign.id)
        quote_corrections = _load_corrections(session, campaign.id, session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            campaign.id,
            session_id,
            "utterance",
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)

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
    request: Request,
    q: str = Query(..., min_length=2),
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)

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
            if spoiler_cutoff is None
            or spoiler_map.get(("event", e.id), 0) <= spoiler_cutoff
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
                "title": title_map.get(t.id, t.title),
                "summary": summary_map.get(t.id, t.summary),
                "status": status_map.get(t.id, t.status),
                "score": _score_terms(
                    f"{title_map.get(t.id, t.title)} {summary_map.get(t.id, t.summary) or ''}",
                    terms,
                ),
            }
            for t in threads_raw
            if t.id not in hidden_threads and t.id not in merge_threads
            and (
                spoiler_cutoff is None
                or spoiler_map.get(("thread", t.id), 0) <= spoiler_cutoff
            )
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
            if u.thread_id not in hidden_threads and u.thread_id not in merge_threads
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
            if q.id not in redacted_quotes and q.utterance_id not in redacted_utterances
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
            if u.id not in redacted_utterances
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


@app.get("/campaigns/{campaign_slug}/semantic_retrieve")
def semantic_retrieve_campaign(
    campaign_slug: str,
    request: Request,
    q: str = Query(..., min_length=2),
    top_k: Annotated[int, Query()] = settings.semantic_final_k,
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)

        run_ids = None
        if not include_all_runs:
            run_ids = _latest_run_ids_for_campaign(session, campaign.id)

        query_vector = embed_texts([q])[0]
        embedding_query = _embedding_query_base(session, campaign.id, run_ids, session_id)

        embeddings: list[Embedding] = []
        dialect = session.bind.dialect.name if session.bind else "unknown"
        dense_top_k = max(settings.semantic_dense_top_k, top_k)
        if dialect == "postgresql":
            distance = Embedding.embedding.op("<->")(query_vector)
            embeddings = (
                embedding_query.order_by(distance.asc())
                .limit(dense_top_k)
                .all()
            )
        else:
            candidates = embedding_query.all()
            scored = [
                (entry, cosine_similarity(entry.embedding or [], query_vector))
                for entry in candidates
            ]
            scored.sort(key=lambda item: item[1], reverse=True)
            embeddings = [entry for entry, _score in scored[:dense_top_k]]

        if not embeddings:
            return {"query": q, "results": [], "missing_embeddings": True}

        entity_ids = {e.target_id for e in embeddings if e.target_type == "entity"}
        event_ids = {e.target_id for e in embeddings if e.target_type == "event"}
        scene_ids = {e.target_id for e in embeddings if e.target_type == "scene"}
        thread_ids = {e.target_id for e in embeddings if e.target_type == "thread"}
        quote_ids = {e.target_id for e in embeddings if e.target_type == "quote"}
        utterance_ids = {e.target_id for e in embeddings if e.target_type == "utterance"}

        entity_corrections = _load_corrections(session, campaign.id, session_id, "entity")
        hidden_entities, merge_entities, rename_entities = _entity_correction_maps(entity_corrections)
        thread_corrections = _load_corrections(session, campaign.id, session_id, "thread")
        hidden_threads, merge_threads, title_map, status_map, summary_map = _thread_correction_maps(
            thread_corrections
        )
        spoiler_cutoff = _spoiler_cutoff(session, campaign.id, request, session_id)
        spoiler_map = _spoiler_map(session, campaign.id)
        quote_corrections = _load_corrections(session, campaign.id, session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            campaign.id,
            session_id,
            "utterance",
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)

        entities = (
            session.query(Entity)
            .filter(Entity.id.in_(entity_ids))
            .all()
            if entity_ids
            else []
        )
        entity_evidence = _entity_evidence(session, entity_ids, redacted_utterances)
        entity_lookup = {entity.id: entity for entity in entities}

        events = (
            session.query(Event).filter(Event.id.in_(event_ids)).all() if event_ids else []
        )
        event_lookup = {event.id: event for event in events}

        scenes = (
            session.query(Scene).filter(Scene.id.in_(scene_ids)).all() if scene_ids else []
        )
        scene_lookup = {scene.id: scene for scene in scenes}

        threads = (
            session.query(Thread).filter(Thread.id.in_(thread_ids)).all() if thread_ids else []
        )
        thread_lookup = {thread.id: thread for thread in threads}

        quotes = (
            session.query(Quote).filter(Quote.id.in_(quote_ids)).all() if quote_ids else []
        )
        quote_lookup = {quote.id: quote for quote in quotes}

        utterances = (
            session.query(Utterance)
            .filter(Utterance.id.in_(utterance_ids))
            .all()
            if utterance_ids
            else []
        )
        utterance_lookup = {utt.id: utt for utt in utterances}

        scored: list[dict] = []
        for entry in embeddings:
            if entry.target_type == "entity":
                entity = entity_lookup.get(entry.target_id)
                if not entity or entity.id in hidden_entities or entity.id in merge_entities:
                    continue
                if spoiler_cutoff is not None and spoiler_map.get(("entity", entity.id), 0) > spoiler_cutoff:
                    continue
                evidence = entity_evidence.get(entity.id, [])
                if not evidence:
                    continue
                scored.append(
                    {
                        "type": "entity",
                        "id": entity.id,
                        "session_id": None,
                        "name": rename_entities.get(entity.id, entity.canonical_name),
                        "description": entity.description,
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )
                continue

            if entry.target_type == "event":
                event = event_lookup.get(entry.target_id)
                if not event:
                    continue
                if spoiler_cutoff is not None and spoiler_map.get(("event", event.id), 0) > spoiler_cutoff:
                    continue
                evidence = _filter_evidence_spans(event.evidence, redacted_utterances)
                if not evidence:
                    continue
                scored.append(
                    {
                        "type": "event",
                        "id": event.id,
                        "session_id": event.session_id,
                        "event_type": event.event_type,
                        "summary": event.summary,
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )
                continue

            if entry.target_type == "scene":
                scene = scene_lookup.get(entry.target_id)
                if not scene:
                    continue
                evidence = _filter_evidence_spans(scene.evidence, redacted_utterances)
                if not evidence:
                    continue
                scored.append(
                    {
                        "type": "scene",
                        "id": scene.id,
                        "session_id": scene.session_id,
                        "title": scene.title,
                        "summary": scene.summary,
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )
                continue

            if entry.target_type == "thread":
                thread = thread_lookup.get(entry.target_id)
                if not thread or thread.id in hidden_threads or thread.id in merge_threads:
                    continue
                if spoiler_cutoff is not None and spoiler_map.get(("thread", thread.id), 0) > spoiler_cutoff:
                    continue
                evidence = _filter_evidence_spans(thread.evidence, redacted_utterances)
                if not evidence:
                    continue
                scored.append(
                    {
                        "type": "thread",
                        "id": thread.id,
                        "session_id": thread.session_id,
                        "title": title_map.get(thread.id, thread.title),
                        "summary": summary_map.get(thread.id, thread.summary),
                        "status": status_map.get(thread.id, thread.status),
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )
                continue

            if entry.target_type == "quote":
                quote = quote_lookup.get(entry.target_id)
                if not quote:
                    continue
                if quote.id in redacted_quotes or quote.utterance_id in redacted_utterances:
                    continue
                evidence = _quote_evidence(quote, redacted_utterances)
                if not evidence:
                    continue
                scored.append(
                    {
                        "type": "quote",
                        "id": quote.id,
                        "session_id": quote.session_id,
                        "speaker": quote.speaker,
                        "note": quote.note,
                        "display_text": _quote_display_text(
                            quote, {utt.id: utt.text for utt in utterances}
                        ),
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )
                continue

            if entry.target_type == "utterance":
                utt = utterance_lookup.get(entry.target_id)
                if not utt or utt.id in redacted_utterances:
                    continue
                evidence = _utterance_evidence(utt)
                scored.append(
                    {
                        "type": "utterance",
                        "id": utt.id,
                        "session_id": utt.session_id,
                        "participant_id": utt.participant_id,
                        "start_ms": utt.start_ms,
                        "end_ms": utt.end_ms,
                        "text": utt.text,
                        "evidence": evidence,
                        "content": entry.content,
                        "dense_score": cosine_similarity(_embedding_values(entry), query_vector),
                    }
                )

        scored.sort(key=lambda item: item["dense_score"], reverse=True)
        scored = scored[: max(settings.semantic_rerank_top_k, top_k)]

        evidence_utterance_ids: set[str] = set()
        for item in scored:
            evidence_utterance_ids |= _utterance_ids_from_evidence(item.get("evidence"))
        utterance_text_lookup = _utterance_lookup_by_id(session, evidence_utterance_ids)
        evidence_utterances = {
            utt_id: text
            for utt_id, text in utterance_text_lookup.items()
            if utt_id not in redacted_utterances
        }

        if settings.rerank_enabled and scored:
            candidates: list[RerankCandidate] = []
            for item in scored[: settings.semantic_rerank_top_k]:
                evidence_texts = []
                for span in item.get("evidence", []):
                    utterance_id = span.get("utterance_id")
                    if not utterance_id:
                        continue
                    text = evidence_utterances.get(utterance_id)
                    if text:
                        evidence_texts.append(text)
                if not evidence_texts:
                    continue
                candidates.append(
                    RerankCandidate(
                        candidate_id=str(item.get("id")),
                        text="\n".join(evidence_texts),
                        dense_score=item["dense_score"],
                        payload=item,
                    )
                )
            reranked = rerank(q, candidates)
            rerank_map = {candidate.candidate_id: score for candidate, score in reranked}
            for item in scored:
                rerank_score = rerank_map.get(str(item.get("id")))
                item["rerank_score"] = rerank_score
                item["scores"] = {"dense": item["dense_score"], "rerank": rerank_score}
            scored.sort(
                key=lambda item: (
                    item.get("rerank_score") is None,
                    -(item.get("rerank_score") or 0.0),
                )
            )
        else:
            for item in scored:
                item["rerank_score"] = None
                item["scores"] = {"dense": item["dense_score"], "rerank": None}

        scored = scored[:top_k]

        return {
            "query": q,
            "results": scored,
            "missing_embeddings": False,
            "evidence_utterances": evidence_utterances,
        }


@app.post("/campaigns/{campaign_slug}/ask")
def ask_campaign(
    campaign_slug: str,
    payload: dict,
    request: Request,
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    retrieval = semantic_retrieve_campaign(
        campaign_slug,
        request,
        q=question,
        include_all_runs=include_all_runs,
        session_id=session_id,
    )
    results = retrieval.get("results") or []
    evidence_utterances = retrieval.get("evidence_utterances") or {}
    if not results:
        return {
            "answer": "I couldn't find evidence in the campaign data for that question.",
            "citations": [],
            "results": [],
        }

    evidence_lines = []
    used_utterances: set[str] = set()
    for item in results:
        for span in item.get("evidence", []):
            utterance_id = span.get("utterance_id")
            if not utterance_id or utterance_id in used_utterances:
                continue
            text = evidence_utterances.get(utterance_id)
            if not text:
                continue
            used_utterances.add(utterance_id)
            evidence_lines.append(f"[{utterance_id}] {text.strip()}")
    evidence_block = "\n".join(evidence_lines) or "[none]"

    prompt = (
        Path(settings.prompts_root) / "ask_campaign_v1.txt"
    ).read_text(encoding="utf-8").format(
        question=question,
        evidence=evidence_block,
    )

    try:
        client = LLMClient()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw = client.generate_json_schema(prompt, schema=ask_campaign_schema())
    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Invalid LLM response") from exc

    return {
        "answer": response.get("answer", ""),
        "citations": response.get("citations", []),
        "results": results,
    }


@app.get("/sessions/{session_id}/scenes")
def list_scenes(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        _session_for_id(session, session_id, request)
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
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        session_obj = _session_for_id(session, session_id, request)
        spoiler_cutoff = _spoiler_cutoff(session, session_obj.campaign_id, request, session_id)
        spoiler_map = _spoiler_map(session, session_obj.campaign_id)
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
            if spoiler_cutoff is None
            or spoiler_map.get(("event", e.id), 0) <= spoiler_cutoff
        ]


@app.get("/sessions/{session_id}/threads")
def list_threads(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        session_obj = _session_for_id(session, session_id, request)
        corrections = _load_corrections(session, session_obj.campaign_id, session_id, "thread")
        hidden_ids, merge_map, title_map, status_map, summary_map = _thread_correction_maps(
            corrections
        )
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
                "campaign_thread_id": t.campaign_thread_id,
                "title": title_map.get(t.id, t.title),
                "kind": t.kind,
                "status": status_map.get(t.id, t.status),
                "summary": summary_map.get(t.id, t.summary),
                "evidence": t.evidence,
                "confidence": t.confidence,
                "created_at": t.created_at.isoformat(),
                "updates": updates_by_thread.get(t.id, []),
            }
            for t in threads
            if t.id not in hidden_ids and t.id not in merge_map
        ]


@app.post("/threads/{thread_id}/corrections")
def create_thread_correction(thread_id: str, payload: dict, request: Request) -> dict:
    action = payload.get("action")
    correction_payload = payload.get("payload") or {}
    session_id = payload.get("session_id")
    created_by = payload.get("created_by")
    allowed_actions = {
        "thread_status",
        "thread_title",
        "thread_summary",
        "thread_merge",
        "thread_hide",
    }
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Unsupported correction action")
    if action == "thread_status" and not correction_payload.get("status"):
        raise HTTPException(status_code=400, detail="Missing status for correction")
    if action == "thread_title" and not correction_payload.get("title"):
        raise HTTPException(status_code=400, detail="Missing title for correction")
    if action == "thread_merge" and not correction_payload.get("into_id"):
        raise HTTPException(status_code=400, detail="Missing merge target id")

    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        run = session.query(Run).filter_by(id=thread.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        _require_dm(session, run.campaign_id, request)
        if session_id:
            session_obj = session.query(Session).filter_by(id=session_id).first()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
            if session_obj.campaign_id != run.campaign_id:
                raise HTTPException(status_code=400, detail="Session does not match campaign")
        correction = Correction(
            campaign_id=run.campaign_id,
            session_id=session_id,
            target_type="thread",
            target_id=thread.id,
            action=action,
            payload=correction_payload,
            created_by=created_by,
        )
        session.add(correction)
        session.flush()
        return {
            "id": correction.id,
            "action": correction.action,
            "target_id": correction.target_id,
        }


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


def _utterance_lookup_by_id(session, utterance_ids: set[str]) -> dict[str, str]:
    if not utterance_ids:
        return {}
    utterances = (
        session.query(Utterance)
        .filter(Utterance.id.in_(sorted(utterance_ids)))
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
    session_obj = session.query(Session).filter_by(id=session_id).first()
    if session_obj and session_obj.current_run_id:
        run = (
            session.query(Run)
            .filter_by(id=session_obj.current_run_id, session_id=session_id)
            .first()
        )
        if run:
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
    session_rows = session.query(Session).filter_by(campaign_id=campaign_id).all()
    selected_by_session = {
        row.id: row.current_run_id for row in session_rows if row.current_run_id
    }
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
    return set(selected_by_session.values()) | set(latest_by_session.values())


def _simple_score(text: str, query: str) -> float:
    hay = text.lower()
    needle = query.lower()
    if not hay or not needle:
        return 0.0
    return float(hay.count(needle))


def _embedding_query_base(session, campaign_id: str, run_ids: set[str] | None, session_id: str | None):
    query = (
        session.query(Embedding)
        .filter(
            Embedding.campaign_id == campaign_id,
            Embedding.model == settings.embedding_model,
            Embedding.version == settings.embedding_version,
        )
    )
    if session_id:
        query = query.filter(
            or_(Embedding.session_id == session_id, Embedding.session_id.is_(None))
        )
    if run_ids is not None:
        query = query.filter(or_(Embedding.run_id.in_(run_ids), Embedding.run_id.is_(None)))
    return query


def _embedding_values(entry: Embedding) -> list[float]:
    if entry.embedding is None:
        return []
    if hasattr(entry.embedding, "tolist"):
        return entry.embedding.tolist()
    return list(entry.embedding)


def _filter_evidence_spans(
    evidence: list[dict] | None,
    redacted_utterances: set[str],
) -> list[dict]:
    filtered = []
    for span in evidence or []:
        utterance_id = span.get("utterance_id")
        if not utterance_id or utterance_id in redacted_utterances:
            continue
        filtered.append(span)
    return filtered


def _entity_evidence(
    session,
    entity_ids: set[str],
    redacted_utterances: set[str],
) -> dict[str, list[dict]]:
    if not entity_ids:
        return {}
    rows = (
        session.query(EntityMention.entity_id, Mention.evidence)
        .join(Mention, Mention.id == EntityMention.mention_id)
        .filter(EntityMention.entity_id.in_(entity_ids))
        .all()
    )
    evidence_map: dict[str, list[dict]] = {}
    for entity_id, evidence in rows:
        spans = _filter_evidence_spans(evidence, redacted_utterances)
        if not spans:
            continue
        evidence_map.setdefault(entity_id, []).extend(spans)
    return evidence_map


def _quote_evidence(quote: Quote, redacted_utterances: set[str]) -> list[dict]:
    if not quote.utterance_id or quote.utterance_id in redacted_utterances:
        return []
    if quote.char_start is None or quote.char_end is None:
        return [
            {
                "utterance_id": quote.utterance_id,
                "kind": "quote",
            }
        ]
    return [
        {
            "utterance_id": quote.utterance_id,
            "char_start": quote.char_start,
            "char_end": quote.char_end,
            "kind": "quote",
        }
    ]


def _utterance_evidence(utterance: Utterance) -> list[dict]:
    return [
        {
            "utterance_id": utterance.id,
            "char_start": 0,
            "char_end": len(utterance.text or ""),
            "kind": "support",
        }
    ]


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
def list_thread_mentions(thread_id: str, request: Request) -> list[dict]:
    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        run = session.query(Run).filter_by(id=thread.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        _require_campaign_access(session, run.campaign_id, request)
        corrections = _load_corrections(session, run.campaign_id, thread.session_id, "thread")
        hidden_ids, merge_map, title_map, _, _ = _thread_correction_maps(corrections)
        if thread.id in hidden_ids or thread.id in merge_map:
            raise HTTPException(status_code=404, detail="Thread not found")
        thread_title = title_map.get(thread.id, thread.title)
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

        tokens = _thread_title_tokens(thread_title)
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
def list_thread_quotes(thread_id: str, request: Request) -> list[dict]:
    with get_session() as session:
        thread = session.query(Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        run = session.query(Run).filter_by(id=thread.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        _require_campaign_access(session, run.campaign_id, request)
        corrections = _load_corrections(session, run.campaign_id, thread.session_id, "thread")
        hidden_ids, merge_map, title_map, _, _ = _thread_correction_maps(corrections)
        if thread.id in hidden_ids or thread.id in merge_map:
            raise HTTPException(status_code=404, detail="Thread not found")
        quote_corrections = _load_corrections(session, run.campaign_id, thread.session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            run.campaign_id,
            thread.session_id,
            "utterance",
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)
        thread_title = title_map.get(thread.id, thread.title)
        updates = session.query(ThreadUpdate).filter_by(thread_id=thread_id).all()

        utterance_ids = set()
        utterance_ids |= _utterance_ids_from_evidence(thread.evidence)
        related_event_ids: list[str] = []
        for update in updates:
            utterance_ids |= _utterance_ids_from_evidence(update.evidence)
            related_event_ids.extend(update.related_event_ids or [])
        utterance_ids |= _thread_event_utterance_ids(session, thread, related_event_ids)

        if not utterance_ids:
            tokens = _thread_title_tokens(thread_title)
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
            if q.id not in redacted_quotes and q.utterance_id not in redacted_utterances
        ]


@app.get("/sessions/{session_id}/artifacts")
def list_artifacts(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        _session_for_id(session, session_id, request)
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
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        _session_for_id(session, session_id, request)
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        summary_kinds = {
            "summary_text",
            "summary_player",
            "summary_dm",
            "summary_hooks",
            "summary_npc_changes",
        }
        summaries = (
            session.query(SessionExtraction)
            .filter(
                SessionExtraction.session_id == session_id,
                SessionExtraction.run_id == resolved_run_id,
                SessionExtraction.kind.in_(summary_kinds),
            )
            .order_by(SessionExtraction.created_at.desc())
            .all()
        )
        summary_by_kind = {}
        for record in summaries:
            if record.kind in summary_by_kind:
                continue
            summary_by_kind[record.kind] = record
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
        llm_calls = (
            session.query(LLMCall)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(LLMCall.created_at.asc(), LLMCall.id.asc())
            .all()
        )
        llm_usage = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="llm_usage")
            .order_by(SessionExtraction.created_at.asc(), SessionExtraction.id.asc())
            .all()
        )
        run_steps = (
            session.query(RunStep)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(RunStep.started_at.asc(), RunStep.id.asc())
            .all()
        )
        if not summary_by_kind:
            raise HTTPException(status_code=404, detail="Summary not found")
        summary_text = summary_by_kind.get("summary_text")
        variants = {
            kind: record.payload.get("text", "")
            for kind, record in summary_by_kind.items()
            if record.payload
        }
        return {
            "text": summary_text.payload.get("text", "") if summary_text else "",
            "variants": variants,
        }


@app.get("/sessions/{session_id}/export")
def export_session(session_id: str, request: Request) -> FileResponse:
    with get_session() as session:
        session_obj = session.query(Session).filter_by(id=session_id).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_dm(session, session_obj.campaign_id, request)
        artifacts = (
            session.query(Artifact)
            .filter_by(session_id=session_id)
            .order_by(Artifact.created_at.asc())
            .all()
        )
        utterances = (
            session.query(Utterance)
            .filter_by(session_id=session_id)
            .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
            .all()
        )
        utterance_corrections = _load_corrections(
            session,
            session_obj.campaign_id,
            session_id,
            "utterance",
        )
        redacted_utterances = _redacted_ids(utterance_corrections)
        if redacted_utterances:
            utterances = [utt for utt in utterances if utt.id not in redacted_utterances]
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            zip_path = Path(handle.name)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if utterances:
                transcript_path = Path(f"session_{session_id}") / "utterances.txt"
                transcript_text = "\n".join(
                    f"{utt.start_ms}\t{utt.end_ms}\t{utt.participant_id}\t{utt.text}"
                    for utt in utterances
                )
                archive.writestr(str(transcript_path), transcript_text)
            for artifact in artifacts:
                artifact_path = Path(artifact.path)
                if not artifact_path.is_absolute():
                    artifact_path = Path(settings.artifacts_root) / artifact.path
                if artifact_path.exists():
                    archive.write(
                        artifact_path,
                        arcname=str(Path("artifacts") / artifact_path.name),
                    )
        return FileResponse(
            zip_path,
            filename=f"session_{session_id}_export.zip",
            media_type="application/zip",
        )


@app.get("/sessions/{session_id}/runs")
def list_runs(session_id: str, request: Request) -> list[dict]:
    with get_session() as session:
        _session_for_id(session, session_id, request)
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


@app.get("/sessions/{session_id}/run-status")
def get_run_status(
    session_id: str,
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        _session_for_id(session, session_id, request)
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        run = session.query(Run).filter_by(id=resolved_run_id, session_id=session_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found for session")

        steps = (
            session.query(RunStep)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(RunStep.started_at.asc(), RunStep.id.asc())
            .all()
        )
        latest_call = (
            session.query(LLMCall)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(LLMCall.created_at.desc(), LLMCall.id.desc())
            .first()
        )
        latest_artifact = (
            session.query(Artifact)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
            .first()
        )

        return {
            "run_id": resolved_run_id,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "steps": [
                {
                    "id": step.id,
                    "name": step.name,
                    "status": step.status,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "finished_at": step.finished_at.isoformat() if step.finished_at else None,
                    "error": step.error,
                }
                for step in steps
            ],
            "latest_llm_call": {
                "id": latest_call.id,
                "kind": latest_call.kind,
                "status": latest_call.status,
                "created_at": latest_call.created_at.isoformat(),
                "error": latest_call.error,
            }
            if latest_call
            else None,
            "latest_artifact": {
                "id": latest_artifact.id,
                "kind": latest_artifact.kind,
                "path": latest_artifact.path,
                "created_at": latest_artifact.created_at.isoformat(),
            }
            if latest_artifact
            else None,
        }


@app.put("/sessions/{session_id}/current-run")
def set_current_run(session_id: str, run_id: str, request: Request) -> dict:
    with get_session() as session:
        run = session.query(Run).filter_by(id=run_id, session_id=session_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found for session")
        session_obj = session.query(Session).filter_by(id=session_id).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_dm(session, session_obj.campaign_id, request)
        session_obj.current_run_id = run.id
        return {"session_id": session_id, "current_run_id": run.id}


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request) -> dict:
    with get_session() as session:
        session_obj = session.query(Session).filter_by(id=session_id).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_dm(session, session_obj.campaign_id, request)
        run_ids = [run.id for run in session.query(Run).filter_by(session_id=session_id).all()]
        session.query(Artifact).filter_by(session_id=session_id).delete()
        session.query(SessionExtraction).filter_by(session_id=session_id).delete()
        session.query(LLMCall).filter_by(session_id=session_id).delete()
        session.query(Quote).filter_by(session_id=session_id).delete()
        session.query(Event).filter_by(session_id=session_id).delete()
        session.query(Scene).filter_by(session_id=session_id).delete()
        session.query(ThreadUpdate).filter_by(session_id=session_id).delete()
        session.query(Thread).filter_by(session_id=session_id).delete()
        session.query(EntityMention).filter_by(session_id=session_id).delete()
        session.query(Mention).filter_by(session_id=session_id).delete()
        session.query(Utterance).filter_by(session_id=session_id).delete()
        session.query(Run).filter_by(session_id=session_id).delete()
        session.delete(session_obj)

        return {"session_id": session_id, "deleted_runs": len(run_ids)}


@app.get("/utterances")
def list_utterances(
    request: Request,
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
        redacted_by_session: dict[str, set[str]] = {}
        for utter_session_id in {utt.session_id for utt in utterances}:
            session_obj = session.query(Session).filter_by(id=utter_session_id).first()
            if not session_obj:
                continue
            _require_campaign_access(session, session_obj.campaign_id, request)
            corrections = _load_corrections(
                session,
                session_obj.campaign_id,
                utter_session_id,
                "utterance",
            )
            redacted_by_session[utter_session_id] = _redacted_ids(corrections)
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
            if utt.id not in redacted_by_session.get(utt.session_id, set())
        ]


@app.get("/utterances/{utterance_id}")
def get_utterance(utterance_id: str, request: Request) -> dict:
    with get_session() as session:
        utterance = session.query(Utterance).filter_by(id=utterance_id).first()
        if not utterance:
            raise HTTPException(status_code=404, detail="Utterance not found")
        session_obj = session.query(Session).filter_by(id=utterance.session_id).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_campaign_access(session, session_obj.campaign_id, request)
        corrections = _load_corrections(
            session,
            session_obj.campaign_id,
            utterance.session_id,
            "utterance",
        )
        if utterance.id in _redacted_ids(corrections):
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
    request: Request,
    status: Annotated[str | None, Query()] = None,
    include_all_runs: Annotated[bool, Query()] = False,
    session_id: Annotated[str | None, Query()] = None,
) -> list[dict]:
    with get_session() as session:
        campaign = _campaign_for_slug(session, campaign_slug, request)
        corrections = _load_corrections(session, campaign.id, None, "thread")
        hidden_ids, merge_map, title_map, status_map, summary_map = _thread_correction_maps(
            corrections
        )
        spoiler_cutoff = _spoiler_cutoff(session, campaign.id, request, session_id)
        spoiler_map = _spoiler_map(session, campaign.id)

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
            if thread.id in hidden_ids or thread.id in merge_map:
                continue
            thread_title = title_map.get(thread.id, thread.title)
            thread_status = status_map.get(thread.id, thread.status)
            thread_summary = summary_map.get(thread.id, thread.summary)
            if (
                spoiler_cutoff is not None
                and spoiler_map.get(("thread", thread.id), 0) > spoiler_cutoff
            ):
                continue
            if status and thread_status != status:
                continue
            key = thread.campaign_thread_id or " ".join((thread_title or "").lower().split())
            if not key:
                continue
            entry = {
                "id": thread.id,
                "campaign_thread_id": thread.campaign_thread_id,
                "title": thread_title,
                "kind": thread.kind,
                "status": thread_status,
                "summary": thread_summary,
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
    request: Request,
    run_id: Annotated[str | None, Query()] = None,
) -> dict:
    with get_session() as session:
        resolved_run_id = _resolve_run_id(session, session_id, run_id)
        run = session.query(Run).filter_by(id=resolved_run_id).first()
        session_obj = _session_for_id(session, session_id, request)
        entity_corrections = _load_corrections(session, session_obj.campaign_id, session_id, "entity")
        thread_corrections = _load_corrections(session, session_obj.campaign_id, session_id, "thread")
        quote_corrections = _load_corrections(session, session_obj.campaign_id, session_id, "quote")
        utterance_corrections = _load_corrections(
            session,
            session_obj.campaign_id,
            session_id,
            "utterance",
        )
        hidden_entities, merge_entities, rename_entities = _entity_correction_maps(
            entity_corrections
        )
        hidden_threads, merge_threads, title_map, status_map, summary_map = _thread_correction_maps(
            thread_corrections
        )
        redacted_quotes = _redacted_ids(quote_corrections)
        redacted_utterances = _redacted_ids(utterance_corrections)

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
        llm_calls = (
            session.query(LLMCall)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(LLMCall.created_at.asc(), LLMCall.id.asc())
            .all()
        )
        llm_usage = (
            session.query(SessionExtraction)
            .filter_by(session_id=session_id, run_id=resolved_run_id, kind="llm_usage")
            .order_by(SessionExtraction.created_at.asc(), SessionExtraction.id.asc())
            .all()
        )
        run_steps = (
            session.query(RunStep)
            .filter_by(session_id=session_id, run_id=resolved_run_id)
            .order_by(RunStep.started_at.asc(), RunStep.id.asc())
            .all()
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
        utterances = (
            session.query(Utterance)
            .options(joinedload(Utterance.participant))
            .filter_by(session_id=session_id)
            .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
            .all()
        )
        if redacted_utterances:
            utterances = [utt for utt in utterances if utt.id not in redacted_utterances]
        transcript_lines: list[str] = []
        utterance_timecodes: dict[str, str] = {}
        if utterances and run:
            character_map = load_character_map(session, run.campaign_id)
            transcript_text, key_to_id = format_transcript(utterances, character_map)
            transcript_lines = transcript_text.splitlines()
            utterance_timecodes = {utt_id: key for key, utt_id in key_to_id.items()}

        character_sheets = (
            session.query(CharacterSheetSnapshot)
            .filter_by(session_id=session_id)
            .order_by(CharacterSheetSnapshot.created_at.desc())
            .all()
        )
        dice_rolls = (
            session.query(DiceRoll)
            .filter_by(session_id=session_id)
            .order_by(DiceRoll.t_ms.asc(), DiceRoll.roll_index.asc())
            .all()
        )

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
        spoiler_cutoff = _spoiler_cutoff(session, session_obj.campaign_id, request, session_id)
        spoiler_map = _spoiler_map(session, session_obj.campaign_id)

        return {
            "session_id": session_id,
            "run_id": resolved_run_id,
            "run_status": run.status if run else None,
            "run_created_at": run.created_at.isoformat() if run else None,
            "summary": summary.payload.get("text", "") if summary else "",
            "metrics": persist_metrics.payload if persist_metrics else None,
            "quality": quality_report.payload if quality_report else None,
            "llm_calls": [
                {
                    "id": call.id,
                    "kind": call.kind,
                    "status": call.status,
                    "latency_ms": call.latency_ms,
                    "prompt_id": call.prompt_id,
                    "prompt_version": call.prompt_version,
                    "model": call.model,
                    "error": call.error,
                    "created_at": call.created_at.isoformat(),
                }
                for call in llm_calls
            ],
            "llm_usage": [record.payload for record in llm_usage],
            "run_steps": [
                {
                    "id": step.id,
                    "name": step.name,
                    "status": step.status,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "finished_at": step.finished_at.isoformat() if step.finished_at else None,
                    "error": step.error,
                }
                for step in run_steps
            ],
            "transcript": {
                "format": settings.transcript_format_version,
                "lines": transcript_lines,
                "utterance_timecodes": utterance_timecodes,
            },
            "character_sheets": [
                {
                    "id": sheet.id,
                    "character_slug": sheet.character_slug,
                    "character_name": sheet.character_name,
                    "source_path": sheet.source_path,
                    "payload": sheet.payload,
                    "created_at": sheet.created_at.isoformat(),
                }
                for sheet in character_sheets
            ],
            "dice_rolls": [
                {
                    "id": roll.id,
                    "t_ms": roll.t_ms,
                    "character_name": roll.character_name,
                    "kind": roll.kind,
                    "expression": roll.expression,
                    "total": roll.total,
                    "detail": roll.detail,
                    "utterance_id": (
                        None
                        if roll.utterance_id in redacted_utterances
                        else roll.utterance_id
                    ),
                    "utterance_timecode": (
                        utterance_timecodes.get(roll.utterance_id)
                        if roll.utterance_id not in redacted_utterances
                        else None
                    ),
                    "evidence": (
                        [{"utterance_id": roll.utterance_id, "kind": "support"}]
                        if roll.utterance_id and roll.utterance_id not in redacted_utterances
                        else []
                    ),
                }
                for roll in dice_rolls
            ],
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
                if q.id not in redacted_quotes and q.utterance_id not in redacted_utterances
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
                if spoiler_cutoff is None
                or spoiler_map.get(("event", e.id), 0) <= spoiler_cutoff
            ],
            "threads": [
                {
                    "id": t.id,
                    "campaign_thread_id": t.campaign_thread_id,
                    "title": title_map.get(t.id, t.title),
                    "kind": t.kind,
                    "status": status_map.get(t.id, t.status),
                    "summary": summary_map.get(t.id, t.summary),
                    "evidence": t.evidence,
                    "confidence": t.confidence,
                    "created_at": t.created_at.isoformat(),
                    "updates": updates_by_thread.get(t.id, []),
                }
                for t in threads
                if t.id not in hidden_threads and t.id not in merge_threads
                and (
                    spoiler_cutoff is None
                    or spoiler_map.get(("thread", t.id), 0) <= spoiler_cutoff
                )
            ],
            "entities": [
                {
                    "id": e.id,
                    "name": rename_entities.get(e.id, e.canonical_name),
                    "type": e.entity_type,
                    "description": e.description,
                }
                for e in entities
                if e.id not in hidden_entities and e.id not in merge_entities
                and (
                    spoiler_cutoff is None
                    or spoiler_map.get(("entity", e.id), 0) <= spoiler_cutoff
                )
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
