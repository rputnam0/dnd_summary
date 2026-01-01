from __future__ import annotations

import asyncio

from dnd_summary.activities.resolve import (
    _entity_ids_from_evidence,
    _normalize_entity_tokens,
    _normalize_key,
    resolve_entities_activity,
)
from dnd_summary.models import Entity, EntityMention, EventEntity, SceneEntity, ThreadEntity
from tests.factories import (
    create_campaign,
    create_event,
    create_mention,
    create_run,
    create_scene,
    create_session,
    create_thread,
    create_thread_update,
)


def test_normalize_key_trims_spaces():
    assert _normalize_key("  Goblin King ") == "goblin king"


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
