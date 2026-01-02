# Project TODO

## MVP Close-Out Plan (finish PRD v0)
Definition of Done (all must pass):
- PRD MVP criteria in `docs/PRD.md` are met and verified.
- `uv run pytest` passes.
- Manual UI smoke checks recorded (run start/progress, current run persistence, evidence links).

Commit-sized TODO (in order):
1) Corrections inform extraction/resolve
   - Acceptance: corrections project into a canonical map used by extraction/resolution and summary inputs.
   - Acceptance: hidden/merged/renamed entities and thread status changes are honored in reruns.
   - Spec: see `docs/CORRECTIONS.md`.
   - Tests: add activity tests that inject corrections and assert outputs.
2) Summary variants + artifact switcher in UI
   - Acceptance: DM can toggle and download player/DM/hooks/NPC artifacts.
   - Tests: UI smoke check + API test for artifacts payload if needed.
3) Ask the campaign panel in UI
   - Acceptance: DM/player can submit a question and see evidence-cited answers.
   - Tests: API tests for `/ask` already exist or are added as needed.
4) User testing round 1
   - Acceptance: 5 DMs + 5 players complete `docs/USER_TESTING.md` task script; findings logged with fixes ranked.

MVP verification checklist (record results in the PRD or a release note):
- Create a session with required metadata, upload transcript, start a run, and see progress update to completion.
- Set current run, refresh the page, confirm the selection persists.
- Open evidence for a quote and confirm the highlighted text matches transcript content.
- Apply a redaction/spoiler and confirm the player view hides it.
- Ask the campaign returns an answer with citations.
- Export a session zip and delete the session; confirm it disappears from lists.

## Post-MVP Roadmap (feature branch: post-mvp-ui-polish)
Start after MVP close-out is complete. Each item is a PR-sized batch with clear acceptance.
1) IA and layout refresh (role-based views, collapsible panels, mobile polish)
   - Acceptance: DM and player paths are distinct; UI density is reduced without losing data.
2) Campaign config editor
   - Acceptance: DM can manage speaker mappings, participants, and PC links from the UI.
3) Session management polish
   - Acceptance: edit session title/date, compare runs, and view a change log of corrections.
4) Performance pass (bundle slicing, pagination, caching)
   - Acceptance: large sessions load without timeouts; bundle payloads are smaller by default.
5) Relationship and objective modeling
   - Acceptance: add relationships + thread objectives and expose them in the UI.
6) External sources UX
   - Acceptance: character sheets and dice rolls are visible in the session view with evidence.
7) DM prep pack + player share
   - Acceptance: "next session prep" panel + shareable player recap view.
8) User testing round 2
   - Acceptance: repeat task tests and close top UI regressions.

## Current implementation recap
- End-to-end pipeline works (local runner + Temporal workflow): ingest → extract → persist → resolve → plan → write → render DOCX.
- Canonical inputs under `transcripts/**` with optional `campaign.json` for participant/character mapping.
- DB schema covers campaigns, sessions, participants, runs, utterances, mentions, entities, scenes, events, threads, quotes, artifacts, and LLM call provenance (success + failure).
- Read APIs available for campaigns/sessions, entities, scenes, events, threads, quotes, summaries, artifacts, campaign search, and a session bundle endpoint.
- DSPy eval harness in place with legacy analysis docs used to bootstrap a rough gold set; supports NPC/location/item/faction tasks.
- Comprehensive pytest suite covers API, CLI, activities, parsing, and cache logic using in-memory SQLite and mocked external services.


## Recently completed
- Trust + provenance signals in UI (confidence + corrected badge)
- Data lifecycle controls in UI (export/delete session)
- Persist current run selection from UI (set current run + API tests)
- UI run controls + progress feed (start run + polling via run-status endpoint)
- UI session onboarding + transcript upload (session creation API, UI form, and tests)
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
- Player notes + bookmarks scoping fix for authenticated requests
- Comprehensive pytest suite for API/CLI/activities/parsing
- Embeddings storage + semantic retrieval + ask-campaign endpoint
- Summary variants (player/DM/hooks/NPC changes) + improved DOCX rendering
- External sources ingestion for character sheets + dice rolls with transcript alignment
- Shareable app compose services (api/worker) + .env example
- Evidence repair activity, resume-partial CLI, and cache verification tooling
- Admin metrics endpoints + structured logging defaults

## Archive: Completed Roadmap (commit-sized)

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

25) Commit: Spoiler controls (done)
   - Per-session “spoiler until session N” tagging for threads/entities/events; filter per player.
   - Acceptance: campaign stays playable for late-joining players.

