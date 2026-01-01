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

## Database migrations (Alembic)

Migrations are authoritative; runtime schema creation is disabled.

### Fresh DB setup
- `export DND_DATABASE_URL="postgresql+psycopg://dnd:dnd@localhost:5432/dnd_summary"`
- `uv run alembic upgrade head`

### Stamping an existing DB created via create_all
1) Identify the baseline revision id in `alembic/versions/0001_initial_schema.py`
   - `revision = "0001_initial_schema"`
2) Back up the existing DB (required):
   - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_summary -Fc > backup_before_alembic_stamp.dump`
   - Optional sanity check: `pg_restore --list backup_before_alembic_stamp.dump | head`
3) Create a scratch DB and run the baseline migration:
   - `docker compose exec -T app-postgres createdb -U dnd dnd_scratch_schemacheck`
   - `export DND_DATABASE_URL="postgresql+psycopg://dnd:dnd@localhost:5432/dnd_scratch_schemacheck"`
   - `uv run alembic upgrade head`
4) Dump schema-only from both DBs and diff them:
   - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_scratch_schemacheck --schema-only --no-owner --no-privileges > /tmp/schema_from_alembic.sql`
   - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_summary --schema-only --no-owner --no-privileges > /tmp/schema_existing.sql`
   - `diff -u /tmp/schema_from_alembic.sql /tmp/schema_existing.sql | less`
   - Acceptable diffs: `alembic_version`, `\\restrict/\\unrestrict` tokens, ownership/comments/order.
5) If differences are only trivial (ordering/ownership/comments), stamp the existing DB:
   - `uv run alembic stamp 0001_initial_schema`
6) Verify tracking:
   - `uv run alembic current`
   - `uv run alembic history --verbose | head -n 50`
7) Drop scratch DB if not needed:
   - `docker compose exec -T app-postgres dropdb -U dnd dnd_scratch_schemacheck`

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
