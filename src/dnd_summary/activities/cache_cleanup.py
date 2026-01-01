from __future__ import annotations

from datetime import datetime, timezone

from temporalio import activity

from dnd_summary.config import settings
from dnd_summary.db import get_session
from dnd_summary.models import Run, SessionExtraction


def _should_release(status: str | None) -> bool:
    if status == "completed":
        return settings.cache_release_on_complete
    if status == "partial":
        return settings.cache_release_on_partial
    if status == "failed":
        return settings.cache_release_on_failed
    return False


@activity.defn
async def release_transcript_cache_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    status = payload.get("status")

    if not settings.enable_explicit_cache or not _should_release(status):
        return {"run_id": run_id, "released": 0, "skipped": True}

    from google import genai

    if not settings.gemini_api_key:
        return {"run_id": run_id, "released": 0, "skipped": True}

    client = genai.Client(api_key=settings.gemini_api_key)
    released = 0
    now = datetime.now(timezone.utc).isoformat()

    with get_session() as session:
        run = session.query(Run).filter_by(id=run_id).one_or_none()
        if not run:
            return {"run_id": run_id, "released": 0, "skipped": True}
        caches = (
            session.query(SessionExtraction)
            .filter_by(
                run_id=run.id,
                session_id=run.session_id,
                kind="transcript_cache",
            )
            .order_by(SessionExtraction.created_at.desc())
            .all()
        )
        for record in caches:
            payload = record.payload or {}
            if payload.get("invalidated"):
                continue
            cache_name = payload.get("cache_name")
            result = "skipped"
            if cache_name:
                try:
                    client.caches.delete(cache_name)
                    result = "deleted"
                    released += 1
                except Exception as exc:
                    result = f"error={str(exc)[:120]}"
            record.payload = {
                **payload,
                "invalidated": True,
                "invalidated_at": now,
                "delete_result": result,
            }

    return {"run_id": run_id, "released": released, "skipped": False}
