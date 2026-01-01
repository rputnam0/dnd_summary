from __future__ import annotations

from typer.testing import CliRunner

from dnd_summary.cli import app
from dnd_summary.models import Embedding, SessionExtraction
from tests.factories import (
    create_campaign,
    create_event,
    create_participant,
    create_run,
    create_session,
    create_session_extraction,
    create_utterance,
)


runner = CliRunner()


def test_show_config_outputs_defaults():
    result = runner.invoke(app, ["show-config"])
    assert result.exit_code == 0
    assert "database_url=" in result.output


def test_inspect_usage_summarizes_tokens(db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, status="completed")
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="llm_usage",
        payload={
            "call_kind": "extract",
            "prompt_token_count": 100,
            "cached_content_token_count": 20,
            "candidates_token_count": 50,
            "total_token_count": 150,
            "non_cached_prompt_token_count": 80,
            "input_cost_usd": 0.01,
            "cached_cost_usd": 0.0,
            "output_cost_usd": 0.02,
            "total_cost_usd": 0.03,
        },
    )
    db_session.commit()

    result = runner.invoke(app, ["inspect-usage", "alpha", "session_1"])

    assert result.exit_code == 0
    assert "by_call_kind:" in result.output
    assert "extract" in result.output


def test_list_caches_lists_records(db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="transcript_cache",
        payload={"cache_name": "cache-1", "invalidated": False},
    )
    db_session.commit()

    result = runner.invoke(app, ["list-caches", "--campaign-slug", "alpha"])

    assert result.exit_code == 0
    assert "alpha/session_1" in result.output


def test_clear_caches_marks_invalidated(db_session, settings_overrides):
    settings_overrides(gemini_api_key=None)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="transcript_cache",
        payload={"cache_name": "cache-1", "invalidated": False},
    )
    db_session.commit()

    result = runner.invoke(app, ["clear-caches", "--all", "--dry-run"])

    assert result.exit_code == 0
    record = db_session.query(SessionExtraction).filter_by(kind="transcript_cache").one()
    assert record.payload["invalidated"] is True


def test_build_embeddings_command(db_session, settings_overrides):
    settings_overrides(embedding_dimensions=8)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utterance = create_utterance(db_session, session_obj=session_obj, participant=participant)
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Goblin ambush",
        evidence=[{"utterance_id": utterance.id, "char_start": 0, "char_end": 5}],
        entities=["Goblin"],
    )
    db_session.commit()

    result = runner.invoke(app, ["build-embeddings", "alpha", "--include-all-runs"])

    assert result.exit_code == 0
    assert "embeddings" in result.output
    assert db_session.query(Embedding).filter_by(campaign_id=campaign.id).count() > 0


def test_doctor_reports_config(db_session):
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "embedding provider" in result.output
    assert "rerank enabled" in result.output


def test_verify_cache_reports_cached_tokens(db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, status="completed")
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="llm_usage",
        payload={"cached_content_token_count": 12},
    )
    db_session.commit()

    result = runner.invoke(app, ["verify-cache", "alpha", "session_1"])

    assert result.exit_code == 0
    assert "cached_tokens=12" in result.output


def test_resume_partial_dry_run(db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign, slug="session_2")
    create_run(db_session, campaign=campaign, session_obj=session_obj, status="partial")
    db_session.commit()

    result = runner.invoke(app, ["resume-partial", "alpha", "session_2", "--dry-run"])

    assert result.exit_code == 0
    assert "Resume dry-run" in result.output
