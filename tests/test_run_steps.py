from __future__ import annotations

from dnd_summary.run_steps import finish_run_step, run_step, start_run_step
from dnd_summary.models import RunStep
from tests.factories import create_campaign, create_run, create_session


def test_start_and_finish_run_step(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    db_session.commit()

    step_id = start_run_step(run.id, session_obj.id, "extract")
    finish_run_step(step_id, "completed")

    step = db_session.query(RunStep).filter_by(id=step_id).one()
    assert step.status == "completed"
    assert step.finished_at is not None


def test_run_step_records_failure(db_session):
    campaign = create_campaign(db_session)
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    db_session.commit()

    try:
        with run_step(run.id, session_obj.id, "explode"):
            raise ValueError("boom")
    except ValueError:
        pass

    step = db_session.query(RunStep).filter_by(run_id=run.id, name="explode").one()
    assert step.status == "failed"
    assert step.error == "boom"
