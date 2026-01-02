# Product Requirements Document (PRD)

## 1) Summary / Thesis
`dnd_summary` turns D&D session transcripts into:
- **A narrative session summary** (primary v0 outcome; DOCX export).
- **Structured campaign memory** (Postgres) suitable for UI browsing/search and future “memory tools” / automated DM assistance.

This is a hobby-first project designed to scale to broader audiences without a rewrite.

## 2) Primary v0 outcome
Given a transcript placed under `transcripts/**`, the system produces:
1) A high-quality narrative summary (DOCX).
2) A structured representation of the session in Postgres (entities/events/quotes/threads/etc.) with transcript-grounded evidence.

### v0 acceptance criteria (operational)
- Given `transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/transcript.{jsonl,txt,srt}`,
  starting a workflow produces:
  - a completed Run with persisted provenance (prompt/model versions + hashes)
  - a narrative summary DOCX artifact for that session
  - structured memory objects linked back to transcript evidence
- Every displayed quote in the DOCX has evidence and matches the referenced transcript span exactly.
- Re-running a session creates a new immutable Run; the UI can select which Run is “current”.

## 2.1 MVP scope (current target)
The MVP delivers a local-first DM companion + player aid loop:
- Session onboarding: create a session (slug + title + date required) and upload a transcript from the UI.
- DM can upload a transcript, start a run, monitor progress, and select the current Run in the UI.
- Evidence-first browsing: summary, scenes, events, quotes, threads, entities, and transcript evidence.
- DM curation: entity/thread corrections, redactions, spoiler tags, notes, and bookmarks.
- Player-safe views with role gating (no redactions or spoilers leaked).
- Search (lexical + semantic) and "Ask the campaign" for evidence-backed answers.
- Downloadable summary artifacts (DOCX/TXT) with provenance.
- Data lifecycle controls: export/delete session data from the UI.
- Trust signals: confidence and correction badges are visible where applicable.

## 2.2 MVP completion criteria (Definition of Done)
MVP is complete when all of the following are true:
- Pipeline: a canonical transcript produces a completed Run, summary DOCX, and structured memory.
- Evidence: all displayed quotes are exact substrings of transcript text with valid spans.
- Runs: UI can set and persist a "current run" per session.
- UI: DM can create a session (title/date required), upload a transcript, start a run, watch progress, and view evidence links.
- Roles: player view respects spoilers/redactions and hides DM-only panels.
- Corrections: known fixes (rename/merge/hide/status) persist and influence reruns.
- Privacy: export/delete session data works and is accessible in the UI.
- Variants: summary variants and Ask-the-campaign are usable in the UI.
- Search/Q&A: results include evidence or transcript spans; semantic answers cite sources.
- Tests: `uv run pytest` passes; new MVP behaviors have coverage or documented manual checks.

## 3) Scope
### In scope (v0)
- Multi-campaign organization (campaign boundary enforced in schema + retrieval).
- Transcript ingestion (JSONL/TXT/SRT) → normalized utterances with stable IDs.
- Single-pass extraction over the full transcript (no map/reduce chunking by default).
- Evidence-first data model (quotes and displayed facts are auditable).
- Temporal-orchestrated pipeline (retries, partial reruns, provenance, reprocessing).

### Out of scope (v0)
- Image generation execution (store scene candidates; make it pluggable later).
- Perfect single-track diarization (Discord multi-track is primary supported input).
- Hosted auth/permissions (define the model; implement later).

## 4) Personas and roles
- **DM (v0 buyer)**: runs pipeline, curates canonical state, may approve/correct extracted facts.
- **Player (v0 reader + lightweight editor)**: consumes summaries; may correct names/aliases and personal-character details.
- **Admin (future hosting)**: manages users, tenancy, retention, exports.

