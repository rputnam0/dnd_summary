# Project TODO

## Current implementation recap
- End-to-end pipeline works (local runner + Temporal workflow): ingest → extract → persist → resolve → plan → write → render DOCX.
- Canonical inputs under `transcripts/**` with optional `campaign.json` for participant/character mapping.
- DB schema covers campaigns, sessions, participants, runs, utterances, mentions, entities, scenes, events, threads, quotes, artifacts, and LLM call provenance (success + failure).
- Read APIs available for campaigns/sessions, entities, scenes, events, threads, quotes, summaries, artifacts, and campaign search.
- DSPy eval harness in place with legacy analysis docs used to bootstrap a rough gold set; supports NPC/location/item/faction tasks.

## Next commit plan (near-term)
1) Entity-centric API endpoints  
   - Add `GET /entities/{entity_id}/mentions`, `/entities/{entity_id}/quotes`, `/entities/{entity_id}/events`  
   - Enables UI views like “all appearances of Baba Yaga” or “events involving X”.

2) Eval dataset cleanup + overrides  
   - Add `evals/overrides/*.json` for manual fixes (per session or per task).  
   - Update dataset builder to merge overrides and track `gold_source`.

3) Thread evidence enrichment  
   - Add optional event linkage in extraction schema (thread updates include `related_event_ids`).  
   - Use event evidence to populate thread mention/quote endpoints.

## Mid-term
- Add correction loop (rename/merge entities, mark false positives, lock canonical names).  
- Add Postgres search indexes + rank (GIN/TSVECTOR) and return score in API.  
- Add eval dashboard output (CSV + summary tables) to track prompt versions over time.

## Later
- Ingest external sources (D&D Beyond sheets, dice rolls) once data formats are defined.  
- UI integration and multi-tenant hosting considerations.
