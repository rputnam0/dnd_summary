from __future__ import annotations

import asyncio

from google import genai

from dnd_summary.activities.cache_cleanup import _should_release, release_transcript_cache_activity
from dnd_summary.models import SessionExtraction
from tests.factories import create_campaign, create_run, create_session, create_session_extraction


class DummyCaches:
    def __init__(self):
        self.deleted = []

    def delete(self, name):
        self.deleted.append(name)


class DummyClient:
    def __init__(self):
        self.caches = DummyCaches()


def test_should_release_respects_status(settings_overrides):
    settings_overrides(
        cache_release_on_complete=True,
        cache_release_on_partial=False,
        cache_release_on_failed=True,
    )
    assert _should_release("completed") is True
    assert _should_release("partial") is False
    assert _should_release("failed") is True
    assert _should_release(None) is False


def test_release_transcript_cache_activity_marks_invalidated(
    db_session, settings_overrides, monkeypatch
):
    settings_overrides(enable_explicit_cache=True, gemini_api_key="key")
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="transcript_cache",
        payload={"cache_name": "cache-1", "invalidated": False},
    )
    db_session.commit()

    client = DummyClient()
    monkeypatch.setattr(genai, "Client", lambda api_key=None: client)

    result = asyncio.run(release_transcript_cache_activity({"run_id": run.id, "status": "completed"}))

    assert result["released"] == 1
    db_session.expire_all()
    record = db_session.query(SessionExtraction).filter_by(kind="transcript_cache").one()
    assert record.payload["invalidated"] is True
    assert record.payload["delete_result"] == "deleted"
