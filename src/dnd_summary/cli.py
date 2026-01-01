from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import typer
from sqlalchemy import text

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
def run_session_local(campaign_slug: str, session_slug: str) -> None:
    """Run the pipeline locally without Temporal (for quick testing)."""
    from dnd_summary.activities.extract import extract_session_facts_activity
    from dnd_summary.activities.cache_cleanup import release_transcript_cache_activity
    from dnd_summary.activities.persist import persist_session_facts_activity
    from dnd_summary.activities.resolve import resolve_entities_activity
    from dnd_summary.activities.run_status import update_run_status_activity
    from dnd_summary.activities.summary import (
        plan_summary_activity,
        render_summary_docx_activity,
        write_summary_activity,
    )
    from dnd_summary.activities.transcripts import ingest_transcript_activity

    async def _run() -> None:
        payload = {"campaign_slug": campaign_slug, "session_slug": session_slug}
        transcript = await ingest_transcript_activity(payload)
        extract_payload = {
            "run_id": transcript["run_id"],
            "session_id": transcript["session_id"],
        }
        try:
            await extract_session_facts_activity(extract_payload)
            await persist_session_facts_activity(extract_payload)
            await resolve_entities_activity(extract_payload)
        except Exception:
            await update_run_status_activity(
                {"run_id": transcript["run_id"], "status": "failed"}
            )
            await release_transcript_cache_activity(
                {"run_id": transcript["run_id"], "status": "failed"}
            )
            raise
        try:
            await plan_summary_activity(extract_payload)
            await write_summary_activity(extract_payload)
            await render_summary_docx_activity(extract_payload)
        except Exception:
            await update_run_status_activity(
                {"run_id": transcript["run_id"], "status": "partial"}
            )
            await release_transcript_cache_activity(
                {"run_id": transcript["run_id"], "status": "partial"}
            )
            raise
        await update_run_status_activity(
            {"run_id": transcript["run_id"], "status": "completed"}
        )
        await release_transcript_cache_activity(
            {"run_id": transcript["run_id"], "status": "completed"}
        )

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


@app.command()
def list_entities(campaign_slug: str) -> None:
    """List canonical entities for a campaign."""
    from dnd_summary.db import get_session
    from dnd_summary.models import Campaign, Entity

    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise SystemExit("Campaign not found.")
        entities = (
            session.query(Entity)
            .filter_by(campaign_id=campaign.id)
            .order_by(Entity.entity_type.asc(), Entity.canonical_name.asc())
            .all()
        )
        for entity in entities:
            typer.echo(f"{entity.entity_type}\t{entity.canonical_name}")


