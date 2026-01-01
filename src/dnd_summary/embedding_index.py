from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_

from dnd_summary.config import settings
from dnd_summary.embeddings import EmbeddingInput, embed_texts, text_hash
from dnd_summary.models import (
    Embedding,
    Entity,
    Event,
    Quote,
    Run,
    Scene,
    Session,
    Thread,
    ThreadUpdate,
    Utterance,
)


@dataclass(frozen=True)
class EmbeddingStats:
    created: int
    skipped: int
    deleted: int


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


def _content_or_empty(*parts: str | None) -> str:
    text = " ".join(part.strip() for part in parts if part and part.strip())
    return text.strip()


def _collect_embedding_inputs(
    session,
    campaign_id: str,
    session_id: str | None,
    include_all_runs: bool,
) -> list[EmbeddingInput]:
    run_ids = None
    if not include_all_runs:
        run_ids = _latest_run_ids_for_campaign(session, campaign_id)

    inputs: list[EmbeddingInput] = []

    entities = session.query(Entity).filter_by(campaign_id=campaign_id).all()
    for entity in entities:
        content = _content_or_empty(entity.canonical_name, entity.description)
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="entity",
                target_id=entity.id,
                campaign_id=campaign_id,
                session_id=None,
                run_id=None,
                content=content,
            )
        )

    runs_query = session.query(Run).filter_by(campaign_id=campaign_id)
    if session_id:
        runs_query = runs_query.filter(Run.session_id == session_id)
    if run_ids is not None:
        runs_query = runs_query.filter(Run.id.in_(run_ids))
    scoped_runs = runs_query.all()
    run_ids = {run.id for run in scoped_runs}

    if not run_ids:
        return inputs

    utterance_sessions = {run.session_id for run in scoped_runs}
    utterances = (
        session.query(Utterance)
        .filter(Utterance.session_id.in_(utterance_sessions))
        .order_by(Utterance.start_ms.asc())
        .all()
    )
    for utt in utterances:
        content = (utt.text or "").strip()
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="utterance",
                target_id=utt.id,
                campaign_id=campaign_id,
                session_id=utt.session_id,
                run_id=None,
                content=content,
            )
        )

    events = session.query(Event).filter(Event.run_id.in_(run_ids)).all()
    for event in events:
        content = _content_or_empty(event.summary, " ".join(event.entities or []))
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="event",
                target_id=event.id,
                campaign_id=campaign_id,
                session_id=event.session_id,
                run_id=event.run_id,
                content=content,
            )
        )

    scenes = session.query(Scene).filter(Scene.run_id.in_(run_ids)).all()
    for scene in scenes:
        content = _content_or_empty(scene.title, scene.summary, scene.location)
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="scene",
                target_id=scene.id,
                campaign_id=campaign_id,
                session_id=scene.session_id,
                run_id=scene.run_id,
                content=content,
            )
        )

    threads = session.query(Thread).filter(Thread.run_id.in_(run_ids)).all()
    updates = session.query(ThreadUpdate).filter(ThreadUpdate.run_id.in_(run_ids)).all()
    updates_by_thread: dict[str, list[str]] = defaultdict(list)
    for update in updates:
        if update.note:
            updates_by_thread[update.thread_id].append(update.note)
    for thread in threads:
        updates_text = " ".join(updates_by_thread.get(thread.id, []))
        content = _content_or_empty(thread.title, thread.summary, updates_text)
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="thread",
                target_id=thread.id,
                campaign_id=campaign_id,
                session_id=thread.session_id,
                run_id=thread.run_id,
                content=content,
            )
        )

    quote_lookup = {utt.id: utt.text for utt in utterances}
    quotes = session.query(Quote).filter(Quote.run_id.in_(run_ids)).all()
    for quote in quotes:
        content = _content_or_empty(
            quote.clean_text,
            quote.note,
            quote_lookup.get(quote.utterance_id),
        )
        if not content:
            continue
        inputs.append(
            EmbeddingInput(
                target_type="quote",
                target_id=quote.id,
                campaign_id=campaign_id,
                session_id=quote.session_id,
                run_id=quote.run_id,
                content=content,
            )
        )

    return inputs


def _embedding_signature() -> tuple[str, str, str, int, bool]:
    return (
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_version,
        settings.embedding_dimensions,
        settings.embedding_normalize,
    )