### Phase 7: Real semantic recall (embeddings + rerank + grounded Q&A)
Model choices (local, well-documented path)
- Embedding model: BAAI/bge-m3
  - High-quality dense retrieval model suitable for both query→span retrieval and higher-level objects (scenes/entities).
  - Practical benefit: one model covers short spans and longer text (useful since you embed utterances/events/scenes/entities).
- Reranker: BAAI/bge-reranker-large
  - Cross-encoder reranker used for “rerank top-K candidates” after vector search.
  - Biggest quality improvement per unit effort for English-only corpora.

What’s already done (keep as-is)
26) Commit: Add embeddings storage + vector index (pgvector)
   - Store vectors for utterances/events/scenes/entities with versioning.
   - Acceptance: semantic search works even when exact terms differ.

27) Commit: Add semantic retrieval endpoint that always returns evidence spans
   - Return top matches with transcript-backed citations and confidence.
   - Acceptance: “Ask the campaign” can be built on top without hallucinated citations.

28) Commit: Add “Ask the campaign” Q&A endpoint (DM and player modes)
   - DM mode can use hidden context; player mode must respect spoiler/redaction filters.
   - Acceptance: answers include quoted evidence and links to timeline/scene context.

Updated Phase 7 additions (bite-size commits)
29) Commit: Add local HF embedding provider (bge-m3) (done)
   - Goal: replace the hash embedding provider for real runs while keeping hash for CI/tests.
   - Scope:
     - New provider in `src/dnd_summary/embeddings.py` (or `providers/embeddings_hf.py`)
     - Loads BAAI/bge-m3
     - GPU/CPU device selection
     - Batching + deterministic normalization
     - Config additions:
       - `EMBEDDING_PROVIDER=hf|hash`
       - `EMBEDDING_MODEL=BAAI/bge-m3`
       - `EMBEDDING_BATCH_SIZE`, `EMBEDDING_DEVICE`, `EMBEDDING_MAX_LENGTH`
   - Acceptance:
     - `build-embeddings <campaign>` runs locally and produces non-hash vectors.
     - Embeddings are stable between runs (same text → same vector).

30) Commit: Add embedding metadata + compatibility checks (done)
   - Goal: make re-indexing and migrations safe when you change models/settings.
   - Scope:
     - Ensure embeddings rows store (if not already): `model_name`, `provider`, `dims`, `normalize`, `text_hash`, `created_at`
     - Add “index compatibility check” in `embedding_index.py`:
       - Refuse to mix embeddings with different dims/model unless explicitly forced (`--rebuild`).
   - Acceptance:
     - Running `build-embeddings` on an already-indexed campaign does the right thing:
       - skip unchanged text
       - rebuild on model mismatch only when requested

31) Commit: Add reranker provider abstraction (local HF + test stub) (done)
   - Goal: introduce reranking without entangling it with endpoints.
   - Scope:
     - New module: `src/dnd_summary/rerank.py`
     - Interface: `rerank(query, candidates[{id, text, dense_score, evidence_span...}])`
     - Providers:
       - `HFRerankerProvider` (model=BAAI/bge-reranker-large, device, batch_size, max_length=512)
       - `HashRerankerProvider` for deterministic CI/unit tests
   - Acceptance:
     - Unit tests validate reranking deterministically with the hash provider.

32) Commit: Integrate reranking into `/semantic_retrieve` (done)
   - Goal: improve match quality while preserving “always returns evidence spans.”
   - Scope:
     - Retrieval flow becomes:
       - pgvector dense search returns `dense_top_k` candidates (e.g., 100)
       - Apply mode filters (player spoiler/redaction) and any structural filters
       - Rerank remaining candidates (top `rerank_top_k`, e.g., 50)
       - Return final k (e.g., 15)
     - Response payload adds:
       - `rerank_score`
       - `scores: {dense, rerank}`
     - Keep evidence spans and transcript citations unchanged.
   - Config:
     - `RERANK_ENABLED=true|false`
     - `RERANK_MODEL=BAAI/bge-reranker-large`
     - `SEMANTIC_DENSE_TOP_K`, `SEMANTIC_RERANK_TOP_K`, `SEMANTIC_FINAL_K`
   - Acceptance:
     - With rerank enabled, ordering changes on a known test set while evidence spans/citations remain valid.

