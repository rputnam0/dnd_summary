from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_runs_campaign_id", "runs", ["campaign_id"])
    op.create_index("ix_runs_session_created", "runs", ["session_id", "created_at"])

    op.create_index("ix_utterances_session_start", "utterances", ["session_id", "start_ms"])

    op.create_index("ix_mentions_session_run", "mentions", ["session_id", "run_id"])
    op.create_index(
        "ix_mentions_search",
        "mentions",
        [
            sa.text(
                "to_tsvector('english', \"text\" || ' ' || coalesce(description, ''))"
            )
        ],
        postgresql_using="gin",
    )

    op.create_index("ix_scenes_session_run", "scenes", ["session_id", "run_id"])
    op.create_index("ix_events_session_run", "events", ["session_id", "run_id"])
    op.create_index("ix_threads_session_run", "threads", ["session_id", "run_id"])
    op.create_index("ix_thread_updates_session_run", "thread_updates", ["session_id", "run_id"])
    op.create_index("ix_thread_updates_thread_id", "thread_updates", ["thread_id"])

    op.create_index("ix_quotes_session_run", "quotes", ["session_id", "run_id"])
    op.create_index("ix_quotes_utterance_id", "quotes", ["utterance_id"])

    op.create_index("ix_entity_mentions_session_run", "entity_mentions", ["session_id", "run_id"])
    op.create_index("ix_entity_mentions_entity_id", "entity_mentions", ["entity_id"])

    op.create_index(
        "ix_session_extractions_session_run_kind",
        "session_extractions",
        ["session_id", "run_id", "kind", "created_at"],
    )
    op.create_index(
        "ix_llm_calls_session_run_created",
        "llm_calls",
        ["session_id", "run_id", "created_at"],
    )
    op.create_index("ix_artifacts_session_run", "artifacts", ["session_id", "run_id"])

    op.create_index(
        "ix_utterances_search",
        "utterances",
        [sa.text("to_tsvector('english', \"text\")")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_utterances_search", table_name="utterances")
    op.drop_index("ix_artifacts_session_run", table_name="artifacts")
    op.drop_index("ix_llm_calls_session_run_created", table_name="llm_calls")
    op.drop_index(
        "ix_session_extractions_session_run_kind",
        table_name="session_extractions",
    )
    op.drop_index("ix_entity_mentions_entity_id", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_session_run", table_name="entity_mentions")
    op.drop_index("ix_quotes_utterance_id", table_name="quotes")
    op.drop_index("ix_quotes_session_run", table_name="quotes")
    op.drop_index("ix_thread_updates_thread_id", table_name="thread_updates")
    op.drop_index("ix_thread_updates_session_run", table_name="thread_updates")
    op.drop_index("ix_threads_session_run", table_name="threads")
    op.drop_index("ix_events_session_run", table_name="events")
    op.drop_index("ix_scenes_session_run", table_name="scenes")
    op.drop_index("ix_mentions_search", table_name="mentions")
    op.drop_index("ix_mentions_session_run", table_name="mentions")
    op.drop_index("ix_utterances_session_start", table_name="utterances")
    op.drop_index("ix_runs_session_created", table_name="runs")
    op.drop_index("ix_runs_campaign_id", table_name="runs")