def _validate_embedding_compatibility(
    session,
    campaign_id: str,
    session_id: str | None,
    rebuild: bool,
) -> None:
    if rebuild:
        return
    query = session.query(
        Embedding.provider,
        Embedding.model,
        Embedding.version,
        Embedding.dimensions,
        Embedding.normalized,
    ).filter(Embedding.campaign_id == campaign_id)
    if session_id:
        query = query.filter(
            (Embedding.session_id == session_id) | (Embedding.session_id.is_(None))
        )
    rows = query.distinct().all()
    if not rows:
        return
    expected_provider, expected_model, expected_version, expected_dims, expected_norm = (
        _embedding_signature()
    )
    for provider, model, version, dimensions, normalized in rows:
        if model and model != expected_model:
            raise ValueError("Embedding model mismatch; use --rebuild to regenerate.")
        if version and version != expected_version:
            raise ValueError("Embedding version mismatch; use --rebuild to regenerate.")
        if provider and provider != expected_provider:
            raise ValueError("Embedding provider mismatch; use --rebuild to regenerate.")
        if dimensions and dimensions != expected_dims:
            raise ValueError("Embedding dimensions mismatch; use --rebuild to regenerate.")
        if normalized is not None and normalized != expected_norm:
            raise ValueError("Embedding normalization mismatch; use --rebuild to regenerate.")


def build_embeddings_for_campaign(
    session,
    campaign_id: str,
    session_id: str | None = None,
    include_all_runs: bool = False,
    replace: bool = False,
    rebuild: bool = False,
) -> EmbeddingStats:
    model = settings.embedding_model
    version = settings.embedding_version
    now = datetime.utcnow()

    if replace or rebuild:
        delete_query = session.query(Embedding).filter(Embedding.campaign_id == campaign_id)
        if not rebuild:
            delete_query = delete_query.filter(
                Embedding.model == model,
                Embedding.version == version,
            )
        if session_id:
            delete_query = delete_query.filter(
                (Embedding.session_id == session_id) | (Embedding.session_id.is_(None))
            )
        deleted = delete_query.delete(synchronize_session=False)
    else:
        deleted = 0

    _validate_embedding_compatibility(session, campaign_id, session_id, rebuild or replace)

    existing_rows = (
        session.query(Embedding.target_type, Embedding.target_id, Embedding.text_hash)
        .filter(
            Embedding.campaign_id == campaign_id,
            Embedding.model == model,
            Embedding.version == version,
        )
        .all()
    )
    existing = {(row[0], row[1]): row[2] for row in existing_rows}

    inputs = _collect_embedding_inputs(session, campaign_id, session_id, include_all_runs)
    pending: list[EmbeddingInput] = []
    to_delete: list[tuple[str, str]] = []
    skipped = 0
    for entry in inputs:
        key = (entry.target_type, entry.target_id)
        digest = text_hash(entry.content)
        if key in existing:
            existing_hash = existing[key]
            if existing_hash == digest:
                skipped += 1
                continue
            to_delete.append(key)
        pending.append(entry)

    if to_delete:
        delete_filter = [
            (Embedding.target_type == target_type) & (Embedding.target_id == target_id)
            for target_type, target_id in to_delete
        ]
        session.query(Embedding).filter(
            Embedding.campaign_id == campaign_id,
            Embedding.model == model,
            Embedding.version == version,
            or_(*delete_filter),
        ).delete(synchronize_session=False)

    created = 0
    batch_size = max(settings.embedding_batch_size, 1)
    for idx in range(0, len(pending), batch_size):
        batch = pending[idx : idx + batch_size]
        texts = [item.content for item in batch]
        vectors = embed_texts(texts)
        rows = [
            Embedding(
                campaign_id=item.campaign_id,
                session_id=item.session_id,
                run_id=item.run_id,
                target_type=item.target_type,
                target_id=item.target_id,
                content=item.content,
                text_hash=text_hash(item.content),
                embedding=vector,
                model=model,
                version=version,
                provider=settings.embedding_provider,
                dimensions=settings.embedding_dimensions,
                normalized=settings.embedding_normalize,
                created_at=now,
            )
            for item, vector in zip(batch, vectors)
        ]
        session.add_all(rows)
        created += len(rows)

    return EmbeddingStats(created=created, skipped=skipped, deleted=deleted)
