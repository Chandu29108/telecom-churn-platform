"""add email verification, refresh tokens, audit logging

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12

Backs Phase 1 of the audit-driven roadmap: email verification / password
reset (email_tokens), revocable/rotating refresh tokens (refresh_tokens,
replacing pure-stateless-JWT auth), and a queryable audit trail
(audit_logs) — see app/models_db.py for the reasoning behind each table.

Additive only: no existing column is altered or dropped, and
users.is_verified defaults to 0 so this is safe to run against existing
rows without a backfill step.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String, nullable=False, unique=True, index=True),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String, nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column("replaced_by_hash", sa.String, nullable=True),
        sa.Column("user_agent", sa.String, nullable=True),
        sa.Column("ip_address", sa.String, nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("event_type", sa.String, nullable=False, index=True),
        sa.Column("resource_type", sa.String, nullable=True),
        sa.Column("resource_id", sa.String, nullable=True),
        sa.Column("success", sa.Integer, nullable=True, server_default="1"),
        sa.Column("ip_address", sa.String, nullable=True),
        sa.Column("user_agent", sa.String, nullable=True),
        sa.Column("event_metadata", sa.JSON, nullable=True),
        sa.Column("request_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("email_tokens")
    op.drop_column("users", "is_verified")
