"""add billing fields to organizations

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04

Backs the Lemon Squeezy subscription integration. Additive only — every
existing Organization row gets plan='free' via the server default, which
is correct: no org had a paid plan before this migration existed.

lemon_squeezy_customer_id/subscription_id are nullable because a free-plan
org has neither yet; they're populated the first time an org's owner
completes checkout (see routers/billing.py's webhook handler).
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("plan", sa.String, nullable=False, server_default="free"),
    )
    op.add_column(
        "organizations", sa.Column("lemon_squeezy_customer_id", sa.String, nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("lemon_squeezy_subscription_id", sa.String, nullable=True)
    )
    # Lemon Squeezy's own subscription status vocabulary (on_trial, active,
    # past_due, cancelled, expired, ...) — stored as-is rather than
    # re-mapped to a smaller enum, so a status change on their side never
    # requires a matching enum migration on ours.
    op.add_column(
        "organizations", sa.Column("subscription_status", sa.String, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("organizations", "subscription_status")
    op.drop_column("organizations", "lemon_squeezy_subscription_id")
    op.drop_column("organizations", "lemon_squeezy_customer_id")
    op.drop_column("organizations", "plan")
