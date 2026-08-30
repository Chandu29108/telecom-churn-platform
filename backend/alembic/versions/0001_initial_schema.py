"""initial schema: organizations, users, analysis_runs, customer_scores

Revision ID: 0001
Revises:
Create Date: 2026-08-06

NOTE: this was written by hand to mirror models_db.py rather than produced
by `alembic revision --autogenerate` against a live database (none was
available in the environment this was authored in). Before relying on it,
run `alembic upgrade head` against a scratch Postgres instance and diff the
result against `alembic revision --autogenerate` on the same models to
confirm there's no drift.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("email", sa.String, nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=True, server_default="member"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("trained", sa.Integer, nullable=True, server_default="0"),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("eda_summary", sa.JSON, nullable=True),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("feature_importance", sa.JSON, nullable=True),
        sa.Column("risk_counts", sa.JSON, nullable=True),
        sa.Column("insights", sa.JSON, nullable=True),
        sa.Column("recommendations", sa.JSON, nullable=True),
    )

    op.create_table(
        "customer_scores",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("customer_id", sa.String, nullable=True, index=True),
        sa.Column("churn_probability", sa.Float, nullable=True),
        sa.Column("churn_flag", sa.Integer, nullable=True),
        sa.Column("risk_tier", sa.String, nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("customer_scores")
    op.drop_table("analysis_runs")
    op.drop_table("users")
    op.drop_table("organizations")
