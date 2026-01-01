from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dnd_summary.activities.transcripts import (
    _ensure_participants,
    _find_transcript_source,
    ingest_transcript_activity,
)
from dnd_summary.campaign_config import CampaignConfig, CharacterConfig, ParticipantConfig
from dnd_summary.models import (
    Campaign,
    CharacterSheetSnapshot,
    DiceRoll,
    Entity,
    EntityAlias,
    Participant,
    ParticipantCharacter,
    Utterance,
)
from tests.factories import create_campaign


def test_find_transcript_source_prefers_canonical(tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    (session_dir / "other.jsonl").write_text("{}\n", encoding="utf-8")

    src = _find_transcript_source(session_dir)

    assert src.path.endswith("transcript.jsonl")


def test_ensure_participants_creates_entities(db_session):
    campaign = create_campaign(db_session)
    config = CampaignConfig(
        participants=[
            ParticipantConfig(
                display_name="Lia",
                role="player",
                speaker_aliases=["lia"],
                character=CharacterConfig(name="Lia Sun", kind="pc", aliases=["Sun"]),
            )
        ]
    )

    participants = _ensure_participants(db_session, campaign, config)
    db_session.commit()

    assert "Lia" in participants
    entity = (
        db_session.query(Entity)
        .filter_by(campaign_id=campaign.id, canonical_name="Lia Sun")
        .one()
    )
    alias = db_session.query(EntityAlias).filter_by(entity_id=entity.id, alias="Sun").one()
    link = (
        db_session.query(ParticipantCharacter)
        .filter_by(participant_id=participants["Lia"].id, entity_id=entity.id)
        .one()
    )
    assert alias.alias == "Sun"
    assert link.entity_id == entity.id


def test_ingest_transcript_activity_creates_run_and_utterances(tmp_path, db_session, settings_overrides):
    settings_overrides(transcripts_root=str(tmp_path))
    campaign_slug = "alpha"
    session_slug = "session_1"
    session_dir = tmp_path / "campaigns" / campaign_slug / "sessions" / session_slug
    session_dir.mkdir(parents=True)
    transcript_path = session_dir / "transcript.jsonl"
    transcript_path.write_text(
        json.dumps({"speaker": "Al", "start": 0.0, "end": 1.0, "text": "Hi"})
        + "\n"
        + json.dumps({"speaker": "Bob", "start": 1.0, "end": 2.0, "text": "Yo"})
        + "\n",
        encoding="utf-8",
    )

    config_payload = {
        "name": "Alpha Campaign",
        "participants": [
            {
                "display_name": "Alice",
                "speaker_aliases": ["Al"],
                "character": {"name": "Hero", "kind": "pc", "aliases": ["H"]},
            }
        ],
    }
    campaign_dir = tmp_path / "campaigns" / campaign_slug
    (campaign_dir / "campaign.json").write_text(json.dumps(config_payload), encoding="utf-8")

    result = asyncio.run(
        ingest_transcript_activity({"campaign_slug": campaign_slug, "session_slug": session_slug})
    )

    db_session.expire_all()
    assert result["utterances"] == 2
    campaign = db_session.query(Campaign).filter_by(slug=campaign_slug).one()
    participants = (
        db_session.query(Participant).filter_by(campaign_id=campaign.id).order_by(Participant.display_name).all()
    )
    assert [p.display_name for p in participants] == ["Alice", "Bob"]
    utterances = db_session.query(Utterance).filter_by(session_id=result["session_id"]).all()
    assert len(utterances) == 2

    # Re-ingest reuses utterances when transcript hash matches.
    result_again = asyncio.run(
        ingest_transcript_activity({"campaign_slug": campaign_slug, "session_slug": session_slug})
    )
    assert result_again["utterances_reused"] is True


def test_ingest_transcript_activity_ingests_external_sources(
    tmp_path, db_session, settings_overrides
):
    settings_overrides(transcripts_root=str(tmp_path))
    campaign_slug = "alpha"
    session_slug = "session_2"
    session_dir = tmp_path / "campaigns" / campaign_slug / "sessions" / session_slug
    session_dir.mkdir(parents=True)
    (session_dir / "transcript.jsonl").write_text(
        json.dumps({"speaker": "Al", "start": 0.0, "end": 1.0, "text": "Hi"})
        + "\n",
        encoding="utf-8",
    )
    sheets_dir = session_dir / "character_sheets"
    sheets_dir.mkdir()
    (sheets_dir / "hero.json").write_text(
        json.dumps({"name": "Hero", "class": "Fighter"}),
        encoding="utf-8",
    )
    (session_dir / "rolls.jsonl").write_text(
        json.dumps(
            {
                "t_ms": 1000,
                "character": "Hero",
                "kind": "attack",
                "expression": "1d20+7",
                "total": 19,
                "detail": {"die": 12},
            }
        )
        + "\n"
        + json.dumps(
            {
                "t_ms": 1500,
                "character": "Hero",
                "kind": "damage",
                "expression": "1d8+4",
                "total": 10,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = asyncio.run(
        ingest_transcript_activity({"campaign_slug": campaign_slug, "session_slug": session_slug})
    )

    db_session.expire_all()
    snapshots = (
        db_session.query(CharacterSheetSnapshot)
        .filter_by(session_id=result["session_id"])
        .all()
    )
    assert len(snapshots) == 1
    assert snapshots[0].character_slug == "hero"
    assert snapshots[0].character_name == "Hero"
    rolls = (
        db_session.query(DiceRoll)
        .filter_by(session_id=result["session_id"])
        .order_by(DiceRoll.roll_index.asc())
        .all()
    )
    assert len(rolls) == 2
    assert rolls[0].t_ms == 1000
    assert rolls[0].character_name == "Hero"
    assert rolls[0].utterance_id is not None
