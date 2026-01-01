from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from dnd_summary.db import get_session
from dnd_summary.models import RunStep


def _truncate_error(message: str | None) -> str | None:
    if not message:
        return None
    return message[:2000]


def start_run_step(run_id: str, session_id: str, name: str) -> str:
    with get_session() as session:
        step = RunStep(
            run_id=run_id,
            session_id=session_id,
            name=name,
            status="running",
            started_at=datetime.utcnow(),
        )
        session.add(step)
        session.flush()
        return step.id


def finish_run_step(step_id: str, status: str, error: str | None = None) -> None:
    with get_session() as session:
        step = session.query(RunStep).filter_by(id=step_id).one_or_none()
        if not step:
            return
        step.status = status
        step.finished_at = datetime.utcnow()
        step.error = _truncate_error(error)


@contextmanager
def run_step(run_id: str, session_id: str, name: str):
    step_id = start_run_step(run_id, session_id, name)
    try:
        yield
    except Exception as exc:
        finish_run_step(step_id, "failed", str(exc))
        raise
    else:
        finish_run_step(step_id, "completed")
