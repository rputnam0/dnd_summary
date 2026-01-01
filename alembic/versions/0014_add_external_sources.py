from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_add_external_sources"
down_revision = "0013_update_embedding_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_sheet_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("character_slug", sa.String(), nullable=False),
        sa.Column("character_name", sa.String(), nullable=True),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("source_hash", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "session_id",
            "character_slug",
            "source_hash",
            name="uq_character_sheet_snapshot",
        ),
    )
    op.create_table(
        "dice_rolls",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("utterance_id", sa.String(), sa.ForeignKey("utterances.id"), nullable=True),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("source_hash", sa.String(), nullable=False),
        sa.Column("roll_index", sa.Integer(), nullable=False),
        sa.Column("t_ms", sa.BigInteger(), nullable=False),
        sa.Column("character_name", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("expression", sa.String(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "session_id",
            "source_hash",
            "roll_index",
            name="uq_dice_roll",
        ),
    )


def downgrade() -> None:
    op.drop_table("dice_rolls")
    op.drop_table("character_sheet_snapshots")
