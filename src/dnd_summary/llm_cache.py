from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from dnd_summary.config import settings
from dnd_summary.models import Run, SessionExtraction


class CacheRequiredError(RuntimeError):
    pass


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


def _approx_token_count(char_count: int) -> int:
    if char_count <= 0:
        return 0
    return max(1, char_count // 4)


def _round_cost(value: float) -> float:
    return round(value, 6)


def _cost_for_tokens(tokens: int, cost_per_million: float) -> float:
    if tokens <= 0 or cost_per_million <= 0:
        return 0.0
    return (tokens / 1_000_000) * cost_per_million


def build_text_metrics(label: str, text: str) -> dict[str, int]:
    char_count = len(text)
    line_count = text.count("\n") + 1 if text else 0
    return {
        f"{label}_char_count": char_count,
        f"{label}_line_count": line_count,
        f"{label}_token_estimate": _approx_token_count(char_count),
    }


def cache_hit_from_usage(usage: Any, cache_name: str | None) -> bool:
    if not cache_name:
        return False
    cached_tokens = _usage_value(usage, "cached_content_token_count")
    return cached_tokens is not None and cached_tokens > 0


def cache_storage_cost(token_count: int | None, ttl_seconds: int) -> float | None:
    if token_count is None or token_count <= 0:
        return None
    if ttl_seconds <= 0:
        return None
    hours = ttl_seconds / 3600
    return _round_cost(
        _cost_for_tokens(token_count, settings.llm_cache_storage_cost_per_million_hour)
        * hours
    )


def build_transcript_block(transcript_text: str, cached: bool) -> str:
    if cached:
        return (
            "Transcript (cached above; each line includes the utterance_id timecode key)."
        )
    return (
        "Transcript (each line includes the utterance_id timecode key):\n"
        f"{transcript_text}"
    )


def _record_transcript_cache_error(session, run: Run, reason: str, error: str | None) -> None:
    payload = {"reason": reason}
    if error:
        payload["error"] = error[:2000]
    session.add(
        SessionExtraction(
            run_id=run.id,
            session_id=run.session_id,
            kind="transcript_cache_error",
            model=settings.gemini_model,
            prompt_id="transcript_cache",
            prompt_version="1",
            payload=payload,
            created_at=datetime.utcnow(),
        )
    )


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
        if payload.get("format_version") != settings.transcript_format_version:
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
        if settings.require_transcript_cache:
            _record_transcript_cache_error(
                session,
                run,
                reason="cache_disabled",
                error="Explicit transcript cache required but disabled.",
            )
            raise CacheRequiredError("Explicit transcript cache required but disabled.")
        return None, build_transcript_block(transcript_text, cached=False)

    cache_name = _find_cached_transcript(session, run)
    if cache_name:
        return cache_name, build_transcript_block("", cached=True)

    if not settings.gemini_api_key:
        if settings.require_transcript_cache:
            _record_transcript_cache_error(
                session,
                run,
                reason="missing_api_key",
                error="Missing Gemini API key for transcript cache.",
            )
            raise CacheRequiredError("Missing Gemini API key for transcript cache.")
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
        token_count = _usage_value(getattr(cache, "usage_metadata", None), "total_token_count")
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
                    "format_version": settings.transcript_format_version,
                    "token_count": token_count,
                    "storage_hours": round(settings.cache_ttl_seconds / 3600, 4),
                    "storage_cost_usd": cache_storage_cost(
                        token_count, settings.cache_ttl_seconds
                    ),
                },
                created_at=datetime.utcnow(),
            )
        )
        return cache.name, build_transcript_block("", cached=True)
    except Exception as exc:
        _record_transcript_cache_error(
            session,
            run,
            reason="create_failed",
            error=str(exc),
        )
        if settings.require_transcript_cache:
            raise CacheRequiredError("Failed to create transcript cache.") from exc
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
    metadata: dict[str, Any] | None = None,
) -> None:
    if usage is None:
        return
    prompt_tokens = _usage_value(usage, "prompt_token_count") or 0
    cached_tokens = _usage_value(usage, "cached_content_token_count") or 0
    output_tokens = _usage_value(usage, "candidates_token_count") or 0
    non_cached_tokens = max(prompt_tokens - cached_tokens, 0)
    input_cost = _cost_for_tokens(non_cached_tokens, settings.llm_input_cost_per_million)
    cached_cost = _cost_for_tokens(cached_tokens, settings.llm_cached_cost_per_million)
    output_cost = _cost_for_tokens(output_tokens, settings.llm_output_cost_per_million)
    total_cost = input_cost + cached_cost + output_cost
    payload = {
        "call_kind": call_kind,
        "prompt_token_count": prompt_tokens,
        "cached_content_token_count": cached_tokens,
        "candidates_token_count": output_tokens,
        "total_token_count": _usage_value(usage, "total_token_count"),
        "non_cached_prompt_token_count": non_cached_tokens,
        "cache_name": cache_name,
        "cache_hit": cache_hit_from_usage(usage, cache_name),
        "cache_required": settings.require_transcript_cache,
        "input_cost_usd": _round_cost(input_cost),
        "cached_cost_usd": _round_cost(cached_cost),
        "output_cost_usd": _round_cost(output_cost),
        "total_cost_usd": _round_cost(total_cost),
    }
    if metadata:
        payload.update(metadata)
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
