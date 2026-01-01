from __future__ import annotations

import asyncio

import pytest

from dnd_summary.activities.run_status import update_run_status_activity
from dnd_summary.models import Run
from tests.factories import create_campaign, create_run, create_session


def test_update_run_status_updates_run(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, status="running")
    db_session.commit()

    result = asyncio.run(update_run_status_activity({"run_id": run.id, "status": "failed"}))

    db_session.expire_all()
    updated = db_session.query(Run).filter_by(id=run.id).one()
    assert updated.status == "failed"
    assert updated.finished_at is not None
    assert result["status"] == "failed"


def test_update_run_status_missing_run_raises(db_session):
    with pytest.raises(ValueError):
        asyncio.run(update_run_status_activity({"run_id": "missing", "status": "failed"}))
