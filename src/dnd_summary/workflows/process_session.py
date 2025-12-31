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
        extraction = await workflow.execute_activity(
            "extract_session_facts_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=10),
        )
        persisted = await workflow.execute_activity(
            "persist_session_facts_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=2),
        )
        resolved = await workflow.execute_activity(
            "resolve_entities_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=2),
        )
        plan = await workflow.execute_activity(
            "plan_summary_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=10),
        )
        summary = await workflow.execute_activity(
            "write_summary_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=10),
        )
        docx = await workflow.execute_activity(
            "render_summary_docx_activity",
            {
                "run_id": transcript["run_id"],
                "session_id": transcript["session_id"],
            },
            start_to_close_timeout=timedelta(minutes=2),
        )
        return {
            "status": "ok",
            "ingest": transcript,
            "extract": extraction,
            "persist": persisted,
            "resolve": resolved,
            "plan": plan,
            "summary": summary,
            "docx": docx,
        }
