from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from temporalio import activity

from dnd_summary.config import settings


@dataclass(frozen=True)
class TranscriptSource:
    format: Literal["jsonl", "txt"]
    path: str


def _find_transcript_source(session_dir: Path) -> TranscriptSource:
    preferred_jsonl = session_dir / "transcript.jsonl"
    if preferred_jsonl.exists():
        return TranscriptSource(format="jsonl", path=str(preferred_jsonl))

    preferred_txt = session_dir / "transcript.txt"
    if preferred_txt.exists():
        return TranscriptSource(format="txt", path=str(preferred_txt))

    # Back-compat fallback for pre-migrated directories.
    jsonl_files = sorted(
        session_dir.glob("*.jsonl"),
        key=lambda p: (p.stat().st_size, p.stat().st_mtime),
        reverse=True,
    )
    if jsonl_files:
        return TranscriptSource(format="jsonl", path=str(jsonl_files[0]))

    txt_files = sorted(
        session_dir.glob("*.txt"),
        key=lambda p: (p.stat().st_size, p.stat().st_mtime),
        reverse=True,
    )
    if txt_files:
        return TranscriptSource(format="txt", path=str(txt_files[0]))

    raise FileNotFoundError(f"No transcript found in {session_dir}")


@activity.defn
async def ingest_transcript_activity(payload: dict) -> dict:
    """Locate the best transcript artifact for a session.

    v0: just discovers the canonical transcript file and returns its path.
    Next: parse utterances and persist to Postgres.
    """
    campaign_slug = payload["campaign_slug"]
    session_slug = payload["session_slug"]

    session_dir = (
        Path(settings.transcripts_root)
        / "campaigns"
        / campaign_slug
        / "sessions"
        / session_slug
    )
    src = _find_transcript_source(session_dir)
    return {"campaign_slug": campaign_slug, "session_slug": session_slug, "transcript": src.__dict__}
