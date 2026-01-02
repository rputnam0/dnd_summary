from __future__ import annotations

import asyncio

from dnd_summary.activities.resolve import (
    _entity_ids_from_evidence,
    _normalize_entity_tokens,
    resolve_entities_activity,
)
from dnd_summary.corrections import normalize_key
from dnd_summary.models import Correction, Entity, EntityMention, EventEntity, SceneEntity, ThreadEntity
from tests.factories import (
    create_campaign,
    create_event,
    create_entity,
    create_entity_alias,
    create_mention,
    create_run,
    create_scene,
    create_session,
    create_thread,
    create_thread_update,
)


def test_normalize_key_trims_spaces():
    assert normalize_key("  Goblin King ") == "goblin king"


def test_entity_ids_from_evidence_collects_ids():
    lookup = {"utt-1": {"e1"}, "utt-2": {"e2"}}
    ids = _entity_ids_from_evidence(
        [{"utterance_id": "utt-1"}, {"utterance_id": "utt-2"}],
        lookup,
    )
    assert ids == {"e1", "e2"}


def test_normalize_entity_tokens():
    assert _normalize_entity_tokens([" Goblin ", ""]) == ["goblin"]


def test_resolve_entities_activity_links_entities(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    evidence = [{"utterance_id": "utt-1"}]
    create_mention(db_session, run=run, session_obj=session_obj, text="Goblin", evidence=evidence)
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Fight",
        evidence=evidence,
        entities=["Goblin"],
    )
    create_scene(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Scene",
        evidence=evidence,
        participants=["Goblin"],
    )
    thread = create_thread(db_session, run=run, session_obj=session_obj, evidence=evidence)
    create_thread_update(db_session, run=run, session_obj=session_obj, thread=thread, evidence=evidence)
    db_session.commit()

    result = asyncio.run(resolve_entities_activity({"run_id": run.id, "session_id": session_obj.id}))

    assert result["entities_created"] == 1
    entity = db_session.query(Entity).filter_by(campaign_id=campaign.id).one()
    assert entity.canonical_name == "Goblin"
    assert db_session.query(EntityMention).count() == 1
    assert db_session.query(EventEntity).count() >= 1
    assert db_session.query(SceneEntity).count() >= 1
    assert db_session.query(ThreadEntity).count() >= 1


def test_resolve_entities_applies_corrections(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    entity = create_entity(db_session, campaign=campaign, name="Alyx", entity_type="character")
    create_entity_alias(db_session, entity=entity, alias="Alix")
    db_session.add(
        Correction(
            campaign_id=campaign.id,
            session_id=None,
            target_type="entity",
            target_id=entity.id,
            action="entity_rename",
            payload={"name": "Alyxandra"},
            created_by="dm",
        )
    )
    hidden = create_entity(db_session, campaign=campaign, name="Secret", entity_type="character")
    db_session.add(
        Correction(
            campaign_id=campaign.id,
            session_id=None,
            target_type="entity",
            target_id=hidden.id,
            action="entity_hide",
            payload={},
            created_by="dm",
        )
    )
    evidence = [{"utterance_id": "utt-1"}]
    create_mention(db_session, run=run, session_obj=session_obj, text="Alix", evidence=evidence)
    create_mention(db_session, run=run, session_obj=session_obj, text="Secret", evidence=evidence)
    db_session.commit()

    result = asyncio.run(resolve_entities_activity({"run_id": run.id, "session_id": session_obj.id}))

    assert result["entities_created"] == 0
    mentions = db_session.query(EntityMention).all()
    assert len(mentions) == 1
    mention = db_session.query(EntityMention).first()
    assert mention.entity_id == entity.id
    updated = db_session.query(Entity).filter_by(id=entity.id).one()
    assert updated.canonical_name == "Alyx"
