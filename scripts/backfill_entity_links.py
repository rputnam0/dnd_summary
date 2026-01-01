from __future__ import annotations

import argparse

from dnd_summary.db import get_session
from dnd_summary.models import (
    Entity,
    EntityAlias,
    EntityMention,
    Event,
    EventEntity,
    Mention,
    Run,
    Scene,
    SceneEntity,
    Thread,
    ThreadEntity,
    ThreadUpdate,
)


def _normalize_key(text: str) -> str:
    return " ".join(text.lower().split())


def _entity_name_map(session, campaign_id: str) -> dict[str, str]:
    entities = session.query(Entity).filter_by(campaign_id=campaign_id).all()
    entity_ids = [entity.id for entity in entities]
    aliases = (
        session.query(EntityAlias)
        .filter(EntityAlias.entity_id.in_(entity_ids))
        .all()
    )
    mapping: dict[str, str] = {}
    for entity in entities:
        mapping[_normalize_key(entity.canonical_name)] = entity.id
    for alias in aliases:
        mapping[_normalize_key(alias.alias)] = alias.entity_id
    return mapping


def _utterance_to_entities(session, run_id: str, session_id: str) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    rows = (
        session.query(EntityMention.entity_id, Mention.evidence)
        .join(Mention, Mention.id == EntityMention.mention_id)
        .filter(EntityMention.run_id == run_id, EntityMention.session_id == session_id)
        .all()
    )
    for entity_id, evidence in rows:
        for entry in evidence or []:
            utt_id = entry.get("utterance_id")
            if not utt_id:
                continue
            mapping.setdefault(utt_id, set()).add(entity_id)
    return mapping


def _entity_ids_from_evidence(evidence: list[dict] | None, lookup: dict[str, set[str]]) -> set[str]:
    ids: set[str] = set()
    for entry in evidence or []:
        utt_id = entry.get("utterance_id")
        if not utt_id:
            continue
        ids |= lookup.get(utt_id, set())
    return ids


def _normalize_entity_tokens(names: list[str] | None) -> list[str]:
    if not names:
        return []
    return [_normalize_key(name) for name in names if name]


def backfill_run(session, run: Run, dry_run: bool) -> tuple[int, int, int]:
    session_id = run.session_id
    session.query(EventEntity).filter_by(run_id=run.id, session_id=session_id).delete()
    session.query(SceneEntity).filter_by(run_id=run.id, session_id=session_id).delete()
    session.query(ThreadEntity).filter_by(run_id=run.id, session_id=session_id).delete()

    name_map = _entity_name_map(session, run.campaign_id)
    utterance_map = _utterance_to_entities(session, run.id, session_id)

    event_links: list[EventEntity] = []
    events = session.query(Event).filter_by(run_id=run.id, session_id=session_id).all()
    for event in events:
        evidence_ids = _entity_ids_from_evidence(event.evidence, utterance_map)
        linked_ids = set(evidence_ids)
        for token in _normalize_entity_tokens(event.entities or []):
            entity_id = name_map.get(token)
            if entity_id:
                linked_ids.add(entity_id)
        for entity_id in linked_ids:
            role = "evidence" if entity_id in evidence_ids else "entity_ref"
            event_links.append(
                EventEntity(
                    run_id=run.id,
                    session_id=session_id,
                    event_id=event.id,
                    entity_id=entity_id,
                    role=role,
                    evidence=event.evidence,
                )
            )

    scene_links: list[SceneEntity] = []
    scenes = session.query(Scene).filter_by(run_id=run.id, session_id=session_id).all()
    for scene in scenes:
        evidence_ids = _entity_ids_from_evidence(scene.evidence, utterance_map)
        linked_ids = set(evidence_ids)
        for token in _normalize_entity_tokens(scene.participants or []):
            entity_id = name_map.get(token)
            if entity_id:
                linked_ids.add(entity_id)
        for entity_id in linked_ids:
            role = "evidence" if entity_id in evidence_ids else "participant"
            scene_links.append(
                SceneEntity(
                    run_id=run.id,
                    session_id=session_id,
                    scene_id=scene.id,
                    entity_id=entity_id,
                    role=role,
                    evidence=scene.evidence,
                )
            )

    thread_links: list[ThreadEntity] = []
    threads = session.query(Thread).filter_by(run_id=run.id, session_id=session_id).all()
    updates = session.query(ThreadUpdate).filter_by(run_id=run.id, session_id=session_id).all()
    updates_by_thread: dict[str, list[ThreadUpdate]] = {}
    for update in updates:
        updates_by_thread.setdefault(update.thread_id, []).append(update)
    for thread in threads:
        linked_ids = _entity_ids_from_evidence(thread.evidence, utterance_map)
        for update in updates_by_thread.get(thread.id, []):
            linked_ids |= _entity_ids_from_evidence(update.evidence, utterance_map)
        for entity_id in linked_ids:
            thread_links.append(
                ThreadEntity(
                    run_id=run.id,
                    session_id=session_id,
                    thread_id=thread.id,
                    entity_id=entity_id,
                    role="evidence",
                    evidence=thread.evidence,
                )
            )

    if not dry_run:
        if event_links:
            session.add_all(event_links)
        if scene_links:
            session.add_all(scene_links)
        if thread_links:
            session.add_all(thread_links)

    return len(event_links), len(scene_links), len(thread_links)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", dest="campaign", default=None)
    parser.add_argument("--session", dest="session", default=None)
    parser.add_argument("--run", dest="run", default=None)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session() as session:
        query = session.query(Run)
        if args.run:
            query = query.filter(Run.id == args.run)
        if args.session:
            query = query.filter(Run.session_id == args.session)
        if args.campaign:
            query = query.filter(Run.campaign_id == args.campaign)
        runs = query.order_by(Run.created_at.asc()).all()
        if not runs:
            print("No runs found for backfill.")
            return
        for run in runs:
            event_count, scene_count, thread_count = backfill_run(
                session, run, args.dry_run
            )
            print(
                f"run={run.id} session={run.session_id} events={event_count} scenes={scene_count} threads={thread_count}"
            )
        if args.dry_run and args.commit:
            print("Refusing to commit with --dry-run.")
            session.rollback()
        elif args.commit:
            session.commit()
        else:
            session.rollback()


if __name__ == "__main__":
    main()
