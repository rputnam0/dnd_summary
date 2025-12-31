from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dnd_summary.models import Entity, Participant, ParticipantCharacter


def load_character_map(session: Session, campaign_id: str) -> dict[str, str]:
    stmt = (
        select(Participant.display_name, Entity.canonical_name)
        .select_from(ParticipantCharacter)
        .join(Participant, ParticipantCharacter.participant_id == Participant.id)
        .join(Entity, ParticipantCharacter.entity_id == Entity.id)
        .where(Participant.campaign_id == campaign_id)
    )
    rows = session.execute(stmt).all()
    return {row[0]: row[1] for row in rows}
