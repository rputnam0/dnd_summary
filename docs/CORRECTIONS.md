# Corrections Specification

## Purpose
Ensure DM-approved corrections become canonical and persist across future runs.
Corrections must affect extraction, resolution, summaries, and UI so known errors
are not reintroduced by the LLM.

## Scope (MVP)
- Entity corrections: rename, alias add/remove, merge, hide.
- Thread corrections: status/title/summary, merge, hide.
- Player edits are allowed only as proposals and require DM approval.

## Definitions
- Correction: an auditable override submitted by a user.
- Canonical map: derived, deterministic mapping from names and IDs to canonical entities
  and threads, built from approved corrections plus base data.
- Approved correction: a correction that is applied to new runs and read paths.

## Correction Lifecycle
- DM corrections are approved immediately on creation.
- Player corrections are created in a pending state and have no effect until DM approval.
- Corrections are immutable; approval status is updated by DM action.

Required fields (proposed model changes to `Correction`):
- `state`: pending | approved | rejected (default approved for DM, pending for player)
- `approved_by`: user_id (nullable)
- `approved_at`: timestamp (nullable)
- `review_note`: optional DM comment for approval/rejection

## Canonical Map Rules
### Entity map
Inputs:
- `entities` (canonical_name, entity_type)
- `entity_aliases`
- approved corrections (rename, merge, hide, alias add/remove)

Rules:
1) Rename
   - new name becomes the canonical name for the entity.
   - old canonical name is added as an alias.
2) Merge
   - merged entity ID maps to the target entity ID.
   - merged entity names become aliases of the target entity.
   - merged entity is treated as hidden in UI lists.
3) Hide
   - hidden entities are excluded from new runs and UI lists.
   - name lookups for hidden entities resolve to none (drop from extraction/resolution).
4) Alias add/remove
   - alias add: new alias maps to the entity.
   - alias remove: alias no longer resolves to the entity.

Conflict resolution:
- Apply corrections in chronological order; later approved corrections override earlier ones.
- Merge and hide actions override renames if they target the same entity.
- Merge chains are collapsed (A -> B -> C resolves to C).

### Thread map
Inputs:
- `threads` and `campaign_threads`
- approved corrections (status/title/summary/merge/hide)

Rules:
- Title/status/summary overrides apply to the thread in all read paths.
- Merge collapses to the target thread ID and hides the source thread.
- Hidden threads are excluded from new runs and UI lists.

## Pipeline Enforcement Points
1) Extraction (LLM)
   - Input prompt includes the canonical entity/thread map and a list of hidden IDs/names.
   - LLM must output canonical names; if unsure, output raw mention text with evidence.
   - Post-process extracted objects to map names through the canonical map and
     drop hidden entities/threads.

2) Resolution
   - Mention -> entity mapping uses the canonical map (including aliases and renames).
   - New entities are not created for hidden or merged names; they map to target or drop.
   - Aliases created during resolve must not conflict with removed aliases.

3) Summary plan and write
   - Summary inputs are built from corrected session facts.
   - Any name used in summaries should be canonical after corrections.

4) Read paths / UI
   - Lists and details always use corrected canonical names and statuses.
   - Correction badge appears on items affected by approved corrections.
   - Pending player corrections do not affect UI or data outputs.

## API Expectations (planned)
- `POST /entities/{id}/corrections`
  - If user is DM: create approved correction.
  - If user is player: create pending correction.
- `POST /threads/{id}/corrections`
  - Same approval rules as entities.
- `POST /corrections/{id}/approve|reject` (DM only)
  - Applies approval state transitions.
- Read endpoints return `corrected: true|false` when applicable.

## Acceptance Criteria
- Rename persists: if DM renames an entity, new runs and summaries use the new name
  and the old name resolves as an alias.
- Merge persists: merged entities never reappear as new canonical entries.
- Hide persists: hidden entities are not recreated in new runs.
- Thread status/title updates persist in future runs and UI.
- Player proposals have no effect until DM approval.
- Tests cover canonical map creation, extraction normalization, and resolve behavior.
