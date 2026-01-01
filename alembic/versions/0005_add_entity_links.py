from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_add_entity_links"
down_revision = "0004_add_run_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_entities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "entity_id", name="uq_event_entity"),
    )
    op.create_index("ix_event_entities_event_id", "event_entities", ["event_id"])
    op.create_index("ix_event_entities_entity_id", "event_entities", ["entity_id"])
    op.create_index("ix_event_entities_run_id", "event_entities", ["run_id"])
    op.create_index("ix_event_entities_session_id", "event_entities", ["session_id"])

    op.create_table(
        "scene_entities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("scene_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "entity_id", name="uq_scene_entity"),
    )
    op.create_index("ix_scene_entities_scene_id", "scene_entities", ["scene_id"])
    op.create_index("ix_scene_entities_entity_id", "scene_entities", ["entity_id"])
    op.create_index("ix_scene_entities_run_id", "scene_entities", ["run_id"])
    op.create_index("ix_scene_entities_session_id", "scene_entities", ["session_id"])

    op.create_table(
        "thread_entities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "entity_id", name="uq_thread_entity"),
    )
    op.create_index("ix_thread_entities_thread_id", "thread_entities", ["thread_id"])
    op.create_index("ix_thread_entities_entity_id", "thread_entities", ["entity_id"])
    op.create_index("ix_thread_entities_run_id", "thread_entities", ["run_id"])
    op.create_index("ix_thread_entities_session_id", "thread_entities", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_thread_entities_session_id", table_name="thread_entities")
    op.drop_index("ix_thread_entities_run_id", table_name="thread_entities")
    op.drop_index("ix_thread_entities_entity_id", table_name="thread_entities")
    op.drop_index("ix_thread_entities_thread_id", table_name="thread_entities")
    op.drop_table("thread_entities")

    op.drop_index("ix_scene_entities_session_id", table_name="scene_entities")
    op.drop_index("ix_scene_entities_run_id", table_name="scene_entities")
    op.drop_index("ix_scene_entities_entity_id", table_name="scene_entities")
    op.drop_index("ix_scene_entities_scene_id", table_name="scene_entities")
    op.drop_table("scene_entities")

    op.drop_index("ix_event_entities_session_id", table_name="event_entities")
    op.drop_index("ix_event_entities_run_id", table_name="event_entities")
    op.drop_index("ix_event_entities_entity_id", table_name="event_entities")
    op.drop_index("ix_event_entities_event_id", table_name="event_entities")
    op.drop_table("event_entities")
