from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_add_spoiler_tags"
down_revision = "0009_add_notes_bookmarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spoiler_tags",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("reveal_session_number", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "target_type",
            "target_id",
            name="uq_spoiler_target",
        ),
    )
    op.create_index("ix_spoiler_tags_campaign_id", "spoiler_tags", ["campaign_id"])
    op.create_index("ix_spoiler_tags_target", "spoiler_tags", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_spoiler_tags_target", table_name="spoiler_tags")
    op.drop_index("ix_spoiler_tags_campaign_id", table_name="spoiler_tags")
    op.drop_table("spoiler_tags")
