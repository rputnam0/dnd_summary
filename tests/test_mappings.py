from __future__ import annotations

from dnd_summary.mappings import load_character_map
from dnd_summary.models import ParticipantCharacter
from tests.factories import create_campaign, create_entity, create_participant


def test_load_character_map_returns_player_characters(db_session):
    campaign = create_campaign(db_session)
    participant = create_participant(db_session, campaign=campaign, display_name="Lia")
    entity = create_entity(db_session, campaign=campaign, name="Lia Sun", entity_type="character")
    db_session.add(ParticipantCharacter(participant_id=participant.id, entity_id=entity.id))
    db_session.commit()

    mapping = load_character_map(db_session, campaign.id)

    assert mapping == {"Lia": "Lia Sun"}
