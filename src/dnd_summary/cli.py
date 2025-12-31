from __future__ import annotations

import asyncio

import typer

from dnd_summary.config import settings

app = typer.Typer(no_args_is_help=True)


@app.command()
def show_config() -> None:
    typer.echo(f"database_url={settings.database_url}")
    typer.echo(f"temporal_address={settings.temporal_address}")
    typer.echo(f"temporal_namespace={settings.temporal_namespace}")
    typer.echo(f"temporal_task_queue={settings.temporal_task_queue}")
    typer.echo(f"transcripts_root={settings.transcripts_root}")


@app.command()
def worker() -> None:
    """Start the Temporal worker (workflow + activities)."""
    from dnd_summary.temporal_worker import run_worker

    asyncio.run(run_worker())


@app.command()
def run_session(campaign_slug: str, session_slug: str) -> None:
    """Kick off a ProcessSession workflow run for a session."""
    from temporalio.client import Client

    from dnd_summary.workflows.process_session import ProcessSessionWorkflow

    async def _run() -> None:
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )
        handle = await client.start_workflow(
            ProcessSessionWorkflow.run,
            {"campaign_slug": campaign_slug, "session_slug": session_slug},
            id=f"process-session:{campaign_slug}:{session_slug}",
            task_queue=settings.temporal_task_queue,
        )
        typer.echo(f"Started workflow: {handle.id} / {handle.run_id}")

    asyncio.run(_run())

