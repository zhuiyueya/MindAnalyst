"""make segment.embedding nullable

Revision ID: 20260210_make_segment_embedding_nullable
Revises: 20260210_add_rag_index_item
Create Date: 2026-02-10 00:00:00.000000

"""

from alembic import op
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "20260210_make_segment_embedding_nullable"
down_revision = "20260210_add_rag_index_item"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "segment",
        "embedding",
        existing_type=Vector(384),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "segment",
        "embedding",
        existing_type=Vector(384),
        nullable=False,
    )
