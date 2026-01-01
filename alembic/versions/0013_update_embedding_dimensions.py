from __future__ import annotations

from alembic import op

revision = "0013_update_embedding_dimensions"
down_revision = "0012_add_embedding_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_cosine")
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_embedding_cosine "
        "ON embeddings USING ivfflat (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_cosine")
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(768)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_embedding_cosine "
        "ON embeddings USING ivfflat (embedding vector_cosine_ops)"
    )
