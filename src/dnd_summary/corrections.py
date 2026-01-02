from __future__ import annotations

from dataclasses import dataclass

from dnd_summary.models import Correction, Entity, EntityAlias, Thread


def normalize_key(text: str) -> str:
    return " ".join(text.lower().split())


def _load_corrections(session, campaign_id: str, session_id: str | None, target_type: str) -> list[Correction]:
    query = session.query(Correction).filter(
        Correction.campaign_id == campaign_id,
        Correction.target_type == target_type,
    )
    if session_id is not None:
        query = query.filter(
            (Correction.session_id.is_(None)) | (Correction.session_id == session_id)
        )
    else:
        query = query.filter(Correction.session_id.is_(None))
    return query.order_by(Correction.created_at.asc(), Correction.id.asc()).all()


@dataclass
class EntityCorrectionState:
    canonical_name_by_id: dict[str, str]
    alias_to_id: dict[str, str]
    hidden_ids: set[str]
    merge_map: dict[str, str]
    name_to_canonical: dict[str, str]
    hidden_names: set[str]

    def resolve_id(self, entity_id: str) -> str:
        seen = set()
        current = entity_id
        while current in self.merge_map and current not in seen:
            seen.add(current)
            current = self.merge_map[current]
        return current


def load_entity_correction_state(session, campaign_id: str, session_id: str | None) -> EntityCorrectionState:
    entities = session.query(Entity).filter_by(campaign_id=campaign_id).all()
    entity_ids = [entity.id for entity in entities]
    aliases = (
        session.query(EntityAlias)
        .filter(EntityAlias.entity_id.in_(entity_ids))
        .all()
        if entity_ids
        else []
    )

    canonical_name_by_id = {entity.id: entity.canonical_name for entity in entities}
    alias_to_id: dict[str, str] = {}
    for entity in entities:
        alias_to_id[normalize_key(entity.canonical_name)] = entity.id
    for alias in aliases:
        alias_to_id[normalize_key(alias.alias)] = alias.entity_id

    hidden_ids: set[str] = set()
    merge_map: dict[str, str] = {}

    corrections = _load_corrections(session, campaign_id, session_id, "entity")
    for correction in corrections:
        payload = correction.payload or {}
        if correction.action in ("entity_rename", "rename"):
            new_name = payload.get("name") or payload.get("canonical_name")
            if not new_name or correction.target_id not in canonical_name_by_id:
                continue
            old_name = canonical_name_by_id[correction.target_id]
            canonical_name_by_id[correction.target_id] = new_name
            alias_to_id[normalize_key(old_name)] = correction.target_id
            alias_to_id[normalize_key(new_name)] = correction.target_id
            continue
        if correction.action in ("entity_alias_add", "alias_add"):
            alias = payload.get("alias")
            if alias:
                alias_to_id[normalize_key(alias)] = correction.target_id
            continue
        if correction.action in ("entity_alias_remove", "alias_remove"):
            alias = payload.get("alias")
            if alias:
                key = normalize_key(alias)
                if alias_to_id.get(key) == correction.target_id:
                    alias_to_id.pop(key, None)
            continue
        if correction.action in ("entity_merge", "merge"):
            target_id = payload.get("into_id") or payload.get("target_id")
            if not target_id:
                continue
            merge_map[correction.target_id] = target_id
            hidden_ids.add(correction.target_id)
            continue
        if correction.action in ("entity_hide", "hide"):
            hidden_ids.add(correction.target_id)

    # Resolve merge chains and remap aliases.
    resolved_aliases: dict[str, str] = {}
    for key, entity_id in alias_to_id.items():
        resolved = entity_id
        seen = set()
        while resolved in merge_map and resolved not in seen:
            seen.add(resolved)
            resolved = merge_map[resolved]
        resolved_aliases[key] = resolved
    alias_to_id = resolved_aliases

    name_to_canonical: dict[str, str] = {}
    hidden_names: set[str] = set()
    for name_key, entity_id in alias_to_id.items():
        if entity_id in hidden_ids:
            hidden_names.add(name_key)
            continue
        canonical = canonical_name_by_id.get(entity_id)
        if canonical:
            name_to_canonical[name_key] = canonical
    for entity_id, name in canonical_name_by_id.items():
        key = normalize_key(name)
        if entity_id in hidden_ids:
            hidden_names.add(key)
            continue
        name_to_canonical.setdefault(key, name)

    return EntityCorrectionState(
        canonical_name_by_id=canonical_name_by_id,
        alias_to_id=alias_to_id,
        hidden_ids=hidden_ids,
        merge_map=merge_map,
        name_to_canonical=name_to_canonical,
        hidden_names=hidden_names,
    )


