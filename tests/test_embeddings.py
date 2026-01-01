from __future__ import annotations

import pytest

from dnd_summary.embedding_index import build_embeddings_for_campaign
from dnd_summary.embeddings import cosine_similarity, embed_texts
from dnd_summary.models import Embedding
from tests.factories import (
    create_campaign,
    create_entity,
    create_event,
    create_participant,
    create_run,
    create_session,
    create_utterance,
)


def test_embed_texts_hash_is_deterministic(settings_overrides):
    settings_overrides(embedding_dimensions=8)
    first = embed_texts(["hello"])[0]
    second = embed_texts(["hello"])[0]

    assert first == second
    assert cosine_similarity(first, second) == pytest.approx(1.0)


def test_build_embeddings_for_campaign_creates_rows(db_session, settings_overrides):
    settings_overrides(embedding_dimensions=8)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utterance = create_utterance(db_session, session_obj=session_obj, participant=participant)
    create_entity(db_session, campaign=campaign, name="Goblin", entity_type="monster")
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Goblin ambush",
        evidence=[{"utterance_id": utterance.id, "char_start": 0, "char_end": 5}],
        entities=["Goblin"],
    )
    db_session.commit()

    stats = build_embeddings_for_campaign(db_session, campaign.id, include_all_runs=True)

    assert stats.created > 0
    rows = db_session.query(Embedding).filter_by(campaign_id=campaign.id).all()
    assert rows
