from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dnd_summary.llm_cache import (
    CacheRequiredError,
    _parse_datetime,
    build_text_metrics,
    cache_hit_from_usage,
    cache_storage_cost,
    ensure_transcript_cache,
    record_llm_usage,
)
from dnd_summary.models import SessionExtraction
from tests.factories import (
    create_campaign,
    create_run,
    create_session,
    create_session_extraction,
)


class DummyCaches:
    def __init__(self, cache):
        self._cache = cache

    def create(self, **_kwargs):
        return self._cache


class DummyClient:
    def __init__(self, cache):
        self.caches = DummyCaches(cache)


class DummyCache:
    def __init__(self):
        self.name = "cache-123"
        self.expire_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.usage_metadata = {"total_token_count": 200}


def test_parse_datetime_handles_strings():
    value = _parse_datetime("2024-01-01T00:00:00Z")
    assert value is not None
    assert value.tzinfo is not None


def test_build_text_metrics_counts_characters():
    metrics = build_text_metrics("sample", "a\nb")
    assert metrics["sample_char_count"] == 3
    assert metrics["sample_line_count"] == 2
    assert metrics["sample_token_estimate"] >= 1


def test_cache_hit_from_usage_handles_dict():
    usage = {"cached_content_token_count": 5}
    assert cache_hit_from_usage(usage, "cache") is True
    assert cache_hit_from_usage(usage, None) is False


def test_cache_storage_cost_handles_zero():
    assert cache_storage_cost(None, 3600) is None
    assert cache_storage_cost(0, 3600) is None
    assert cache_storage_cost(100, 0) is None


def test_ensure_transcript_cache_disabled(db_session, settings_overrides):
    settings_overrides(enable_explicit_cache=False, require_transcript_cache=False)
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    db_session.commit()

    cache_name, block = ensure_transcript_cache(db_session, run, "hello")

    assert cache_name is None
    assert "Transcript" in block
    assert db_session.query(SessionExtraction).count() == 0


def test_ensure_transcript_cache_missing_key_required(db_session, settings_overrides):
    settings_overrides(enable_explicit_cache=True, require_transcript_cache=True, gemini_api_key=None)
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    db_session.commit()

    with pytest.raises(CacheRequiredError):
        ensure_transcript_cache(db_session, run, "hello")

    record = db_session.query(SessionExtraction).one()
    assert record.kind == "transcript_cache_error"
    assert record.payload["reason"] == "missing_api_key"


def test_ensure_transcript_cache_returns_existing(db_session, settings_overrides):
    settings_overrides(
        enable_explicit_cache=True,
        require_transcript_cache=True,
        gemini_api_key=None,
        gemini_model="test-model",
    )
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, transcript_hash="hash")
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="transcript_cache",
        payload={
            "cache_name": "cache-abc",
            "transcript_hash": "hash",
            "format_version": "timecode_v1",
        },
        model="test-model",
    )
    db_session.commit()

    cache_name, block = ensure_transcript_cache(db_session, run, "hello")

    assert cache_name == "cache-abc"
    assert "cached" in block


def test_ensure_transcript_cache_creates_new(db_session, settings_overrides, monkeypatch):
    settings_overrides(enable_explicit_cache=True, require_transcript_cache=False, gemini_api_key="key")
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, transcript_hash="hash")
    db_session.commit()

    cache = DummyCache()
    monkeypatch.setattr(
        "dnd_summary.llm_cache.genai.Client",
        lambda api_key=None: DummyClient(cache),
    )

    cache_name, block = ensure_transcript_cache(db_session, run, "hello")

    assert cache_name == "cache-123"
    assert "cached" in block
    record = (
        db_session.query(SessionExtraction)
        .filter_by(kind="transcript_cache", run_id=run.id)
        .one()
    )
    assert record.payload["cache_name"] == "cache-123"


def test_record_llm_usage_persists_costs(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, transcript_hash="hash")
    db_session.commit()

    usage = {
        "prompt_token_count": 100,
        "cached_content_token_count": 20,
        "candidates_token_count": 50,
        "total_token_count": 150,
    }
    record_llm_usage(
        db_session,
        run_id=run.id,
        session_id=session_obj.id,
        prompt_id="prompt",
        prompt_version="1",
        call_kind="extract",
        usage=usage,
        cache_name="cache-1",
    )

    record = (
        db_session.query(SessionExtraction)
        .filter_by(kind="llm_usage", run_id=run.id)
        .one()
    )
    assert record.payload["call_kind"] == "extract"
    assert record.payload["cache_hit"] is True
