from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_add_notes_bookmarks"
down_revision = "0008_add_users_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_campaign_id", "notes", ["campaign_id"])
    op.create_index("ix_notes_session_id", "notes", ["session_id"])
    op.create_index("ix_notes_target", "notes", ["target_type", "target_id"])

    op.create_table(
        "bookmarks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "target_type",
            "target_id",
            "created_by",
            name="uq_bookmark_target",
        ),
    )
    op.create_index("ix_bookmarks_campaign_id", "bookmarks", ["campaign_id"])
    op.create_index("ix_bookmarks_session_id", "bookmarks", ["session_id"])
    op.create_index("ix_bookmarks_target", "bookmarks", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_bookmarks_target", table_name="bookmarks")
    op.drop_index("ix_bookmarks_session_id", table_name="bookmarks")
    op.drop_index("ix_bookmarks_campaign_id", table_name="bookmarks")
    op.drop_table("bookmarks")
    op.drop_index("ix_notes_target", table_name="notes")
    op.drop_index("ix_notes_session_id", table_name="notes")
    op.drop_index("ix_notes_campaign_id", table_name="notes")
    op.drop_table("notes")
