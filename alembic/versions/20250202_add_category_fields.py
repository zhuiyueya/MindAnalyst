"""add category fields

Revision ID: 20250202_add_category_fields
Revises: 
Create Date: 2025-02-02 23:12:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250202_add_category_fields"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "author",
        sa.Column(
            "category_list",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "summary",
        sa.Column(
            "short_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "summary",
        sa.Column(
            "video_category",
            sa.String(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_summary_video_category"),
        "summary",
        ["video_category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_summary_video_category"), table_name="summary")
    op.drop_column("summary", "video_category")
    op.drop_column("summary", "short_json")
    op.drop_column("author", "category_list")
