"""add account_type/max_seats/max_upload_rows to organizations

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13

Backs personal-vs-organization signup (see routers/auth.py's two
registration paths). Additive only — every existing Organization row
gets account_type='organization' via the server default, which is the
correct classification for every org created before this migration
(personal accounts didn't exist yet).
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("account_type", sa.String, nullable=False, server_default="organization"),
    )
    op.add_column("organizations", sa.Column("max_seats", sa.Integer, nullable=True))
    op.add_column("organizations", sa.Column("max_upload_rows", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "max_upload_rows")
    op.drop_column("organizations", "max_seats")
    op.drop_column("organizations", "account_type")
