from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_add_users_memberships"
down_revision = "0007_add_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "campaign_memberships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_campaign_membership"),
    )
    op.create_index("ix_campaign_memberships_campaign_id", "campaign_memberships", ["campaign_id"])
    op.create_index("ix_campaign_memberships_user_id", "campaign_memberships", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_memberships_user_id", table_name="campaign_memberships")
    op.drop_index("ix_campaign_memberships_campaign_id", table_name="campaign_memberships")
    op.drop_table("campaign_memberships")
    op.drop_table("users")
