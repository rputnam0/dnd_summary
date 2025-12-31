# Project TODO

## Current implementation recap
- End-to-end pipeline works (local runner + Temporal workflow): ingest → extract → persist → resolve → plan → write → render DOCX.
- Canonical inputs under `transcripts/**` with optional `campaign.json` for participant/character mapping.
- DB schema covers campaigns, sessions, participants, runs, utterances, mentions, entities, scenes, events, threads, quotes, artifacts, and LLM call provenance (success + failure).
- Read APIs available for campaigns/sessions, entities, scenes, events, threads, quotes, summaries, artifacts, campaign search, and a session bundle endpoint.
- DSPy eval harness in place with legacy analysis docs used to bootstrap a rough gold set; supports NPC/location/item/faction tasks.

## Next commit plan (near-term)
1) Re-run session_50 end-to-end once Gemini quota resets  
   - Validate mentions include locations/items referenced in events/threads.  
   - Confirm quote coverage stays >= min_quotes after cleaning/dedup.

2) Optional evidence repair step  
   - If evidence gaps persist, add a targeted LLM repair activity for missing spans.  
   - Gate by feature flag to keep costs low.

3) QA follow-up: ensure partial run status displays when summary fails
4) Validate explicit transcript caching (if enabled)  
   - Confirm llm_usage includes cached_content_token_count > 0 on repeated runs.

## Recently completed
- Entity-centric API endpoints (`/entities/{entity_id}/mentions|quotes|events`)
- Session bundle endpoint (`/sessions/{session_id}/bundle`) for UI call reduction
- Quote clean_text support with display_text for UI
- Quality report extraction + inspect_run output (evidence coverage, LLM call stats)
- Thread update evidence includes related event IDs
- Evidence clamping + mention repair/drop for invalid spans
- UI quest journal + campaign codex panels (campaign-wide threads/entities)
- Speakers list added to extraction prompt; mentions checklist tightened
- Quote merge threshold adjusted + prompt updates to avoid DM narration
- Quote dedupe in persist step + quote fallback threshold raised
- Run status updates (completed/failed) + API prefers completed runs
- LLM retry/backoff for 429/5xx errors
- Partial run status for summary failures + UI messaging
- Run diagnostics panel (metrics + LLM calls)
- Explicit transcript cache support + token usage logging
- Idempotent transcript ingest for re-runs (reuse or replace utterances)
- Summary quote validation tightened to enforce quote bank grounding
- Mention span repair regex fixed for multi-token mentions

## Mid-term
- Add correction loop (rename/merge entities, mark false positives, lock canonical names).  
- Add Postgres search indexes + rank (GIN/TSVECTOR) and return score in API.
- Add Gemini Embeddings and incorporate symantic search over the campaing for a proper RAG database.  
- Add eval dashboard output (CSV + summary tables) to track prompt versions over time.

## Later
- Ingest external sources (D&D Beyond sheets, dice rolls) once data formats are defined.  
- UI integration and multi-tenant hosting considerations.
