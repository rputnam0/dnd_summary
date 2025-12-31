# dnd_summary

Production-oriented pipeline to turn D&D session transcripts into:
- Structured, queryable campaign memory (Postgres)
- High-quality narrative summaries (DOCX export + UI-ready data)

This repo is being rebuilt from an early prototype. The original notebook-derived script and prompt files are kept under `legacy/` (gitignored) for reference only.

## Local dev (Temporal + Postgres)

Bring up infrastructure:
- `docker compose up -d`

Services:
- Temporal server: `localhost:7233`
- Temporal UI: `http://localhost:8080`
- App Postgres: `localhost:5432` (DB: `dnd_summary`)

## Python setup (uv)

Use `uv` with `pyproject.toml` (no `requirements.txt`).

- Create venv + install deps:
  - `uv venv`
  - `uv pip install -e ".[dev]"`
- Run linters:
  - `uv run black .`
  - `uv run flake8`
- Run tests:
  - `uv run pytest`

## LLM configuration

Set your Gemini API key in the environment before running extraction:
- `DND_GEMINI_API_KEY=...`
- Optional: `DND_GEMINI_MODEL=gemini-3-flash-preview`
Artifacts are written to `artifacts/` by default (see `DND_ARTIFACTS_ROOT`).

## Canonical transcript inputs

Canonical ingestion source lives under `transcripts/` (multi-campaign):
- `transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/...`

The pipeline will prefer `.jsonl` transcripts when present, falling back to `.txt`.

Optional campaign config lives at:
`transcripts/campaigns/<campaign_slug>/campaign.json`
Use this to map speakers to participants and PCs to character names.

## Quick local run (no Temporal)
If Docker/Temporal is not running, you can execute the pipeline in-process:
- `uv run dnd-summary run-session-local avarias session_54`

## UI dashboard
Run the API server and open the fantasy UI:
- `uv run dnd-summary api`
- Visit `http://127.0.0.1:8000/ui/`

Search tips:
- Toggle Semantic Search for query expansion (LLM-backed).
- Example: `Baba Yaga`, `magic shop potion`, `Rowan's Blessing`.

## DSPy evals
Evaluate prompt quality with the NPC extraction harness:
- `uv pip install -e ".[eval]"`
- `uv run python scripts/run_dspy_eval.py --dataset evals/npc_eval_template.jsonl`
