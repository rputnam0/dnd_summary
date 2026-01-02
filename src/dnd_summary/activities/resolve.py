from __future__ import annotations

from temporalio import activity
from sqlalchemy import func

from dnd_summary.db import get_session
from dnd_summary.corrections import EntityCorrectionState, load_entity_correction_state, normalize_key
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
from dnd_summary.run_steps import run_step


def _entity_name_map_from_corrections(state: EntityCorrectionState) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, entity_id in state.alias_to_id.items():
        if entity_id in state.hidden_ids:
            continue
        mapping[key] = entity_id
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
    return [normalize_key(name) for name in names if name]


@activity.defn
async def resolve_entities_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    session_id = payload["session_id"]

    with run_step(run_id, session_id, "resolve_entities"):
        with get_session() as session:
            run = session.query(Run).filter_by(id=run_id).one()
            correction_state = load_entity_correction_state(
                session, run.campaign_id, session_id
            )
            mentions = (
                session.query(Mention)
                .filter_by(run_id=run_id, session_id=session_id)
                .all()
            )

            created = 0
            linked = 0
            aliases_added = 0
            for mention in mentions:
                key = normalize_key(mention.text)
                if key in correction_state.hidden_names:
                    continue
                mapped_id = correction_state.alias_to_id.get(key)
                entity = None
                if mapped_id:
                    resolved = correction_state.resolve_id(mapped_id)
                    if resolved in correction_state.hidden_ids:
                        continue
                    entity = session.query(Entity).filter_by(id=resolved).one_or_none()
                    if entity and mention.text.strip():
                        mention.text = correction_state.canonical_name_by_id.get(
                            entity.id, mention.text
                        )
                if not entity:
                    entity = (
                        session.query(Entity)
                        .filter(
                            Entity.campaign_id == run.campaign_id,
                            Entity.entity_type == mention.entity_type,
                            func.lower(Entity.canonical_name) == key,
                        )
                        .one_or_none()
                    )
                if not entity:
                    entity = Entity(
                        campaign_id=run.campaign_id,
                        canonical_name=mention.text.strip() or key,
                        entity_type=mention.entity_type,
                        description=mention.description,
                    )
                    session.add(entity)
                    session.flush()
                    created += 1

                if mention.text.strip() and mention.text.strip().lower() != entity.canonical_name.lower():
                    alias = (
                        session.query(EntityAlias)
                        .filter_by(entity_id=entity.id, alias=mention.text.strip())
                        .one_or_none()
                    )
                    if not alias:
                        session.add(EntityAlias(entity_id=entity.id, alias=mention.text.strip()))
                        aliases_added += 1

                mention_link = EntityMention(
                    run_id=run_id,
                    session_id=session_id,
                    mention_id=mention.id,
                    entity_id=entity.id,
                )
                session.add(mention_link)
                linked += 1

            session.query(EventEntity).filter_by(run_id=run_id, session_id=session_id).delete()
            session.query(SceneEntity).filter_by(run_id=run_id, session_id=session_id).delete()
            session.query(ThreadEntity).filter_by(run_id=run_id, session_id=session_id).delete()

            name_map = _entity_name_map_from_corrections(correction_state)
            utterance_map = _utterance_to_entities(session, run_id, session_id)

            events = (
                session.query(Event)
                .filter_by(run_id=run_id, session_id=session_id)
                .all()
            )
            event_links: list[EventEntity] = []
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
                            run_id=run_id,
                            session_id=session_id,
                            event_id=event.id,
                            entity_id=entity_id,
                            role=role,
                            evidence=event.evidence,
                        )
                    )
            if event_links:
                session.add_all(event_links)

            scenes = (
                session.query(Scene)
                .filter_by(run_id=run_id, session_id=session_id)
                .all()
            )
            scene_links: list[SceneEntity] = []
            for scene in scenes:
                evidence_ids = _entity_ids_from_evidence(scene.evidence, utterance_map)
                linked_ids = set(evidence_ids)
                for token in _normalize_entity_tokens(scene.participants or []):
                    entity_id = name_map.get(token)
                    if entity_id:
                        linked_ids.add(entity_id)
                for entity_id in linked_ids:
                    role = (
                        "evidence"
                        if entity_id in evidence_ids
                        else "participant"
                    )
                    scene_links.append(
                        SceneEntity(
                            run_id=run_id,
                            session_id=session_id,
                            scene_id=scene.id,
                            entity_id=entity_id,
                            role=role,
                            evidence=scene.evidence,
                        )
                    )
            if scene_links:
                session.add_all(scene_links)

            threads = (
                session.query(Thread)
                .filter_by(run_id=run_id, session_id=session_id)
                .all()
            )
            updates = (
                session.query(ThreadUpdate)
                .filter_by(run_id=run_id, session_id=session_id)
                .all()
            )
            updates_by_thread: dict[str, list[ThreadUpdate]] = {}
            for update in updates:
                updates_by_thread.setdefault(update.thread_id, []).append(update)
            thread_links: list[ThreadEntity] = []
            for thread in threads:
                linked_ids = _entity_ids_from_evidence(thread.evidence, utterance_map)
                for update in updates_by_thread.get(thread.id, []):
                    linked_ids |= _entity_ids_from_evidence(update.evidence, utterance_map)
                for entity_id in linked_ids:
                    thread_links.append(
                        ThreadEntity(
                            run_id=run_id,
                            session_id=session_id,
                            thread_id=thread.id,
                            entity_id=entity_id,
                            role="evidence",
                            evidence=thread.evidence,
                        )
                    )
            if thread_links:
                session.add_all(thread_links)

        return {
            "run_id": run_id,
            "session_id": session_id,
            "entities_created": created,
            "mentions_linked": linked,
            "aliases_added": aliases_added,
        }
