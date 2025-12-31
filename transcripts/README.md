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

If you have multiple variants, place non-canonical versions in `extras/`.