## 5) Glossary / Definitions
- **Campaign**: a distinct world/storyline. Hard isolation boundary for data and retrieval.
- **Session**: one play session within a campaign.
- **Participant (Player)**: a real-world speaker/voice track (e.g., “Alice”, “DM Jonathan”).
- **Character**: an in-world persona (PC or NPC). Summaries and UI refer to characters, not players.
- **Transcript**: the raw text output from transcription (JSONL/TXT/SRT).
- **Utterance**: a timestamped unit of transcript speech: speaker + start/end + text.
- **Evidence**: a pointer into transcript reality used to justify extracted objects.
- **Mention**: a raw reference to a thing in the transcript (string + evidence) before canonical resolution.
- **Entity**: a canonical object in campaign memory (character/npc, location, item, faction, etc.).
- **Scene**: a contiguous time range capturing a coherent slice of play (for UI + narrative structure).
- **Atomic event**: a typed, query-friendly event within a scene (e.g., “item acquired”, “quest advanced”).
- **Thread / Quest**: a persistent plotline tracked like a “video game quest journal”.
- **Run**: one execution of the processing pipeline for a session (prompt/model/versioned outputs).

## 6) Inputs
### 6.1 Canonical input layout
Transcripts are discovered under:
`transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/`

Canonical file names (preferred):
- `transcript.jsonl`
- `transcript.txt`
- `transcript.srt`

Additional files may exist under `extras/` and are not used unless configured.

### 6.2 Supported transcript formats (v0)
**A) JSONL (`transcript.jsonl`)**
- One JSON object per line.
- Required fields:
  - `start` (seconds; float)
  - `end` (seconds; float)
  - `speaker` (string; may be a track label or display name)
  - `text` (string)
- Optional fields:
  - `file` (source audio chunk/track)
  - `speaker_raw` (if present, stored as-is)

**B) TXT (`transcript.txt`)**
- One utterance per line, minimum structure:
  - `<speaker> <HH:MM:SS> <text>`
- Start time is required; end time is derived from the next utterance start (or session end).

**C) SRT (`transcript.srt`)**
- Timestamp ranges are used.
- Speaker attribution may be missing; if so, speaker is `unknown`.

### 6.3 Speaker identity and character mapping (v0)
- The transcript speaker is mapped to a **Participant** via campaign config (speaker mapping / aliases).
- **Participants are distinct from Characters.**
- For PCs, a Participant may map to exactly one Character.
- DM is a Participant; DM utterances may later be attributed to an NPC Character via human correction.

### 6.4 Optional secondary inputs (v1+; define now)
These reduce extraction burden and improve combat fidelity:
- **Character sheet snapshots** (e.g., D&D Beyond exports): PC stats, spells, inventory.
- **Dice roll / combat logs** (timestamped): rolls, damage totals, initiative order, saves.
- **Session metadata**: session title/date, attendance, episode notes.

The v1 contract is: if a log provides timestamps, the pipeline MUST align roll events to transcript time to support accurate combat narration.

Proposed file conventions (v1):
- Character sheets (per session snapshot):
  - `transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/character_sheets/<character_slug>.json`
  - Stored as `CharacterSheetSnapshot` records (raw JSON persisted for audit).
- Dice/roll log (timestamped JSONL):
  - `transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/rolls.jsonl`
  - One JSON object per line, recommended fields:
    - `t_ms` (int; relative to session start)
    - `character` (string; should match a Character canonical name or alias)
    - `kind` (`attack|damage|save|check|initiative|other`)
    - `expression` (string; e.g., `1d20+7`)
    - `total` (int)
    - `detail` (JSON; optional: individual dice, target AC, damage type, etc.)

## 7) Outputs
### 7.1 Narrative summary (v0)
- A single DOCX per session containing a narrative recap in the established style.
- Summary MUST be grounded by transcript evidence:
  - Any direct quote included MUST be traceable to evidence and exactly match transcript text (see Evidence Contract).

### 7.2 Structured campaign memory (v0)
For every processed session, the system stores:
- Entities encountered/mentioned (NPCs, locations, items, factions, PCs, monsters, deities as needed).
- Scenes + events (chronological backbone).
- Threads/quests and their session-linked updates.
- Quotes (verbatim; evidence-backed).
- Artifacts (DOCX outputs, extracted JSON, run metadata).

