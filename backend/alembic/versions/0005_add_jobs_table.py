"""add jobs table for background upload processing

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12

Backs Phase 2 of the audit-driven roadmap: uploads are now processed
asynchronously via FastAPI BackgroundTasks instead of blocking the
request (see app/routers/analysis.py for the full design and the
BackgroundTasks-vs-Celery migration trigger).

Additive only.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("analysis_run_id", sa.Integer, sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="QUEUED", index=True),
        sa.Column("stage", sa.String, nullable=False, server_default="UPLOAD_VALIDATION"),
        sa.Column("progress", sa.Integer, nullable=True, server_default="0"),
        sa.Column("error_message", sa.String, nullable=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("temp_file_path", sa.String, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    # Persists SHAP top-factor breakdowns so they survive past the
    # original request — necessary now that upload processing is async
    # and results are fetched later via GET /runs/{id} (see
    # routers/analysis.py, CustomerScore.top_factors).
    op.add_column("customer_scores", sa.Column("top_factors", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("customer_scores", "top_factors")
    op.drop_table("jobs")
