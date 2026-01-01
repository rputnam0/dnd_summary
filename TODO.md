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

## Roadmap (commit-sized)

This section is intentionally broken into small commits. Each item should be shippable and leave
the repo in a working state.

### Phase 0: Pipeline reliability + developer ergonomics (keep shipping)
1) Commit: Re-run `session_50` end-to-end and record baseline metrics
   - Capture: mention coverage, quote coverage, quality report, LLM usage.
   - Acceptance: run completes (or is `partial` with structured data) and metrics are written.

2) Commit: Add optional evidence repair activity (feature-flagged)
   - Trigger only when quality thresholds fail (e.g., missing spans above a limit).
   - Acceptance: repair step is off by default and lowers missing-span counts when enabled.

3) Commit: Add “resume partial run” CLI command
   - Allow resuming from persisted DB state (e.g., rerun summary plan/write/render only).
   - Acceptance: a `partial` run can be completed without re-running extraction/persist.

4) Commit: Add `.env.example` and tighten local setup docs
   - Document required env vars and safe defaults for cache TTL + release flags.
   - Acceptance: a new clone can run `uv venv && uv pip install -e ".[dev]"` and `dnd-summary api`.

### Phase 1: Backend foundations (migrations, indexes, canonical “current run”)
5) Commit: Add Alembic and a baseline migration for the existing schema (done)
   - Stop relying on runtime `metadata.create_all()` as the primary schema mechanism.
   - Acceptance: `alembic upgrade head` creates all tables on an empty DB.

6) Commit: Add Postgres indexes for UI + search hot paths (done)
   - Add GIN/TSVECTOR indexes for search and indexes for `(campaign_id, session_id, run_id)` joins.
   - Acceptance: search endpoints return identical results; query plans use indexes on Postgres.

7) Commit: Add `sessions.current_run_id` (explicit “current view”) (done)
   - Migration + API behavior: default to `current_run_id` if set, else latest completed.
   - Acceptance: selecting a run becomes persistent across reloads and across UI clients.

8) Commit: Add run-level step tracking for progress (done)
   - Minimal model: `run_steps` (step name, status, started_at, finished_at, error).
   - Acceptance: UI can show live-ish progress without reading Temporal internals.

### Phase 2: API enables a real dashboard workflow (not just “read what exists”)
9) Commit: Add API endpoint to upload/attach a transcript to a session (done)
   - Support `transcript.jsonl|txt|srt` upload into canonical `transcripts/**` layout.
   - Acceptance: UI can create/update a session’s transcript without manual filesystem work.

10) Commit: Add API endpoint to start a workflow run from the UI (done)
   - `POST /campaigns/{campaign}/sessions/{session}/runs` starts Temporal workflow (or local mode).
   - Acceptance: UI can start processing and receive `run_id`.

11) Commit: Add API endpoint to set the “current run” for a session (done)
   - `PUT /sessions/{session_id}/current-run` with validation and authorization hooks.
   - Acceptance: UI run selector persists and affects all bundle reads.

12) Commit: Add a “run status feed” endpoint (polling or SSE) (done)
   - Include: run status, step statuses, last LLM call, latest artifacts.
   - Acceptance: UI can update without page refresh while a run is executing.

13) Commit: Add delete/export primitives (local-first privacy controls) (done)
   - `DELETE /sessions/{id}` (DB + artifacts) and `GET /sessions/{id}/export` (zip).
   - Acceptance: users can remove sensitive data and export for backup.

### Phase 3: Data model upgrades for real interactivity (stop relying on name strings)
14) Commit: Add relational links for events/scenes/threads to entities (done)
   - New tables: `event_entities`, `scene_entities`, `thread_entities` (with role + evidence).
   - Acceptance: “show me everything about Baba Yaga” no longer depends on string matching.

15) Commit: Backfill entity links from existing runs (done)
   - Migration script that links by mention evidence + alias matching.
   - Acceptance: existing data becomes richer without re-running old sessions.

16) Commit: Make threads canonical across sessions (stable quest IDs) (done)
   - Add `campaign_threads` (canonical) + `thread_instances` (per run/session) or equivalent.
   - Acceptance: quest journal has stable IDs and reliable history across sessions.

### Phase 4: DM correction loop (turn extraction into trusted canonical state)
17) Commit: Add “corrections” tables (auditable overrides) (done)
   - Store edits as events: entity rename/merge/hide, alias add/remove; thread status/title merge; redactions.
   - Acceptance: corrections are persisted, reversible, and attributed (even if “local_user” initially).

18) Commit: Apply corrections in read paths (API + UI) (done)
   - All endpoints should reflect corrected names/merges/status; hidden items stay hidden.
   - Acceptance: the dashboard reflects curated truth consistently.