## 8) Campaign memory contract (spec)
The UI and future “memory tools” rely on these guarantees.

### 8.1 Core object types and minimum fields
**Campaign**
- `campaign_id`, `slug`, `name`, `system` (e.g., 5e), `created_at`
- Lore/style artifacts (versioned)

**Session**
- `session_id`, `campaign_id`, `slug`, `session_number` (optional), `title` (optional), `occurred_at` (optional)
- UI creation requires `title` and `occurred_at`, but legacy records may be missing them.

**Participant (Player)**
- `participant_id`, `campaign_id`, `display_name`, `role` (`dm|player|guest`)
- `speaker_aliases[]` (for transcript mapping)

**Utterance**
- `utterance_id`, `session_id`, `start_ms`, `end_ms`, `participant_id`, `speaker_raw`, `text`
- Optional: `mode` (`in_character|out_of_character|rules|table_talk|unknown`)

**Mention**
- `mention_id`, `session_id`, `kind` (entity-like), `text`, `evidence[]`, `confidence`

**Entity** (canonical)
- `entity_id`, `campaign_id`, `entity_type` (`character|location|item|faction|monster|deity|organization|other`)
- `canonical_name`, `aliases[]`, `description` (short), `status` (optional), `created_run_id`
- For `entity_type=character`:
  - `character_kind` (`pc|npc`)
  - Optional: `owner_participant_id` (PCs)

**Scene**
- `scene_id`, `session_id`, `start_ms`, `end_ms`, `title` (optional), `summary`, `location_entity_id` (optional)
- `participants[]` (characters/entities), `evidence[]`

**AtomicEvent**
- `event_id`, `scene_id` (optional), `session_id`, `start_ms`, `end_ms`, `event_type`, `summary`
- `entities[]` (participants), `evidence[]`, `confidence`

**Relationship** (derived + optionally curated)
- `relationship_id`, `campaign_id`, `from_entity_id`, `to_entity_id`, `relationship_type`
- `valid_from_session_id`, optional `valid_to_session_id`
- `confidence`, `evidence[]`

**Quote**
- `quote_id`, `session_id`, `utterance_id`, `char_start`, `char_end`
- `participant_id` (speaker), optional `as_character_id`, optional `scene_id`
- `evidence[]` (at minimum the span reference)

**Thread / Quest**
- `thread_id`, `campaign_id`, `title`, `kind` (`quest|mystery|personal_arc|faction_arc|other`)
- `status` (`proposed|active|blocked|completed|failed|abandoned`)
- `summary`, `created_session_id`, `last_updated_session_id`, `confidence`

**ThreadUpdate**
- `thread_update_id`, `thread_id`, `session_id`, `update_type`, `note`, `evidence[]`
- Optional: `related_event_ids[]`, `related_entity_ids[]`

**ThreadObjective** (optional in v0; recommended in v1)
- `objective_id`, `thread_id`, `description`, `status` (`todo|in_progress|blocked|done`)
- `evidence[]`, `confidence`

**CharacterSheetSnapshot** (v1+)
- `snapshot_id`, `campaign_id`, `character_entity_id`, `session_id` (optional), `source`
- `captured_at` (optional), `raw_payload` (stored as JSON), `hash`

**RollEvent** (v1+)
- `roll_id`, `campaign_id`, `session_id`, `t_ms` (relative to session start), `character_entity_id` (optional)
- `expression`, `total`, `detail` (JSON), `source`, `evidence[]` (optional)

**Run**
- `run_id`, `campaign_id`, `session_id`, `started_at`, `finished_at`, `status`
- `transcript_hash`, `pipeline_version`
- Per-step prompt/model versions and outputs

