from __future__ import annotations

from temporalio import activity
from sqlalchemy import func

from dnd_summary.db import ENGINE, get_session
from dnd_summary.models import Base, Entity, EntityAlias, EntityMention, Mention, Run


def _normalize_key(text: str) -> str:
    return " ".join(text.lower().split())


@activity.defn
async def resolve_entities_activity(payload: dict) -> dict:
    Base.metadata.create_all(bind=ENGINE)
    run_id = payload["run_id"]
    session_id = payload["session_id"]

    with get_session() as session:
        run = session.query(Run).filter_by(id=run_id).one()
        mentions = (
            session.query(Mention)
            .filter_by(run_id=run_id, session_id=session_id)
            .all()
        )

        created = 0
        linked = 0
        aliases_added = 0
        for mention in mentions:
            key = _normalize_key(mention.text)
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

    return {
        "run_id": run_id,
        "session_id": session_id,
        "entities_created": created,
        "mentions_linked": linked,
        "aliases_added": aliases_added,
    }
