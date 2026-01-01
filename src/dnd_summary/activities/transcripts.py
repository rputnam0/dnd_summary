from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from temporalio import activity

from dnd_summary.campaign_config import CampaignConfig, load_campaign_config, speaker_alias_map
from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.external_sources import (
    find_character_sheet_paths,
    find_rolls_path,
    load_character_sheet,
    parse_rolls_jsonl,
)
from dnd_summary.models import (
    Campaign,
    CharacterSheetSnapshot,
    DiceRoll,
    Entity,
    EntityAlias,
    Participant,
    ParticipantCharacter,
    Run,
    Session,
    Utterance,
)
from dnd_summary.transcripts import parse_transcript


@dataclass(frozen=True)
class TranscriptSource:
    format: Literal["jsonl", "txt"]
    path: str


def _find_transcript_source(session_dir: Path) -> TranscriptSource:
    preferred_jsonl = session_dir / "transcript.jsonl"
    if preferred_jsonl.exists():
        return TranscriptSource(format="jsonl", path=str(preferred_jsonl))

    preferred_txt = session_dir / "transcript.txt"
    if preferred_txt.exists():
        return TranscriptSource(format="txt", path=str(preferred_txt))

    # Back-compat fallback for pre-migrated directories.
    jsonl_files = sorted(
        session_dir.glob("*.jsonl"),
        key=lambda p: (p.stat().st_size, p.stat().st_mtime),
        reverse=True,
    )
    if jsonl_files:
        return TranscriptSource(format="jsonl", path=str(jsonl_files[0]))

    txt_files = sorted(
        session_dir.glob("*.txt"),
        key=lambda p: (p.stat().st_size, p.stat().st_mtime),
        reverse=True,
    )
    if txt_files:
        return TranscriptSource(format="txt", path=str(txt_files[0]))

    raise FileNotFoundError(f"No transcript found in {session_dir}")


def _apply_campaign_metadata(campaign: Campaign, config: CampaignConfig | None) -> None:
    if not config:
        return
    if config.name:
        campaign.name = config.name
    if config.system:
        campaign.system = config.system


def _ensure_participants(
    session,
    campaign: Campaign,
    config: CampaignConfig | None,
) -> dict[str, Participant]:
    participants: dict[str, Participant] = {}
    if not config or not config.participants:
        return participants

    for entry in config.participants:
        display_name = entry.display_name.strip()
        if not display_name:
            continue
        participant = (
            session.query(Participant)
            .filter_by(campaign_id=campaign.id, display_name=display_name)
            .one_or_none()
        )
        if not participant:
            participant = Participant(
                campaign_id=campaign.id,
                display_name=display_name,
            )
            session.add(participant)
            session.flush()
        if entry.role and not participant.role:
            participant.role = entry.role
        if entry.speaker_aliases:
            participant.speaker_aliases = entry.speaker_aliases
        participants[display_name] = participant

        if entry.character and entry.character.name:
            character_name = entry.character.name.strip()
            entity = (
                session.query(Entity)
                .filter_by(
                    campaign_id=campaign.id,
                    entity_type="character",
                    canonical_name=character_name,
                )
                .one_or_none()
            )
            if not entity:
                entity = Entity(
                    campaign_id=campaign.id,
                    canonical_name=character_name,
                    entity_type="character",
                    character_kind=entry.character.kind,
                    owner_participant_id=participant.id,
                )
                session.add(entity)
                session.flush()

            for alias in entry.character.aliases or []:
                alias = alias.strip()
                if not alias:
                    continue
                exists = (
                    session.query(EntityAlias)
                    .filter_by(entity_id=entity.id, alias=alias)
                    .one_or_none()
                )
                if not exists:
                    session.add(EntityAlias(entity_id=entity.id, alias=alias))

            link = (
                session.query(ParticipantCharacter)
                .filter_by(participant_id=participant.id, entity_id=entity.id)
                .one_or_none()
            )
            if not link:
                session.add(
                    ParticipantCharacter(
                        participant_id=participant.id,
                        entity_id=entity.id,
                    )
                )

    return participants


