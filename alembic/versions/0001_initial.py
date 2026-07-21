"""Initial schema: workflow_runs, step_records, llm_usage, generated_content.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workflow", sa.String(100), index=True),
        sa.Column("started_at", sa.DateTime, index=True),
        sa.Column("aborted", sa.Boolean),
        sa.Column("duration_s", sa.Float),
    )
    op.create_table(
        "step_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("workflow_runs.id"), index=True),
        sa.Column("name", sa.String(100)),
        sa.Column("status", sa.String(20)),
        sa.Column("attempts", sa.Integer),
        sa.Column("duration_s", sa.Float),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("provider", sa.String(30), index=True),
        sa.Column("model", sa.String(80), index=True),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("latency_s", sa.Float),
        sa.Column("cost_usd", sa.Float),
        sa.Column("caller", sa.String(120), nullable=True),
    )
    op.create_table(
        "generated_content",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("channel", sa.String(60), index=True),
        sa.Column("kind", sa.String(30)),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("path_or_ref", sa.String(500), nullable=True),
        sa.Column("meta", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("generated_content")
    op.drop_table("llm_usage")
    op.drop_table("step_records")
    op.drop_table("workflow_runs")
