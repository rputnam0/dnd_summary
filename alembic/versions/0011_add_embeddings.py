from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_add_embeddings"
down_revision = "0010_add_spoiler_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Avoid importing app settings in migrations; use the default dimension.
    embedding_dimensions = 768

    try:
        from pgvector.sqlalchemy import Vector

        vector_type = Vector(embedding_dimensions)
    except Exception:
        vector_type = sa.JSON()

    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", vector_type, nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "target_type",
            "target_id",
            "model",
            "version",
            name="uq_embedding_target_model_version",
        ),
    )

    op.create_index(
        "ix_embeddings_campaign_type",
        "embeddings",
        ["campaign_id", "target_type"],
    )
    op.create_index(
        "ix_embeddings_campaign_session",
        "embeddings",
        ["campaign_id", "session_id"],
    )
    op.create_index(
        "ix_embeddings_campaign_run",
        "embeddings",
        ["campaign_id", "run_id"],
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_embeddings_embedding_cosine "
            "ON embeddings USING ivfflat (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_cosine")

    op.drop_index("ix_embeddings_campaign_run", table_name="embeddings")
    op.drop_index("ix_embeddings_campaign_session", table_name="embeddings")
    op.drop_index("ix_embeddings_campaign_type", table_name="embeddings")
    op.drop_table("embeddings")
