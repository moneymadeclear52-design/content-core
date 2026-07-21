"""Phase 5 tables: prompts, prompt_versions, eval_runs, eval_results,
benchmark_runs, approvals.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), unique=True, index=True),
    )
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("prompt_id", sa.Integer, sa.ForeignKey("prompts.id"), index=True),
        sa.Column("version", sa.Integer),
        sa.Column("text", sa.Text),
        sa.Column("content_hash", sa.String(32), index=True),
        sa.Column("author", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("prompt_name", sa.String(120), index=True),
        sa.Column("prompt_version", sa.Integer, nullable=True),
        sa.Column("model", sa.String(80)),
        sa.Column("mean_score", sa.Float),
        sa.Column("pass_rate", sa.Float),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("eval_runs.id"), index=True),
        sa.Column("case_id", sa.String(120)),
        sa.Column("output", sa.Text),
        sa.Column("aggregate", sa.Float),
        sa.Column("detail", sa.Text, nullable=True),
    )
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("prompt_excerpt", sa.String(300)),
        sa.Column("provider", sa.String(30), index=True),
        sa.Column("model", sa.String(80), index=True),
        sa.Column("score", sa.Float),
        sa.Column("latency_s", sa.Float),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.DateTime, index=True),
        sa.Column("workflow", sa.String(100), index=True),
        sa.Column("item_ref", sa.String(200)),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), index=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
    )


def downgrade() -> None:
    for t in ("approvals", "benchmark_runs", "eval_results", "eval_runs",
              "prompt_versions", "prompts"):
        op.drop_table(t)
