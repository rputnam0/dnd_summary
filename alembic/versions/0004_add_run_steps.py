from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_add_run_steps"
down_revision = "0003_add_sessions_current_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_run_steps_session_id", "run_steps", ["session_id"])
    op.create_index("ix_run_steps_status", "run_steps", ["status"])


def downgrade() -> None:
    op.drop_index("ix_run_steps_status", table_name="run_steps")
    op.drop_index("ix_run_steps_session_id", table_name="run_steps")
    op.drop_index("ix_run_steps_run_id", table_name="run_steps")
    op.drop_table("run_steps")
