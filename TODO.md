# Project TODO

## Current implementation recap
- End-to-end pipeline works (local runner + Temporal workflow): ingest → extract → persist → resolve → plan → write → render DOCX.
- Canonical inputs under `transcripts/**` with optional `campaign.json` for participant/character mapping.
- DB schema covers campaigns, sessions, participants, runs, utterances, mentions, entities, scenes, events, threads, quotes, artifacts, and LLM call provenance (success + failure).
- Read APIs available for campaigns/sessions, entities, scenes, events, threads, quotes, summaries, artifacts, campaign search, and a session bundle endpoint.
- DSPy eval harness in place with legacy analysis docs used to bootstrap a rough gold set; supports NPC/location/item/faction tasks.

## Next commit plan (near-term)
1) Extraction quality pass vs legacy analysis docs  
   - Compare extracted NPCs/locations/threads/events to `legacy/` analysis docs.  
   - Adjust `prompts/extract_session_facts_v1.txt` to close gaps.

2) Quote coverage tuning  
   - Increase clean_text coverage, keep in-character lines only.  
   - Add a prompt reminder to avoid DM framing ("she says") inside quotes.

3) Optional evidence repair step  
   - If evidence gaps persist, add a targeted LLM repair activity for missing spans.  
   - Gate by feature flag to keep costs low.

## Recently completed
- Entity-centric API endpoints (`/entities/{entity_id}/mentions|quotes|events`)
- Session bundle endpoint (`/sessions/{session_id}/bundle`) for UI call reduction
- Quote clean_text support with display_text for UI
- Quality report extraction + inspect_run output (evidence coverage, LLM call stats)
- Thread update evidence includes related event IDs
- Evidence clamping + mention repair/drop for invalid spans
- UI quest journal + campaign codex panels (campaign-wide threads/entities)

## Mid-term
- Add correction loop (rename/merge entities, mark false positives, lock canonical names).  
- Add Postgres search indexes + rank (GIN/TSVECTOR) and return score in API.  
- Add eval dashboard output (CSV + summary tables) to track prompt versions over time.

## Later
- Ingest external sources (D&D Beyond sheets, dice rolls) once data formats are defined.  
- UI integration and multi-tenant hosting considerations.
