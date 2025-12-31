from __future__ import annotations

from datetime import timedelta

from temporalio import workflow


@workflow.defn
class ProcessSessionWorkflow:
    """Minimal v0 workflow: discover transcript for a session.

    This is the initial "agent run" skeleton; additional activities will be added
    for extraction, DB upserts, summary generation, and DOCX rendering.
    """

    @workflow.run
    async def run(self, payload: dict) -> dict:
        transcript = await workflow.execute_activity(
            "ingest_transcript_activity",
            payload,
            start_to_close_timeout=timedelta(seconds=60),
        )
        return {"status": "ok", "ingest": transcript}