33) Commit: Integrate reranking into `/ask` (DM/player-safe) (done)
   - Goal: ensure reranker never “sees” forbidden content in player mode.
   - Scope:
     - Enforce ordering: filter before rerank (player mode)
     - DM mode can include hidden context
     - Rerank only evidence-span texts (recommended) rather than whole scene blobs:
       - minimizes truncation issues (512-token reranker window)
       - improves precision for citations
   - Acceptance:
     - Player-mode regression test: DM-only evidence cannot influence reranked results.

34) Commit: CLI + docs updates for “production mode” (done)
   - Goal: make it easy to run locally with the new stack.
   - Scope:
     - Update `dnd-summary build-embeddings` to accept/print:
       - provider/model/device/batch/dims
     - Add `dnd-summary doctor` (optional but small) to validate:
       - pgvector extension present
       - embedding/rerank models load on GPU
       - index exists for campaign
     - Update README/runbook:
       - “Apply migration → build embeddings → verify semantic retrieve → ask”
   - Acceptance:
     - A clean “getting started” path produces high-quality retrieval locally.

35) Commit: Evaluation harness (small, pragmatic) (done)
   - Goal: prevent silent quality regressions.
   - Scope:
     - Add a tiny goldens file: `tests/data/retrieval_goldens.jsonl`
     - query → expected evidence span IDs (or “must include one of these”)
     - Tests assert:
       - top-N includes expected evidence
       - citations point to real transcript spans
       - rerank improves or matches baseline on a minimal set
   - Acceptance:
     - CI catches retrieval regressions when chunking, embeddings, or reranking changes.

Suggested default settings (local, RTX 5080-class)
- `EMBEDDING_PROVIDER=hf`
- `EMBEDDING_MODEL=BAAI/bge-m3`
- `EMBEDDING_DEVICE=cuda`
- `EMBEDDING_BATCH_SIZE=64`
- `RERANK_ENABLED=true`
- `RERANK_PROVIDER=hf`
- `RERANK_MODEL=BAAI/bge-reranker-large`
- `RERANK_DEVICE=cuda`
- `RERANK_BATCH_SIZE=32`
- `RERANK_MAX_LENGTH=512`
- `SEMANTIC_DENSE_TOP_K=100`
- `SEMANTIC_RERANK_TOP_K=50`
- `SEMANTIC_FINAL_K=15`

### Phase 8: Narrative outputs (more than one recap)
29) Commit: Summary variants (done)
   - Outputs: player recap, DM prep, “next session hooks”, “NPC roster changes”.
   - Acceptance: same run produces multiple artifacts, each grounded by evidence.

30) Commit: Improve DOCX rendering (structure + styling) (done)
   - Use headings, scene breaks, quote callouts, appendices for loot/quests.
   - Acceptance: exported doc is readable and consistently formatted.

### Phase 9: External sources (v1+ contract)
31) Commit: Define canonical file formats and DB tables for character sheets + dice logs (done)
   - Add schemas and ingestion stubs (no extraction changes yet).
   - Acceptance: pipeline can ingest and store these artifacts with provenance.

32) Commit: Align dice/roll events to transcript time and expose in UI (done)
   - Use timestamps when available; attach as evidence to combat events.
   - Acceptance: combat narration becomes mechanically accurate when logs exist.

### Phase 10: “Shareable app” ops work (still local-first)
33) Commit: Add an app service container (API + worker) and tighten Compose (done)
   - Separate services: api, worker, postgres, temporal, temporal-ui.
   - Acceptance: one `docker compose up` can run the full system.

34) Commit: Optional evidence repair activity (feature-flagged) (done)
   - Trigger only when quality thresholds fail (e.g., missing spans above a limit).
   - Acceptance: repair step is off by default and lowers missing-span counts when enabled.

35) Commit: Add “resume partial run” CLI command (done)
   - Allow resuming from persisted DB state (e.g., rerun summary plan/write/render only).
   - Acceptance: a `partial` run can be completed without re-running extraction/persist.

36) Commit: Add `.env.example` and tighten local setup docs (done)
   - Document required env vars and safe defaults for cache TTL + release flags.
   - Acceptance: a new clone can run `uv venv && uv pip install -e ".[dev]"` and `dnd-summary api`.

37) Commit: QA follow-up: ensure partial run status displays when summary fails (done)
   - Confirm UI/CLI surfaces `partial` status reliably.
   - Acceptance: `partial` status is visible without manual DB inspection.

38) Commit: Validate explicit transcript caching (if enabled) (done)
   - Confirm `llm_usage.cached_content_token_count` > 0 on repeated runs.
   - Acceptance: repeated runs show cache hits in usage logs.

39) Commit: Add observability + admin utilities (done)
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
