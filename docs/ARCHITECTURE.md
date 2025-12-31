# Architecture (Draft)

## High-level components
- **Transcripts**: canonical input files under `transcripts/` (multi-campaign).
- **Temporal**: orchestrates the processing DAG/workflow.
- **Postgres**: canonical store for campaign memory (entities/events/quotes/threads).
- **Worker**: Temporal worker (Python) that runs activities (ingest, extract, summarize, export).
- **API/UI** (later): browse/search campaign memory and rendered artifacts.

## Canonical transcript layout
Expected path:
`transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/`

Canonical transcript artifact names (preferred):
- `transcript.jsonl` (best input when available)
- `transcript.txt`
- `transcript.srt`

Variant artifacts may exist under `extras/`.

## Core domain separation
- **Player/Participant** (real-world voice track) is stored separately from **Character** (in-world).
- Summaries and UI should reference **Character** entities, not players.
- DM utterances are owned by the DM participant but may be attributed to NPC characters later via correction tools.

## Data layers (immutability + replayability)
- **Raw inputs**: on-disk transcript artifacts under `transcripts/` (treated as immutable per Run via `transcript_hash`).
- **Runs**: immutable, versioned outputs of the pipeline (prompt/model versions recorded).
- **Canonical campaign state** (v1+): the “current view” chosen from a Run + human corrections (overrides).

## Temporal workflow (v0)
Workflow: `ProcessSessionWorkflow(campaign_slug, session_slug)`

Activities (initial skeleton):
1) `ingest_transcript_activity`:
   - locates `transcript.jsonl|txt` for a session
   - next: parses utterances and persists to Postgres

Planned additions:
2) `extract_session_facts_activity` (LLM → strict JSON)
3) `resolve_entities_activity` (dedupe/aliases/stable IDs)
4) `generate_summary_plan_activity` (LLM)
5) `write_narrative_summary_activity` (LLM)
6) `render_docx_activity` (python-docx)

## LLM “inner loop” (non-agentic, typed tasks)
Avoid a free-form “agent” that wanders. Prefer a small set of typed, versioned tasks:

- `extract_session_facts_v1` → JSON
  - entities (NPC/location/item/faction/character)
  - events (time ranges + participants + location + evidence utterance refs)
  - threads/quests updates
  - quote candidates (by utterance refs)
  - scene candidates (for future images)

- `plan_summary_v1` → JSON beat sheet
  - ordered beats mapped to extracted events
  - selected quote refs to embed
  - continuity reminders from DB “memory”

- `write_summary_v1` → prose
  - narrative summary in the established style
  - grounded by the beat sheet + exact transcript quotes reconstructed from utterance refs

## LLM integration library (decision)
- Temporal is the workflow engine; we do not rely on LangGraph for DAG control.
- LLM calls should go through a small internal interface (e.g., `LLMClient`) so providers are swappable.
- v0 should use the provider SDK directly (`google-genai`) + Pydantic validation for structured outputs.
- LangChain can be added later for optional tool abstractions (DB retrieval tools), but core extraction/summarization should not depend on LangChain internals.

## Prompt versioning + provenance
Every LLM call should persist:
- `prompt_id`, `prompt_version`, `schema_version`
- model name + parameters
- input hash (transcript + context package)
- output hash + validation results
- cost/latency

This enables reproducibility, regression detection, and prompt optimization.

## DSPy optimization loop (offline)
DSPy is used to iterate on prompts and select better prompt/program variants:
- Inputs: labeled eval sets + scoring rubrics (NPC recall, quote integrity, etc.)
- Output: a new versioned prompt artifact pinned by config
- Production workflows should use pinned prompt versions (no auto-mutation at runtime)

## Database (v0 target tables)
Minimal tables to unlock UI/search:
- `campaigns`, `sessions`
- `participants`, `characters`, `participant_character_map`
- `utterances`
- `entities` (typed), `entity_aliases`, `entity_mentions`
- `events`, `event_entities`
- `quotes`
- `threads`, `thread_updates`
- `artifacts` (DOCX, extracted JSON, summary text)
- `llm_calls` (provenance)

## Evidence model
- Evidence is stored as `EvidenceSpan(utterance_id, char_start?, char_end?)`.
- Quotes in UI and DOCX should be reconstructed from the transcript text using evidence spans (prevents hallucinated quotes).

## External sources (v1+)
- Character sheets / inventories (e.g., D&D Beyond exports) and dice/roll logs are ingested as optional session inputs.
- When roll logs include timestamps, they are aligned to transcript time and can be referenced as evidence for combat beats.

## Chunking strategy
Default: single-pass extraction over the full transcript (when model context allows).
Fallback: overlapping windows + evidence-based merge, only when transcript size exceeds safe limits.
