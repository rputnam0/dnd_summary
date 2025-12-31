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
 
Dependency management:
- Use `uv` with `pyproject.toml` (no `requirements.txt` or `pip` installs).

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, 100-char lines.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Keep modules small and single-purpose (e.g., `activities/transcripts.py`).
- Prefer explicit, typed payloads between workflows/activities.
- Lint/format with Flake8 and Black.

## Testing Guidelines
- No formal test suite yet.
- If you add tests, place them under `tests/` and use `pytest` conventions:
  - Files: `tests/test_*.py`
  - Test functions: `test_*`
- All tests must pass before merging a feature.

## Commit & Pull Request Guidelines
- Initialize a git repo and commit after each reasonable feature implementation.
- Use concise, imperative commit messages (e.g., “Add transcript ingester”).
- PRs should include: a short summary, key files changed, and how you validated changes.

## Security & Configuration Tips
- User data lives under `transcripts/campaigns/` and should not be committed.
- Store credentials via environment variables (see `src/dnd_summary/config.py`).
- Treat transcripts and derived outputs as sensitive campaign data.