def _relative_source_path(path: Path) -> str:
    base = Path(settings.transcripts_root).resolve()
    try:
        return str(path.resolve().relative_to(base))
    except ValueError:
        return str(path.resolve())


def _ingest_character_sheets(
    session,
    campaign: Campaign,
    session_obj: Session,
    session_dir: Path,
) -> dict:
    sheets = find_character_sheet_paths(session_dir)
    if not sheets:
        return {"count": 0, "errors": []}

    errors: list[str] = []
    stored = 0
    for sheet_path in sheets:
        try:
            payload = load_character_sheet(sheet_path)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"{sheet_path.name}: {exc}")
            continue
        source_hash = sha256(sheet_path.read_bytes()).hexdigest()
        character_slug = sheet_path.stem
        if not character_slug:
            errors.append(f"{sheet_path.name}: missing character slug")
            continue
        existing = (
            session.query(CharacterSheetSnapshot)
            .filter_by(session_id=session_obj.id, character_slug=character_slug)
            .all()
        )
        if any(record.source_hash == source_hash for record in existing):
            continue
        if existing:
            session.query(CharacterSheetSnapshot).filter_by(
                session_id=session_obj.id,
                character_slug=character_slug,
            ).delete(synchronize_session=False)
        character_name = payload.get("name") if isinstance(payload, dict) else None
        snapshot = CharacterSheetSnapshot(
            campaign_id=campaign.id,
            session_id=session_obj.id,
            character_slug=character_slug,
            character_name=character_name if isinstance(character_name, str) else None,
            source_path=_relative_source_path(sheet_path),
            source_hash=source_hash,
            payload=payload,
            created_at=datetime.utcnow(),
        )
        session.add(snapshot)
        stored += 1

    return {"count": stored, "errors": errors}


def _align_roll_to_utterance(roll_ms: int, utterances: list[Utterance]) -> str | None:
    if not utterances:
        return None
    best_id = None
    best_distance = None
    for utt in utterances:
        if utt.start_ms <= roll_ms <= utt.end_ms:
            return utt.id
        distance = min(abs(roll_ms - utt.start_ms), abs(roll_ms - utt.end_ms))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_id = utt.id
    return best_id


def _ingest_dice_rolls(
    session,
    campaign: Campaign,
    session_obj: Session,
    session_dir: Path,
    utterances: list[Utterance],
) -> dict:
    rolls_path = find_rolls_path(session_dir)
    if not rolls_path:
        return {"count": 0, "errors": []}

    source_hash = sha256(rolls_path.read_bytes()).hexdigest()
    source_path = _relative_source_path(rolls_path)
    existing = (
        session.query(DiceRoll)
        .filter_by(session_id=session_obj.id, source_path=source_path)
        .first()
    )
    if existing and existing.source_hash == source_hash:
        existing_rolls = (
            session.query(DiceRoll)
            .filter_by(session_id=session_obj.id, source_path=source_path)
            .order_by(DiceRoll.roll_index.asc())
            .all()
        )
        for roll in existing_rolls:
            roll.utterance_id = _align_roll_to_utterance(roll.t_ms, utterances)
        return {"count": 0, "errors": []}
    if existing:
        session.query(DiceRoll).filter_by(
            session_id=session_obj.id,
            source_path=source_path,
        ).delete(synchronize_session=False)

    rolls, errors = parse_rolls_jsonl(rolls_path)
    for roll in rolls:
        utterance_id = _align_roll_to_utterance(roll.t_ms, utterances)
        session.add(
            DiceRoll(
                campaign_id=campaign.id,
                session_id=session_obj.id,
                utterance_id=utterance_id,
                source_path=source_path,
                source_hash=source_hash,
                roll_index=roll.line_number,
                t_ms=roll.t_ms,
                character_name=roll.character if isinstance(roll.character, str) else None,
                kind=roll.kind,
                expression=roll.expression if isinstance(roll.expression, str) else None,
                total=roll.total,
                detail=roll.detail,
                created_at=datetime.utcnow(),
            )
        )

    return {"count": len(rolls), "errors": errors}


