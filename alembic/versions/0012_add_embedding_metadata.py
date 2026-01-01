from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_add_embedding_metadata"
down_revision = "0011_add_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("embeddings", sa.Column("text_hash", sa.String(), nullable=True))
    op.add_column("embeddings", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("embeddings", sa.Column("dimensions", sa.Integer(), nullable=True))
    op.add_column("embeddings", sa.Column("normalized", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("embeddings", "normalized")
    op.drop_column("embeddings", "dimensions")
    op.drop_column("embeddings", "provider")
    op.drop_column("embeddings", "text_hash")