### 8.1.1 Atomic event taxonomy (v0 baseline)
Atomic events exist to make “quest dashboard” and “what happened to X?” queries reliable.
`event_type` MUST be one of:
- `combat`: combat encounter or meaningful combat beat (initiative, downed, kill, retreat)
- `social`: negotiation, interrogation, bargain, deception, persuasion
- `travel`: major movement between locations / time skip
- `discovery`: clue revealed, lore learned, secret uncovered
- `loot`: item gained/lost/used, attunement changes, artifact status changes
- `economy`: gold/treasure/resource deltas (who gained/lost, why)
- `relationship`: affiliation or relationship shift (ally/enemy/trust/debt)
- `thread_update`: quest/mystery progress (also recorded as ThreadUpdate)
- `rules`: level-ups, key rules/mechanics that materially changed outcomes
- `generic`: fallback when a beat doesn’t fit the above (discouraged)

### 8.2 Evidence contract (hard requirement)
Evidence is represented as one or more **EvidenceSpan** records:
- `utterance_id` (required)
- `char_start`, `char_end` (optional but preferred for quotes)
- `start_ms`, `end_ms` (derived from utterance; may be cached)
- `kind` (`quote|support|mention|other`)
- `confidence` (optional)

**Guarantees**
- Any Quote displayed to users MUST have at least one EvidenceSpan with char offsets.
- Quote text MUST be an exact substring of the referenced utterance text (byte-for-byte after newline normalization).
- Any “displayed fact” in the UI MUST have evidence (at least utterance-level).

### 8.3 Uncertainty and truth policy
The system distinguishes:
- **Extracted**: model-inferred objects (have evidence + confidence; may be wrong).
- **Confirmed** (v1+): human-validated facts that become canonical state.

UI defaults to showing extracted facts, but must present uncertainty (confidence + “model inferred” badge) unless confirmed.

## 9) Quest / thread model (quest dashboard foundation)
### 9.1 Definition
A **Thread** is a persistent plotline with:
- a stable identity across sessions
- a current status
- a history of updates with evidence

Threads may be:
- **Explicit** (quest given by an NPC / DM narration)
- **Implicit** (emergent mystery the party follows)

### 9.2 Guardrails (avoid invented quests)
- Threads MUST have evidence.
- Any Thread created with low confidence is marked `proposed` until a human promotes it to `active`.
- “Progress” is stored as `ThreadUpdate` notes linked to evidence/events, not as hallucinated objective completion.

### 9.3 States (v0)
- `proposed`, `active`, `blocked`, `completed`, `failed`, `abandoned`

### 9.4 Quest “video game dashboard” minimum (v0 data, v1 UI)
The system MUST be able to display, per campaign:
- Active threads (sorted by recency/importance)
- For each thread: current status, last updated session, key NPC/location associations
- A chronological list of ThreadUpdates with evidence links

## 10) Pipeline / workflow spec (Temporal)
### 10.1 Unit of idempotency
- Idempotency is defined per **(campaign, session, transcript_hash, prompt_version, model)**.
- A session may have multiple immutable **Runs**; one Run is marked “current” for UI outputs.

### 10.2 Partial failures
- If extraction succeeds but summary writing fails, the Run is retained as `partial` and can be resumed.
- Retries are per-activity with exponential backoff; non-deterministic steps store outputs for audit.

### 10.3 Chunking policy
Default behavior is full-transcript extraction.
Fallback to chunking is allowed only when the transcript exceeds a safe token budget; chunking MUST be overlapping and evidence-mergeable.

### 10.4 Data lifecycle and reprocessing policy
- Raw transcript artifacts are treated as immutable inputs for a given Run (addressed by `transcript_hash`).
- If a transcript is corrected, it produces a new `transcript_hash` and therefore a new Run.
- Derived artifacts (DOCX, extracted JSON) are tied to a Run and MUST be reproducible from stored provenance.
- Deletion policy (v1+): deleting a session removes utterances, derived objects, and artifacts for that session, and (optionally) deletes the on-disk transcript file.

## 11) Search and retrieval (v1 target)
Required modes:
- Entity search (“Baba Yaga”) → entity page with:
  - first/last seen sessions
  - related scenes/events
  - quote highlights (click to transcript evidence)
  - thread associations
