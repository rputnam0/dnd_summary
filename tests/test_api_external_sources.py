from __future__ import annotations

from datetime import datetime

from fastapi import status

from dnd_summary.models import CharacterSheetSnapshot, DiceRoll
from tests.factories import (
    create_campaign,
    create_participant,
    create_run,
    create_session,
    create_utterance,
)


def test_session_bundle_includes_external_sources(api_client, db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign, display_name="DM")
    utterance = create_utterance(
        db_session,
        session_obj=session_obj,
        participant=participant,
        start_ms=0,
        end_ms=1000,
        text="Rolls incoming.",
    )
    sheet = CharacterSheetSnapshot(
        campaign_id=campaign.id,
        session_id=session_obj.id,
        character_slug="hero",
        character_name="Hero",
        source_path="campaigns/alpha/sessions/session_1/character_sheets/hero.json",
        source_hash="abc123",
        payload={"name": "Hero", "class": "Fighter"},
        created_at=datetime.utcnow(),
    )
    roll = DiceRoll(
        campaign_id=campaign.id,
        session_id=session_obj.id,
        utterance_id=utterance.id,
        source_path="campaigns/alpha/sessions/session_1/rolls.jsonl",
        source_hash="def456",
        roll_index=1,
        t_ms=500,
        character_name="Hero",
        kind="attack",
        expression="1d20+7",
        total=19,
        detail={"die": 12},
        created_at=datetime.utcnow(),
    )
    db_session.add_all([sheet, roll])
    db_session.commit()

    response = api_client.get(f"/sessions/{session_obj.id}/bundle")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["character_sheets"][0]["character_slug"] == "hero"
    assert payload["dice_rolls"][0]["utterance_id"] == utterance.id
    assert payload["dice_rolls"][0]["evidence"][0]["utterance_id"] == utterance.id
