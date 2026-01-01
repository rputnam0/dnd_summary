from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_add_corrections"
down_revision = "0006_add_campaign_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_corrections_campaign_id", "corrections", ["campaign_id"])
    op.create_index("ix_corrections_session_id", "corrections", ["session_id"])
    op.create_index(
        "ix_corrections_target",
        "corrections",
        ["target_type", "target_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_corrections_target", table_name="corrections")
    op.drop_index("ix_corrections_session_id", table_name="corrections")
    op.drop_index("ix_corrections_campaign_id", table_name="corrections")
    op.drop_table("corrections")
