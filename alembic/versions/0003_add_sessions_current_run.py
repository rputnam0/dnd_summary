from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_sessions_current_run"
down_revision = "0002_add_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("current_run_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_sessions_current_run",
        "sessions",
        "runs",
        ["current_run_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_sessions_current_run", "sessions", type_="foreignkey")
    op.drop_column("sessions", "current_run_id")
