"""add model_versions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-10

Supports model versioning (see app/models_db.py::ModelVersion docstring):
every trained model gets a row here instead of the previous behaviour of
silently overwriting a single latest_model.joblib file on every upload with
no history and no way to tell which model is actually live.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("storage_backend", sa.String, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("feature_columns_count", sa.Integer, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Integer, nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("org_id", "version", name="uq_model_versions_org_version"),
    )
    # customer_scores.run_id was a ForeignKey without an explicit index,
    # despite being the column every dashboard query (get_run) filters and
    # sorts on. Cheap, worthwhile addition alongside this migration.
    op.create_index("ix_customer_scores_run_id", "customer_scores", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_scores_run_id", table_name="customer_scores")
    op.drop_table("model_versions")
