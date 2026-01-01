# Repository Guidelines

## Project Structure & Module Organization
- `src/dnd_summary/`: application source (Temporal workflows, activities, CLI).
- `docs/`: product and architecture specs (`docs/PRD.md`, `docs/ARCHITECTURE.md`).
- `scripts/`: one-off utilities (e.g., transcript migration).
- `transcripts/`: canonical input data (kept out of git; see `transcripts/README.md`).
- `legacy/`: prior prototype assets (gitignored).

## Build, Test, and Development Commands
- `docker compose up -d`: start Temporal + Postgres locally.
- `python3 -m py_compile <files>`: quick syntax check (no test suite yet).
- `python3 scripts/migrate_transcripts.py`: migrate legacy transcripts into the canonical layout.
- `python3 -m dnd_summary.cli show-config`: verify configuration defaults.
- `python3 -m dnd_summary.cli worker`: run the Temporal worker locally.
- `python3 -m dnd_summary.cli run-session <campaign> <session>`: start a workflow run.
- `uv run alembic upgrade head`: apply DB migrations to the configured database.
- `uv run alembic stamp <rev_id>`: mark an existing DB at a revision without applying migrations.
- `uv run alembic current`: show the current Alembic revision.
- `uv run alembic history --verbose`: show Alembic history.
- `uv run dnd-summary list-caches`: list transcript caches (use `--verify-remote` to confirm cache existence).
- `uv run dnd-summary clear-caches --all`: delete cached transcripts and mark them invalidated in the DB.
- `uv run dnd-summary inspect-usage <campaign> <session>`: summarize LLM token usage by call.
 
Dependency management:
- Use `uv` with `pyproject.toml` (no `requirements.txt` or `pip` installs).

## Database migrations (Alembic)
- Migrations are authoritative; runtime schema creation is disabled.
- To set up a fresh DB:
  - `export DND_DATABASE_URL="postgresql+psycopg://dnd:dnd@localhost:5432/dnd_summary"`
  - `uv run alembic upgrade head`
- To stamp an existing DB created via `create_all()`:
  1) Confirm baseline revision in `alembic/versions/0001_initial_schema.py`.
  2) Back up the DB:
     - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_summary -Fc > backup_before_alembic_stamp.dump`
  3) Create a scratch DB and run the migration:
     - `docker compose exec -T app-postgres createdb -U dnd dnd_scratch_schemacheck`
     - `export DND_DATABASE_URL="postgresql+psycopg://dnd:dnd@localhost:5432/dnd_scratch_schemacheck"`
     - `uv run alembic upgrade head`
  4) Dump schema-only and diff:
     - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_scratch_schemacheck --schema-only --no-owner --no-privileges > /tmp/schema_from_alembic.sql`
     - `docker compose exec -T app-postgres pg_dump -U dnd -d dnd_summary --schema-only --no-owner --no-privileges > /tmp/schema_existing.sql`
     - `diff -u /tmp/schema_from_alembic.sql /tmp/schema_existing.sql | less`
     - Acceptable diffs: `alembic_version`, `\\restrict/\\unrestrict` tokens, ownership/comments/order.
  5) If diffs are trivial, stamp:
     - `uv run alembic stamp 0001_initial_schema`
  6) Verify:
     - `uv run alembic current`
     - `uv run alembic history --verbose | head -n 50`
  7) Drop scratch DB if not needed:
     - `docker compose exec -T app-postgres dropdb -U dnd dnd_scratch_schemacheck`

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, 100-char lines.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Keep modules small and single-purpose (e.g., `activities/transcripts.py`).
- Prefer explicit, typed payloads between workflows/activities.
- Lint/format with Flake8 and Black.

## Testing Guidelines
- Tests live under `tests/` and use `pytest` conventions:
  - Files: `tests/test_*.py`
  - Test functions: `test_*`
- Run the suite with `uv run pytest` (uses in-memory SQLite + mocked external services to exercise API, CLI, and activity logic without Postgres/Temporal).
- All tests must pass before every commit and before merging a feature.
- Coverage map (high-level):
  - `tests/test_api_*.py`: FastAPI endpoints, auth scoping, corrections, and core API behaviors.
  - `tests/test_cli.py`: CLI outputs for config, cache inspection, and usage reporting.
  - `tests/test_activities_*.py`: Temporal activity helpers and side effects (transcripts, cache cleanup, resolve, summary, run status).
  - `tests/test_transcripts.py`: transcript parsing for supported formats.
  - `tests/test_transcript_format.py`: transcript formatting and utterance-id mapping.
  - `tests/test_llm_cache.py`: cache logic and usage accounting.
  - `tests/test_mappings.py`: character/participant mapping.
  - `tests/test_run_steps.py`: run step lifecycle bookkeeping.
  - `tests/test_render.py`: DOCX rendering output.
  - `tests/test_campaign_config.py`: campaign config parsing and alias maps.

## Commit & Pull Request Guidelines
- Initialize a git repo and commit after each reasonable feature implementation.
- Use concise, imperative commit messages (e.g., “Add transcript ingester”).
- PRs should include: a short summary, key files changed, and how you validated changes.

## Security & Configuration Tips
- User data lives under `transcripts/campaigns/` and should not be committed.
- Store credentials via environment variables (see `src/dnd_summary/config.py`).
- Treat transcripts and derived outputs as sensitive campaign data.
- Explicit transcript caching is enabled by default; caches are released after each run unless disabled via config.
- For local prompt testing/optimization, temporarily set `DND_CACHE_RELEASE_ON_COMPLETE=false` and/or `DND_CACHE_RELEASE_ON_PARTIAL=false` and set a short TTL like `DND_CACHE_TTL_SECONDS=600`; clear caches when finished.
