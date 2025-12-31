from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from dnd_summary.activities.extract import extract_session_facts_activity
from dnd_summary.activities.persist import persist_session_facts_activity
from dnd_summary.activities.resolve import resolve_entities_activity
from dnd_summary.activities.summary import (
    plan_summary_activity,
    render_summary_docx_activity,
    write_summary_activity,
)
from dnd_summary.activities.transcripts import ingest_transcript_activity
from dnd_summary.config import settings
from dnd_summary.workflows.process_session import ProcessSessionWorkflow


async def run_worker() -> None:
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[ProcessSessionWorkflow],
        activities=[
            ingest_transcript_activity,
            extract_session_facts_activity,
            persist_session_facts_activity,
            resolve_entities_activity,
            plan_summary_activity,
            write_summary_activity,
            render_summary_docx_activity,
        ],
    )
    await worker.run()
