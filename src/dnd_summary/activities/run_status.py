from __future__ import annotations

from datetime import datetime

from temporalio import activity

from dnd_summary.db import get_session
from dnd_summary.models import Run


@activity.defn
async def update_run_status_activity(payload: dict) -> dict:
    run_id = payload["run_id"]
    status = payload["status"]

    with get_session() as session:
        run = session.query(Run).filter_by(id=run_id).one_or_none()
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        run.status = status
        run.finished_at = datetime.utcnow()

    return {"run_id": run_id, "status": status}