- Thread/quest journal view (“video game dashboard”)
- Full-text search across utterances/events/notes (Postgres FTS)
- Optional embeddings later (semantic recall), but UI must be grounded in structured tables.

## 12) Human correction loop (v1 target)
Edits allowed:
- Rename entity / add alias
- Merge entities (alias resolution)
- Attribute DM speech “as NPC X” for selected quotes
- Correct thread status (proposed → active; active → completed, etc.)
- Mark false positives / redact content

Corrections are persisted as overrides and must influence subsequent runs (constraints for extraction and resolution).

### 12.1 Correction propagation policy
- Corrections are stored as auditable overrides and projected into a campaign "canonical map".
- The canonical map is used in extraction/resolve prompts so LLM outputs prefer canonical names.
- Resolution applies corrections deterministically:
  - **Rename**: new name becomes canonical; old name is treated as an alias.
  - **Merge**: merged entity IDs map to the target entity and never reappear in new runs.
  - **Hide**: hidden entities are excluded from new runs and UI lists.
  - **Thread updates**: status/title/summary overrides apply consistently across runs.
- Summary and UI outputs use corrected canonical names (not raw mention text).
- Player edits are stored as "pending" and only affect the canonical map after DM approval.
- The correction badge indicates a DM-approved correction.

## 13) Quality plan: metrics, thresholds, evaluation
### 13.1 Metrics
- **Quote integrity**: 100% for displayed quotes (hard requirement by design).
- **NPC/location/item extraction**: precision/recall measured on labeled sessions.
- **Thread accuracy**: false-positive rate on new threads; correct status transitions.
- **Combat fidelity (v1+)**: roll outcomes correctly reflected when roll logs exist.

### 13.2 Provisional thresholds (can be adjusted after baselining)
- NPC recall ≥ 0.85, precision ≥ 0.90 (gold set)
- Location recall ≥ 0.85, precision ≥ 0.90 (gold set)
- Item recall ≥ 0.75, precision ≥ 0.85 (gold set)
- New thread false-positive rate ≤ 0.20 (gold set)

### 13.3 Evaluation process (v0→v2)
- Build a gold set of 3–5 sessions with labeled NPCs/locations/items/threads and quote references.
- Run evals on each prompt version; promote versions only when they meet thresholds.
- DSPy optimization runs offline and emits a new pinned prompt version.

### 13.4 UX validation (user testing)
- Run task-based tests with at least 5 DMs and 5 players.
- Track time-to-task, success rate, and top confusion points.
- Log issues and fold the top fixes into the next sprint.

## 14) Non-functional requirements
- **Privacy**: transcripts and derived memory may be sensitive; provide campaign/session deletion and export.
- **Portability**: local-first; single Docker Compose for infra.
- **Cost control**: caching by transcript_hash + prompt/model version; avoid reprocessing unchanged inputs.
- **Multi-tenancy (future)**: campaign boundaries enforced in schema; future auth should map users→campaign permissions.

## 15) Roadmap
### MVP close-out (target completion state)
- UI session onboarding: create session metadata (title/date required) + upload transcript.
- UI run controls: start run, observe progress, set current run.
- Evidence-first navigation and confidence/trust indicators in UI (confidence + correction badges).
- Data lifecycle controls in UI (export/delete).
- Corrections inform extraction/resolve so known fixes persist across reruns.
- Summary variants + Ask the campaign surfaced in the UI.
- First user testing round feeds the final MVP polish list.

### Post-MVP (v1+ polish and scale)
- Information architecture refresh (role-based views, density tuning, mobile polish).
- Campaign config editor (speaker mappings, participant roster, PC links).
- Session management polish (edit title/date, compare runs, show change log).
- Data model additions: relationships, thread objectives, utterance mode, DM-as-NPC attribution.
- Performance: bundle slicing/pagination, query optimization, and caching for large campaigns.
- External sources UX (character sheets + dice rolls surfaced in UI).
- Repeat user testing after major UI changes.

### Longer-term (v1.5+)
- Semantic recall improvements, eval dashboards, and prompt optimization.
- Optional image generation for scene prompts.