@app.command()
def build_embeddings(
    campaign_slug: str,
    session_slug: str | None = None,
    include_all_runs: bool = False,
    replace: bool = False,
    rebuild: bool = False,
) -> None:
    """Generate semantic embeddings for campaign content."""
    from dnd_summary.db import get_session
    from dnd_summary.embedding_index import build_embeddings_for_campaign
    from dnd_summary.models import Campaign, Session

    with get_session() as session:
        campaign = session.query(Campaign).filter_by(slug=campaign_slug).first()
        if not campaign:
            raise SystemExit("Campaign not found.")
        session_obj = None
        if session_slug:
            session_obj = (
                session.query(Session)
                .filter_by(campaign_id=campaign.id, slug=session_slug)
                .first()
            )
            if not session_obj:
                raise SystemExit("Session not found.")
        try:
            stats = build_embeddings_for_campaign(
                session,
                campaign.id,
                session_id=session_obj.id if session_obj else None,
                include_all_runs=include_all_runs,
                replace=replace,
                rebuild=rebuild,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        typer.echo(
            "embeddings created={created} skipped={skipped} deleted={deleted}".format(
                **stats.__dict__
            )
        )
        typer.echo(
            "provider={provider} model={model} device={device} dims={dims} normalize={normalize}".format(
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                device=settings.embedding_device,
                dims=settings.embedding_dimensions,
                normalize=settings.embedding_normalize,
            )
        )


@app.command()
def doctor(load_models: bool = False) -> None:
    """Validate embedding/rerank configuration and storage backends."""
    from dnd_summary.db import get_session
    from dnd_summary.embeddings import _get_provider
    from dnd_summary.rerank import _get_reranker

    with get_session() as session:
        dialect = session.bind.dialect.name if session.bind else "unknown"
        if dialect == "postgresql":
            result = session.execute(
                text("SELECT extname FROM pg_extension WHERE extname='vector'")
            ).fetchone()
            if result:
                typer.echo("pgvector=ok")
            else:
                typer.echo("pgvector=missing")
        else:
            typer.echo(f"pgvector=skip (dialect={dialect})")

    typer.echo(
        "embedding provider={provider} model={model} device={device} dims={dims}".format(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            device=settings.embedding_device,
            dims=settings.embedding_dimensions,
        )
    )
    typer.echo(
        "rerank enabled={enabled} provider={provider} model={model} device={device}".format(
            enabled=settings.rerank_enabled,
            provider=settings.rerank_provider,
            model=settings.rerank_model,
            device=settings.rerank_device,
        )
    )

    if load_models:
        _get_provider()
        if settings.rerank_enabled:
            _get_reranker()
        typer.echo("models=loaded")


def _resolve_latest_run(session, session_id: str, run_id: str | None) -> Run:
    from dnd_summary.models import Run

    if run_id:
        run = session.query(Run).filter_by(id=run_id, session_id=session_id).first()
        if not run:
            raise SystemExit("Run not found for session.")
        return run
    runs = (
        session.query(Run)
        .filter_by(session_id=session_id)
        .order_by(Run.created_at.desc())
        .all()
    )
    if not runs:
        raise SystemExit("No runs found for session.")
    for run in runs:
        if run.status == "completed":
            return run
    return runs[0]


@app.command()
def inspect_usage(campaign_slug: str, session_slug: str, run_id: str | None = None) -> None:
    """Summarize LLM token usage for a session/run."""
    from dnd_summary.db import get_session
    from dnd_summary.models import Campaign, Session, SessionExtraction

    with get_session() as session:
        session_obj = (
            session.query(Session)
            .join(Campaign, Session.campaign_id == Campaign.id)
            .filter(Campaign.slug == campaign_slug, Session.slug == session_slug)
            .first()
        )
        if not session_obj:
            raise SystemExit("Session not found.")
        run = _resolve_latest_run(session, session_obj.id, run_id)
        records = (
            session.query(SessionExtraction)
            .filter_by(run_id=run.id, session_id=session_obj.id, kind="llm_usage")
            .order_by(SessionExtraction.created_at.asc(), SessionExtraction.id.asc())
            .all()
        )
        if not records:
            typer.echo("No usage records found for this run.")
            return

        totals = {
            "prompt": 0,
            "cached": 0,
            "candidates": 0,
            "total": 0,
            "non_cached": 0,
            "input_cost": 0.0,
            "cached_cost": 0.0,
            "output_cost": 0.0,
            "total_cost": 0.0,
        }
        per_kind: dict[str, dict[str, int | float]] = {}
        for record in records:
            payload = record.payload or {}
            kind = payload.get("call_kind", "unknown")
            bucket = per_kind.setdefault(
                kind,
                {
                    "prompt": 0,
                    "cached": 0,
                    "candidates": 0,
                    "total": 0,
                    "non_cached": 0,
                    "input_cost": 0.0,
                    "cached_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0,
                },
            )
            for key, field in [
                ("prompt", "prompt_token_count"),
                ("cached", "cached_content_token_count"),
                ("candidates", "candidates_token_count"),
                ("total", "total_token_count"),
                ("non_cached", "non_cached_prompt_token_count"),
            ]:
                value = payload.get(field) or 0
                totals[key] += value
                bucket[key] += value
            for key, field in [
                ("input_cost", "input_cost_usd"),
                ("cached_cost", "cached_cost_usd"),
                ("output_cost", "output_cost_usd"),
                ("total_cost", "total_cost_usd"),
            ]:
                value = payload.get(field) or 0
                totals[key] += value
                bucket[key] += value

        cache_rate = 0.0
        if totals["prompt"]:
            cache_rate = totals["cached"] / totals["prompt"]

        typer.echo(f"run_id={run.id}")
        typer.echo(f"status={run.status}")
        typer.echo(
            "totals prompt={prompt} cached={cached} non_cached={non_cached} output={candidates} total={total} cache_rate={rate:.2%}".format(
                **totals, rate=cache_rate
            )
        )
        if totals["total_cost"]:
            typer.echo(
                "totals_cost input=${input_cost:.4f} cached=${cached_cost:.4f} output=${output_cost:.4f} total=${total_cost:.4f}".format(
                    **totals
                )
            )
        typer.echo("by_call_kind:")
        for kind, stats in per_kind.items():
            line = (
                f"- {kind}: prompt={stats['prompt']} cached={stats['cached']} "
                f"non_cached={stats['non_cached']} output={stats['candidates']} total={stats['total']}"
            )
            if stats["total_cost"]:
                line += (
                    " cost=${total_cost:.4f} (input={input_cost:.4f} cached={cached_cost:.4f} output={output_cost:.4f})"
                ).format(**stats)
            typer.echo(line)


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local FastAPI server."""
    import uvicorn

    uvicorn.run("dnd_summary.api:app", host=host, port=port, reload=False)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.command()
def list_caches(
    campaign_slug: str | None = None,
    session_slug: str | None = None,
    include_expired: bool = False,
    verify_remote: bool = False,
) -> None:
    """List transcript caches stored in the database."""
    from google import genai
    from google.genai import errors

    from dnd_summary.db import get_session
    from dnd_summary.models import Campaign, Session, SessionExtraction

    client = None
    if verify_remote:
        if not settings.gemini_api_key:
            raise SystemExit("Missing Gemini API key for cache verification.")
        client = genai.Client(api_key=settings.gemini_api_key)

    with get_session() as session:
        query = (
            session.query(SessionExtraction, Session, Campaign)
            .join(Session, SessionExtraction.session_id == Session.id)
            .join(Campaign, Session.campaign_id == Campaign.id)
            .filter(SessionExtraction.kind == "transcript_cache")
            .order_by(SessionExtraction.created_at.desc())
        )
        if campaign_slug:
            query = query.filter(Campaign.slug == campaign_slug)
        if session_slug:
            query = query.filter(Session.slug == session_slug)
        rows = query.all()
        if not rows:
            typer.echo("No transcript caches found.")
            return
        now = datetime.now(timezone.utc)
        for record, session_obj, campaign in rows:
            payload = record.payload or {}
            cache_name = payload.get("cache_name")
            invalidated = payload.get("invalidated", False)
            expires_at = _parse_datetime(payload.get("expires_at"))
            if not include_expired and (invalidated or (expires_at and expires_at <= now)):
                continue
            remote_status = None
            if client and cache_name:
                try:
                    client.caches.get(name=cache_name)
                    remote_status = "ok"
                except errors.ClientError:
                    remote_status = "missing"
                except Exception:
                    remote_status = "error"
            status_bits = []
            if invalidated:
                status_bits.append("invalidated")
            if expires_at:
                status_bits.append(f"expires={expires_at.isoformat()}")
            if remote_status:
                status_bits.append(f"remote={remote_status}")
            status = "; ".join(status_bits) if status_bits else "active"
            typer.echo(
                f"{campaign.slug}/{session_obj.slug}\t{record.run_id[:8]}\t{cache_name}\t{status}"
            )


@app.command()
def clear_caches(
    campaign_slug: str | None = None,
    session_slug: str | None = None,
    all: bool = False,
    dry_run: bool = False,
) -> None:
    """Delete transcript caches and mark them invalidated in the DB."""
    from google import genai

    from dnd_summary.db import get_session
    from dnd_summary.models import Campaign, Session, SessionExtraction

    if not all and not campaign_slug and not session_slug:
        raise SystemExit("Provide --all or filter by campaign/session.")
    if not dry_run and not settings.gemini_api_key:
        raise SystemExit("Missing Gemini API key for cache deletion.")

    client = genai.Client(api_key=settings.gemini_api_key) if not dry_run else None
    now = datetime.now(timezone.utc).isoformat()

    with get_session() as session:
        query = (
            session.query(SessionExtraction, Session, Campaign)
            .join(Session, SessionExtraction.session_id == Session.id)
            .join(Campaign, Session.campaign_id == Campaign.id)
            .filter(SessionExtraction.kind == "transcript_cache")
            .order_by(SessionExtraction.created_at.desc())
        )
        if campaign_slug:
            query = query.filter(Campaign.slug == campaign_slug)
        if session_slug:
            query = query.filter(Session.slug == session_slug)
        rows = query.all()
        if not rows:
            typer.echo("No transcript caches found.")
            return

        for record, session_obj, campaign in rows:
            payload = record.payload or {}
            cache_name = payload.get("cache_name")
            if not cache_name:
                continue
            if payload.get("invalidated"):
                continue
            result = "dry-run"
            if client:
                try:
                    client.caches.delete(name=cache_name)
                    result = "deleted"
                except Exception as exc:
                    result = f"error={str(exc)[:120]}"
            record.payload = {
                **payload,
                "invalidated": True,
                "invalidated_at": now,
            }
            typer.echo(
                f"{campaign.slug}/{session_obj.slug}\t{record.run_id[:8]}\t{cache_name}\t{result}"
            )


if __name__ == "__main__":
    app()
