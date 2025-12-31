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


@app.command()
def inspect_session(campaign_slug: str, session_slug: str) -> None:
    """Show counts and artifacts for the latest run of a session."""
    from dnd_summary.db import get_session
    from dnd_summary.models import Artifact, Campaign, Run, Session, SessionExtraction

    with get_session() as session:
        session_obj = (
            session.query(Session)
            .join(Campaign, Session.campaign_id == Campaign.id)
            .filter(Campaign.slug == campaign_slug, Session.slug == session_slug)
            .first()
        )
        if not session_obj:
            raise SystemExit("Session not found.")

        run = (
            session.query(Run)
            .filter_by(session_id=session_obj.id)
            .order_by(Run.created_at.desc())
            .first()
        )
        if not run:
            raise SystemExit("No runs found for session.")

        metrics = (
            session.query(SessionExtraction)
            .filter_by(run_id=run.id, session_id=session_obj.id, kind="persist_metrics")
            .order_by(SessionExtraction.created_at.desc())
            .first()
        )

        artifacts = (
            session.query(Artifact)
            .filter_by(run_id=run.id, session_id=session_obj.id)
            .all()
        )

        typer.echo(f"run_id={run.id}")
        typer.echo(f"transcript_hash={run.transcript_hash}")
        if metrics:
            for key, value in metrics.payload.items():
                typer.echo(f"{key}={value}")
        else:
            typer.echo("persist_metrics=missing")
        for artifact in artifacts:
            typer.echo(f"artifact[{artifact.kind}]={artifact.path}")


if __name__ == "__main__":
    app()
