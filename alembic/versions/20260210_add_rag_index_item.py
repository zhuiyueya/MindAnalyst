"""add rag index item table

Revision ID: 20260210_add_rag_index_item
Revises: 20250202_add_category_fields
Create Date: 2026-02-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Computed
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "20260210_add_rag_index_item"
down_revision = "20250202_add_category_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_index_item",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("summary_id", sa.String(), nullable=False),
        sa.Column("tag", sa.String(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("video_category", sa.String(), nullable=False, server_default=sa.text("'通用领域'")),
        sa.Column("text_raw", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("text_for_embedding", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            Computed("to_tsvector('simple', coalesce(text_raw,''))", persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.ForeignKeyConstraint(["author_id"], ["author.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["contentitem.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["summary_id"], ["summary.id"], ondelete="CASCADE"),
    )

    op.create_index(op.f("ix_rag_index_item_source_type"), "rag_index_item", ["source_type"], unique=False)
    op.create_index(op.f("ix_rag_index_item_author_id"), "rag_index_item", ["author_id"], unique=False)
    op.create_index(op.f("ix_rag_index_item_content_id"), "rag_index_item", ["content_id"], unique=False)
    op.create_index(op.f("ix_rag_index_item_summary_id"), "rag_index_item", ["summary_id"], unique=False)
    op.create_index(op.f("ix_rag_index_item_tag"), "rag_index_item", ["tag"], unique=False)
    op.create_index(op.f("ix_rag_index_item_video_category"), "rag_index_item", ["video_category"], unique=False)

    op.create_index("ix_rag_index_item_tsv", "rag_index_item", ["tsv"], unique=False, postgresql_using="gin")

    op.create_index(
        "ux_rag_index_item_summary_chunk",
        "rag_index_item",
        ["source_type", "summary_id", "tag", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("source_type='summary_chunk'"),
    )
    op.create_index(
        "ux_rag_index_item_summary_short",
        "rag_index_item",
        ["source_type", "summary_id"],
        unique=True,
        postgresql_where=sa.text("source_type='summary_short'"),
    )

    op.create_index(
        "ix_rag_index_item_filter",
        "rag_index_item",
        ["source_type", "author_id", "tag"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rag_index_item_filter", table_name="rag_index_item")
    op.drop_index("ux_rag_index_item_summary_short", table_name="rag_index_item")
    op.drop_index("ux_rag_index_item_summary_chunk", table_name="rag_index_item")
    op.drop_index("ix_rag_index_item_tsv", table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_video_category"), table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_tag"), table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_summary_id"), table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_content_id"), table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_author_id"), table_name="rag_index_item")
    op.drop_index(op.f("ix_rag_index_item_source_type"), table_name="rag_index_item")
    op.drop_table("rag_index_item")
