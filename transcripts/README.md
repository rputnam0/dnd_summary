# transcripts/

Canonical ingest source for the pipeline.

This directory contains user data (transcripts, logs) and should not be committed. By default, `.gitignore`
ignores `transcripts/campaigns/` but keeps this README.

## Layout
`transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/`

Examples:
- `transcripts/campaigns/avarias/sessions/session_54/transcript.txt`
- `transcripts/campaigns/avarias/sessions/session_48/transcript.jsonl`

## Canonical file names
Prefer these names so the worker can discover inputs deterministically:
- `transcript.jsonl`
- `transcript.txt`
- `transcript.srt`
- `character_sheets/<character_slug>.json`
- `rolls.jsonl`

If you have multiple variants, place non-canonical versions in `extras/`.

## Campaign configuration (optional)
Define participants and PC character mappings in:
`transcripts/campaigns/<campaign_slug>/campaign.json`

Example:
```
{
  "name": "Avarias",
  "system": "5e",
  "participants": [
    {
      "display_name": "Jonathan",
      "role": "dm",
      "speaker_aliases": ["DM", "Dungeon Master"]
    },
    {
      "display_name": "Alice",
      "role": "player",
      "speaker_aliases": ["Alice (Track 1)"],
      "character": {
        "name": "Thorne",
        "kind": "pc",
        "aliases": ["Thorn"]
      }
    }
  ]
}
```
