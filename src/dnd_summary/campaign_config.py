from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dnd_summary.config import settings


@dataclass(frozen=True)
class CharacterConfig:
    name: str
    kind: str = "pc"
    aliases: list[str] | None = None


@dataclass(frozen=True)
class ParticipantConfig:
    display_name: str
    role: str | None = None
    speaker_aliases: list[str] | None = None
    character: CharacterConfig | None = None


@dataclass(frozen=True)
class CampaignConfig:
    name: str | None = None
    system: str | None = None
    participants: list[ParticipantConfig] | None = None


def _config_path(campaign_slug: str) -> Path:
    return (
        Path(settings.transcripts_root)
        / "campaigns"
        / campaign_slug
        / "campaign.json"
    )


def load_campaign_config(campaign_slug: str) -> CampaignConfig | None:
    path = _config_path(campaign_slug)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    participants: list[ParticipantConfig] = []
    for participant in payload.get("participants", []):
        character = participant.get("character")
        character_cfg = None
        if isinstance(character, dict) and character.get("name"):
            character_cfg = CharacterConfig(
                name=str(character["name"]),
                kind=str(character.get("kind") or "pc"),
                aliases=[str(a) for a in character.get("aliases", [])] or None,
            )
        participants.append(
            ParticipantConfig(
                display_name=str(participant.get("display_name") or "").strip(),
                role=participant.get("role"),
                speaker_aliases=[str(a) for a in participant.get("speaker_aliases", [])]
                or None,
                character=character_cfg,
            )
        )

    return CampaignConfig(
        name=payload.get("name"),
        system=payload.get("system"),
        participants=participants or None,
    )


def speaker_alias_map(config: CampaignConfig | None) -> dict[str, str]:
    if not config or not config.participants:
        return {}
    alias_map: dict[str, str] = {}
    for participant in config.participants:
        if not participant.display_name:
            continue
        alias_map[participant.display_name] = participant.display_name
        for alias in participant.speaker_aliases or []:
            alias_map[alias] = participant.display_name
    return alias_map


def character_map_from_config(config: CampaignConfig | None) -> dict[str, str]:
    if not config or not config.participants:
        return {}
    mapping: dict[str, str] = {}
    for participant in config.participants:
        if participant.character and participant.display_name:
            mapping[participant.display_name] = participant.character.name
    return mapping
