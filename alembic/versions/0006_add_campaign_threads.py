from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_add_campaign_threads"
down_revision = "0005_add_entity_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("canonical_title", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "canonical_title", name="uq_campaign_thread_title"),
    )
    op.add_column("threads", sa.Column("campaign_thread_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_threads_campaign_thread",
        "threads",
        "campaign_threads",
        ["campaign_thread_id"],
        ["id"],
    )
    op.create_index("ix_threads_campaign_thread_id", "threads", ["campaign_thread_id"])
    op.create_index("ix_campaign_threads_campaign_id", "campaign_threads", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_threads_campaign_id", table_name="campaign_threads")
    op.drop_index("ix_threads_campaign_thread_id", table_name="threads")
    op.drop_constraint("fk_threads_campaign_thread", "threads", type_="foreignkey")
    op.drop_column("threads", "campaign_thread_id")
    op.drop_table("campaign_threads")