def apply_entity_corrections(facts, state: EntityCorrectionState) -> None:
    cleaned_mentions = []
    for mention in facts.mentions:
        key = normalize_key(mention.text or "")
        if key in state.hidden_names:
            continue
        canonical = state.name_to_canonical.get(key)
        if canonical:
            mention.text = canonical
        cleaned_mentions.append(mention)
    facts.mentions = cleaned_mentions

    for scene in facts.scenes:
        if not scene.participants:
            continue
        updated = []
        for participant in scene.participants:
            key = normalize_key(participant)
            if key in state.hidden_names:
                continue
            canonical = state.name_to_canonical.get(key, participant)
            updated.append(canonical)
        scene.participants = updated

    for event in facts.events:
        if not event.entities:
            continue
        updated = []
        for entity in event.entities:
            key = normalize_key(entity)
            if key in state.hidden_names:
                continue
            canonical = state.name_to_canonical.get(key, entity)
            updated.append(canonical)
        event.entities = updated


@dataclass
class ThreadCorrectionState:
    overrides: dict[str, dict[str, str]]
    hidden: set[str]
    merge_map: dict[str, str]

    def resolve_id(self, thread_id: str) -> str:
        seen = set()
        current = thread_id
        while current in self.merge_map and current not in seen:
            seen.add(current)
            current = self.merge_map[current]
        return current


def load_thread_correction_state(session, campaign_id: str, session_id: str | None) -> ThreadCorrectionState:
    corrections = _load_corrections(session, campaign_id, session_id, "thread")
    overrides: dict[str, dict[str, str]] = {}
    hidden: set[str] = set()
    merge_map: dict[str, str] = {}

    for correction in corrections:
        payload = correction.payload or {}
        thread = session.query(Thread).filter_by(id=correction.target_id).first()
        if not thread or not thread.campaign_thread_id:
            continue
        campaign_thread_id = thread.campaign_thread_id

        if correction.action in ("thread_status", "status_update"):
            status = payload.get("status")
            if status:
                overrides.setdefault(campaign_thread_id, {})["status"] = status
            continue
        if correction.action in ("thread_title", "thread_rename", "title_update"):
            title = payload.get("title") or payload.get("name")
            if title:
                overrides.setdefault(campaign_thread_id, {})["title"] = title
            continue
        if correction.action in ("thread_summary", "summary_update"):
            if "summary" in payload:
                overrides.setdefault(campaign_thread_id, {})["summary"] = payload.get("summary")
            continue
        if correction.action in ("thread_hide", "hide"):
            hidden.add(campaign_thread_id)
            continue
        if correction.action in ("thread_merge", "merge"):
            target_thread_id = payload.get("into_id") or payload.get("target_id")
            if not target_thread_id:
                continue
            target_thread = session.query(Thread).filter_by(id=target_thread_id).first()
            if target_thread and target_thread.campaign_thread_id:
                merge_map[campaign_thread_id] = target_thread.campaign_thread_id

    return ThreadCorrectionState(overrides=overrides, hidden=hidden, merge_map=merge_map)