@activity.defn
async def ingest_transcript_activity(payload: dict) -> dict:
    """Locate the best transcript artifact for a session.

    v0: just discovers the canonical transcript file and returns its path.
    Next: parse utterances and persist to Postgres.
    """
    campaign_slug = payload["campaign_slug"]
    session_slug = payload["session_slug"]

    session_dir = (
        Path(settings.transcripts_root)
        / "campaigns"
        / campaign_slug
        / "sessions"
        / session_slug
    )
    src = _find_transcript_source(session_dir)
    transcript_path = Path(src.path)

    transcript_hash = sha256(transcript_path.read_bytes()).hexdigest()
    utterances = parse_transcript(transcript_path)
    config = load_campaign_config(campaign_slug)
    alias_map = speaker_alias_map(config)

    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).one_or_none()
        if not campaign:
            campaign = Campaign(slug=campaign_slug, name=campaign_slug.replace("_", " ").title())
            session.add(campaign)
            session.flush()
        _apply_campaign_metadata(campaign, config)

        session_obj = (
            session.query(Session)
            .filter_by(campaign_id=campaign.id, slug=session_slug)
            .one_or_none()
        )
        if not session_obj:
            session_number = None
            if session_slug.startswith("session_"):
                try:
                    session_number = int(session_slug.split("_")[1])
                except (ValueError, IndexError):
                    session_number = None
            session_obj = Session(
                campaign_id=campaign.id,
                slug=session_slug,
                session_number=session_number,
            )
            session.add(session_obj)
            session.flush()

        existing_run = (
            session.query(Run)
            .filter_by(session_id=session_obj.id, transcript_hash=transcript_hash)
            .first()
        )
        existing_count = (
            session.query(Utterance)
            .filter_by(session_id=session_obj.id)
            .count()
        )

        run = Run(
            campaign_id=campaign.id,
            session_id=session_obj.id,
            transcript_hash=transcript_hash,
            status="running",
        )
        session.add(run)
        session.flush()

        participants = _ensure_participants(session, campaign, config)
        for utt in utterances:
            speaker_display = alias_map.get(utt.speaker, utt.speaker)
            if speaker_display not in participants:
                participant = (
                    session.query(Participant)
                    .filter_by(campaign_id=campaign.id, display_name=speaker_display)
                    .one_or_none()
                )
                if not participant:
                    participant = Participant(
                        campaign_id=campaign.id,
                        display_name=speaker_display,
                    )
                    session.add(participant)
                    session.flush()
                participants[speaker_display] = participant

        utterances_reused = False
        utterances_deleted = 0
        if existing_count and existing_run:
            utterances_reused = True
        else:
            if existing_count:
                utterances_deleted = existing_count
                session.query(Utterance).filter_by(
                    session_id=session_obj.id
                ).delete(synchronize_session=False)
            utterance_rows = [
                Utterance(
                    session_id=session_obj.id,
                    participant_id=participants[alias_map.get(utt.speaker, utt.speaker)].id,
                    start_ms=utt.start_ms,
                    end_ms=utt.end_ms,
                    speaker_raw=utt.speaker_raw or utt.speaker,
                    text=utt.text,
                )
                for utt in utterances
            ]
            session.add_all(utterance_rows)

        run.status = "completed"
        run.finished_at = datetime.utcnow()

        sheets_result = _ingest_character_sheets(session, campaign, session_obj, session_dir)
        utterance_rows = (
            session.query(Utterance)
            .filter_by(session_id=session_obj.id)
            .order_by(Utterance.start_ms.asc(), Utterance.id.asc())
            .all()
        )
        rolls_result = _ingest_dice_rolls(
            session,
            campaign,
            session_obj,
            session_dir,
            utterance_rows,
        )
        session.flush()

    return {
        "campaign_slug": campaign_slug,
        "session_slug": session_slug,
        "transcript": src.__dict__,
        "utterances": len(utterances),
        "utterances_reused": utterances_reused,
        "utterances_deleted": utterances_deleted,
        "transcript_hash": transcript_hash,
        "run_id": run.id,
        "session_id": session_obj.id,
        "campaign_id": campaign.id,
        "character_sheets": sheets_result,
        "dice_rolls": rolls_result,
    }