19) Commit: Add UI editing for Entity dossier (rename/alias/merge/hide) (done)
   - Include guardrails: show affected mentions/events, require confirmation.
   - Acceptance: a DM can clean up a campaign codex without touching the DB manually.

20) Commit: Add UI editing for Quest journal (status + summary + merge) (done)
   - Include evidence display + link to supporting events/quotes.
   - Acceptance: quest state becomes “video game reliable”.

21) Commit: Add redaction workflow (privacy + spoiler management) (done)
   - Redact utterances/quotes/notes; ensure exports respect redactions.
   - Acceptance: the UI can be player-facing without leaking private table talk.

### Phase 5: Auth + roles (DM vs player)
22) Commit: Add users + campaign memberships (dm/player) and session auth (done)
   - Minimal local auth: passwordless invite links or simple JWT with per-campaign membership.
   - Acceptance: DM-only routes are protected; players can read allowed views.

23) Commit: Role-gate sensitive endpoints and UI panels (done)
   - DM: edits, raw transcripts, redaction tools, “all runs” diagnostics.
   - Player: curated summary, quest journal (non-spoiler), codex (non-hidden).
   - Acceptance: same campaign can be safely shared.

### Phase 6: Player experience improvements (high retention)
24) Commit: Player notes + bookmarks (done)
   - Notes on sessions/entities/threads; bookmark quotes and events.
   - Acceptance: players can build their own “memory layer” without polluting canonical lore.

25) Commit: Spoiler controls
   - Per-session “spoiler until session N” tagging for threads/entities/events; filter per player.
   - Acceptance: campaign stays playable for late-joining players.

### Phase 7: Real semantic recall (embeddings + grounded Q&A)
26) Commit: Add embeddings storage + vector index (pgvector)
   - Store vectors for utterances/events/scenes/entities with versioning.
   - Acceptance: semantic search works even when exact terms differ.

27) Commit: Add semantic retrieval endpoint that always returns evidence spans
   - Return top matches with transcript-backed citations and confidence.
   - Acceptance: “Ask the campaign” can be built on top without hallucinated citations.

28) Commit: Add “Ask the campaign” Q&A endpoint (DM and player modes)
   - DM mode can use hidden context; player mode must respect spoiler/redaction filters.
   - Acceptance: answers include quoted evidence and links to timeline/scene context.

### Phase 8: Narrative outputs (more than one recap)
29) Commit: Summary variants
   - Outputs: player recap, DM prep, “next session hooks”, “NPC roster changes”.
   - Acceptance: same run produces multiple artifacts, each grounded by evidence.

30) Commit: Improve DOCX rendering (structure + styling)
   - Use headings, scene breaks, quote callouts, appendices for loot/quests.
   - Acceptance: exported doc is readable and consistently formatted.

### Phase 9: External sources (v1+ contract)
31) Commit: Define canonical file formats and DB tables for character sheets + dice logs
   - Add schemas and ingestion stubs (no extraction changes yet).
   - Acceptance: pipeline can ingest and store these artifacts with provenance.

32) Commit: Align dice/roll events to transcript time and expose in UI
   - Use timestamps when available; attach as evidence to combat events.
   - Acceptance: combat narration becomes mechanically accurate when logs exist.

### Phase 10: “Shareable app” ops work (still local-first)
33) Commit: Add an app service container (API + worker) and tighten Compose
   - Separate services: api, worker, postgres, temporal, temporal-ui.
   - Acceptance: one `docker compose up` can run the full system.

34) Commit: Add a minimal test suite for invariants
   - Evidence span validity, quote integrity, transcript parsing, corrections application.
   - Acceptance: `uv run pytest` passes and catches regressions in evidence contracts.

35) Commit: Add observability + admin utilities
   - Structured logs, basic metrics, and admin endpoints for data export/deletion.
   - Acceptance: debugging a bad run is possible without reading DB tables directly.

## Backend improvements (beyond UI)
- Schema lifecycle: Alembic migrations, safe evolutions, and Postgres indexes for search + bundles.
- “Canonical view”: explicit `current_run_id` per session plus a correction/override layer applied in reads.
- Better linking: replace name-string heuristics with join tables (entity↔event/scene/thread) and canonical
  threads across sessions (stable quest IDs).
- Run execution: step tracking/progress, resumable partial runs, optional evidence repair, and tighter
  idempotency/caching to control costs.
- Security + sharing: authentication, campaign membership roles, redactions, and spoiler-aware filtering.
- Retrieval: embeddings + vector index (pgvector) for semantic recall and grounded Q&A with evidence spans.
- Reliability: a small pytest suite for invariants (quote integrity, evidence spans, parsing) and basic
  observability/admin tools (export/delete, diagnostics).
