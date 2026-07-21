"""Phase 6: content_performance table for closed-loop feedback.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_performance",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("channel", sa.String(60), index=True),
        sa.Column("video_ref", sa.String(120), index=True),
        sa.Column("category", sa.String(80), index=True, nullable=True),
        sa.Column("format", sa.String(40), nullable=True),
        sa.Column("originality_score", sa.Float, nullable=True),
        sa.Column("views", sa.Integer),
        sa.Column("watch_time_min", sa.Float),
        sa.Column("ctr", sa.Float),
        sa.Column("likes", sa.Integer),
        sa.Column("retention", sa.Float),
    )


def downgrade() -> None:
    op.drop_table("content_performance")
