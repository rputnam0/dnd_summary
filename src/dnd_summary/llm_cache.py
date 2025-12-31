from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from dnd_summary.config import settings
from dnd_summary.models import Run, SessionExtraction


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _usage_value(usage: Any, key: str) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(key)
    return getattr(usage, key, None)


def build_transcript_block(transcript_text: str, cached: bool) -> str:
    if cached:
        return "Transcript (cached above; each line includes the utterance_id)."
    return f"Transcript (each line includes the utterance_id):\n{transcript_text}"


def _find_cached_transcript(
    session,
    run: Run,
) -> str | None:
    candidates = (
        session.query(SessionExtraction)
        .filter_by(
            session_id=run.session_id,
            kind="transcript_cache",
            model=settings.gemini_model,
        )
        .order_by(SessionExtraction.created_at.desc())
        .all()
    )
    now = datetime.now(timezone.utc)
    for record in candidates:
        payload = record.payload or {}
        if payload.get("invalidated"):
            continue
        if payload.get("transcript_hash") != run.transcript_hash:
            continue
        expires_at = _parse_datetime(payload.get("expires_at"))
        if expires_at and expires_at <= now:
            continue
        cache_name = payload.get("cache_name")
        if cache_name:
            return cache_name
    return None


def ensure_transcript_cache(
    session,
    run: Run,
    transcript_text: str,
) -> tuple[str | None, str]:
    if not settings.enable_explicit_cache:
        return None, build_transcript_block(transcript_text, cached=False)

    cache_name = _find_cached_transcript(session, run)
    if cache_name:
        return cache_name, build_transcript_block("", cached=True)

    if not settings.gemini_api_key:
        return None, build_transcript_block(transcript_text, cached=False)

    client = genai.Client(api_key=settings.gemini_api_key)
    cached_text = build_transcript_block(transcript_text, cached=False)
    ttl = f"{settings.cache_ttl_seconds}s"
    display_name = f"{run.session_id}:{run.id}:transcript"
    try:
        cache = client.caches.create(
            model=settings.gemini_model,
            config=types.CreateCachedContentConfig(
                display_name=display_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=cached_text)],
                    )
                ],
                ttl=ttl,
            ),
        )
        session.add(
            SessionExtraction(
                run_id=run.id,
                session_id=run.session_id,
                kind="transcript_cache",
                model=settings.gemini_model,
                prompt_id="transcript_cache",
                prompt_version="1",
                payload={
                    "cache_name": cache.name,
                    "display_name": display_name,
                    "transcript_hash": run.transcript_hash,
                    "expires_at": getattr(cache, "expire_time", None).isoformat()
                    if getattr(cache, "expire_time", None)
                    else None,
                    "token_count": _usage_value(getattr(cache, "usage_metadata", None), "total_token_count"),
                },
                created_at=datetime.utcnow(),
            )
        )
        return cache.name, build_transcript_block("", cached=True)
    except Exception as exc:
        session.add(
            SessionExtraction(
                run_id=run.id,
                session_id=run.session_id,
                kind="transcript_cache_error",
                model=settings.gemini_model,
                prompt_id="transcript_cache",
                prompt_version="1",
                payload={"error": str(exc)[:2000]},
                created_at=datetime.utcnow(),
            )
        )
        return None, build_transcript_block(transcript_text, cached=False)


def record_llm_usage(
    session,
    *,
    run_id: str,
    session_id: str,
    prompt_id: str,
    prompt_version: str,
    call_kind: str,
    usage: Any,
    cache_name: str | None,
) -> None:
    if usage is None:
        return
    payload = {
        "call_kind": call_kind,
        "prompt_token_count": _usage_value(usage, "prompt_token_count"),
        "cached_content_token_count": _usage_value(usage, "cached_content_token_count"),
        "candidates_token_count": _usage_value(usage, "candidates_token_count"),
        "total_token_count": _usage_value(usage, "total_token_count"),
        "cache_name": cache_name,
    }
    session.add(
        SessionExtraction(
            run_id=run_id,
            session_id=session_id,
            kind="llm_usage",
            model=settings.gemini_model,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            payload=payload,
            created_at=datetime.utcnow(),
        )
    )
