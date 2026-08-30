"""add invites table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10

Supports closing the org-join security gap: joining an EXISTING org now
requires a token minted by that org's owner (POST /api/auth/invites)
instead of just matching organization_name at signup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("token", sa.String, nullable=False, unique=True, index=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("role", sa.String, nullable=True, server_default="member"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
        sa.Column("used_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("invites")
