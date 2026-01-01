from __future__ import annotations

import json

from dnd_summary.campaign_config import (
    character_map_from_config,
    load_campaign_config,
    speaker_alias_map,
)


def test_load_campaign_config_parses_participants(tmp_path, settings_overrides):
    settings_overrides(transcripts_root=str(tmp_path))
    campaign_dir = tmp_path / "campaigns" / "alpha"
    campaign_dir.mkdir(parents=True)
    payload = {
        "name": "Alpha Campaign",
        "system": "5e",
        "participants": [
            {
                "display_name": "Lia",
                "role": "player",
                "speaker_aliases": ["liah"],
                "character": {"name": "Lia Sun", "kind": "pc", "aliases": ["Sun"]},
            },
            {
                "display_name": "DM",
                "role": "dm",
            },
        ],
    }
    (campaign_dir / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    config = load_campaign_config("alpha")

    assert config is not None
    assert config.name == "Alpha Campaign"
    assert config.system == "5e"
    assert config.participants
    assert config.participants[0].display_name == "Lia"
    assert config.participants[0].character is not None
    assert config.participants[0].character.name == "Lia Sun"

    aliases = speaker_alias_map(config)
    assert aliases["liah"] == "Lia"
    assert aliases["Lia"] == "Lia"

    character_map = character_map_from_config(config)
    assert character_map["Lia"] == "Lia Sun"
    assert "DM" not in character_map
