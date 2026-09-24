"""
- Organization: the tenant boundary. Every analysis run, model file, and
  user belongs to exactly one org, so two telecom clients (or two teams
  within one) never see each other's uploaded data or trained models.
- Invite: single-use, expiring tokens that gate joining an EXISTING org
  (see the Invite class below for why this exists).
- User: an account within an org. Auth is JWT-based (see security.py /
  deps.py); passwords are never stored in plaintext.
- AnalysisRun: one row per CSV upload/analysis, holds the aggregate results
  (metrics, insights, recommendations) as JSON so the frontend can re-fetch
  a past run without re-running the model. Scoped to org_id so runs are
  tenant-isolated.
- ModelVersion: one row per trained model artifact, giving model storage a
  real history/rollback path instead of a single overwritten file.
- CustomerScore: one row per scored customer per run, which is what powers
  the "high-risk customer table" and the CSV/campaign export endpoint.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Invite(Base):
    """
    Closes the tenant-boundary gap where registration used to auto-admit
    anyone typing a matching organization_name as a "member". Membership in
    an EXISTING org now requires a token an owner explicitly generated (see
    routers/auth.py::create_invite) — created org membership (a brand-new
    org name) still works as a single self-serve step, since there's no
    existing tenant boundary to protect in that case.
    """
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    role = Column(String, default="member")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    org = relationship("Organization")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # "personal" | "organization" — see routers/auth.py's two registration
    # paths. A personal workspace is a normal Organization row underneath
    # (every other table already scopes by org_id, so this reuses that
    # boundary rather than inventing a parallel one) — it just can't grow
    # past one seat and gets a smaller default upload cap.
    account_type = Column(String, nullable=False, default="organization")
    # NULL means "no cap beyond the global default" — only personal
    # workspaces set this to a real number today. Left on Organization
    # (not a hardcoded constant) so a future paid tier could raise it
    # per-org without a code change.
    max_seats = Column(Integer, nullable=True)
    max_upload_rows = Column(Integer, nullable=True)

    # Billing (Lemon Squeezy). "free" is every org's default and the only
    # value that existed before this was added — see alembic 0007.
    # Nullable customer/subscription IDs because a free-plan org has
    # neither yet; subscription_status mirrors Lemon Squeezy's own
    # vocabulary as-is rather than a re-mapped enum (see the migration's
    # docstring for why).
    plan = Column(String, nullable=False, default="free")
    lemon_squeezy_customer_id = Column(String, nullable=True)
    lemon_squeezy_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, nullable=True)

    users = relationship("User", back_populates="org")
    runs = relationship("AnalysisRun", back_populates="org")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="member")  # "owner" | "member"
    created_at = Column(DateTime, default=datetime.utcnow)
    # 0 until the user clicks the emailed verification link. Not currently
    # used to block login (see routers/auth.py docstring for why) — it's
    # surfaced on /me so the frontend can nudge unverified users, and is a
    # deliberate, narrower first step than hard-gating access.
    is_verified = Column(Integer, default=0)

    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    org = relationship("Organization", back_populates="users")

    @property
    def organization_name(self) -> str:
        """Convenience accessor so UserOut can return the org's display
        name without every caller needing a separate query/join."""
        return self.org.name if self.org else ""

    @property
    def account_type(self) -> str:
        """Convenience accessor mirroring organization_name above — lets
        the frontend show/hide team features (invites, audit log) based
        on the user's own account without a second request."""
        return self.org.account_type if self.org else "organization"


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    row_count = Column(Integer)
    trained = Column(Integer, default=0)  # 1 if labels were available to train/evaluate

    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    org = relationship("Organization", back_populates="runs")

    eda_summary = Column(JSON)
    metrics = Column(JSON)
    feature_importance = Column(JSON)
    risk_counts = Column(JSON)
    insights = Column(JSON)
    recommendations = Column(JSON)

    scores = relationship("CustomerScore", back_populates="run", cascade="all, delete-orphan")


class ModelVersion(Base):
    """
    One row per trained model, per org, per upload that included labels.
    This is what turns model persistence from "there's a file on disk
    called latest_model.joblib that gets silently overwritten on every
    upload" into an actual history: which model is live right now
    (is_active), what it was trained on (run_id -> AnalysisRun), what its
    metrics were, and — because old versions are never deleted, only
    deactivated — a rollback path if a newly trained model turns out worse.

    The actual model/columns bytes live in whatever ModelStore backend is
    configured (local disk in dev, Cloudflare R2 in production — see
    model_store.py); this table is the metadata/index over those artifacts,
    not the artifacts themselves.
    """
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("org_id", "version", name="uq_model_versions_org_version"),)

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)  # sequential per org, starting at 1
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)
    storage_backend = Column(String, nullable=False)  # "local" | "r2" — which ModelStore wrote it
    metrics = Column(JSON)
    feature_columns_count = Column(Integer)
    row_count = Column(Integer)
    is_active = Column(Integer, default=0)  # 1 = currently served for scoring/prediction
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class EmailToken(Base):
    """
    Single-use, expiring tokens for both email verification and password
    reset — same shape, different `purpose`, so one table/index covers
    both instead of duplicating near-identical columns twice.

    Only the SHA-256 hash of the token is ever stored (`token_hash`), never
    the token itself — matches how passwords are handled (never store the
    secret, only something you can verify it against). The raw token only
    ever exists in memory long enough to email it and is unrecoverable
    from the database, including by anyone with direct DB access.
    """
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    purpose = Column(String, nullable=False)  # "verify_email" | "reset_password"
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    user = relationship("User")


class RefreshToken(Base):
    """
    Backs the httpOnly-cookie refresh flow (see routers/auth.py). Storing
    these server-side — hashed, same reasoning as EmailToken — is what
    turns "JWT auth" into something that can actually be revoked: logging
    out, resetting a password, or detecting a replayed/stolen refresh
    token all work by flipping `revoked_at` here, which a stateless JWT
    alone can never support (a bare JWT is valid until it expires, full
    stop, no matter what happens server-side in the meantime).
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    # Set when this token is rotated out for a newer one. If a token with
    # this set is ever presented again, it's a replay of an already-used
    # refresh token (e.g. a stolen cookie) — see routers/auth.py::refresh,
    # which treats that as a compromise signal and revokes the whole chain.
    replaced_by_hash = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    user = relationship("User")


class AuditLog(Base):
    """
    Queryable audit trail — deliberately separate from application logs
    (logging_config.py), which are for debugging/ops and aren't a
    structured, filterable record of who-did-what. This table is that
    record. Phase 1 wires it into auth events only (register, login,
    logout, verify, reset); Phase 2 extends coverage to data/model/org
    events per the audit report's Part 6/Part 9 recommendations, using
    the same table and helper (see app/audit.py) rather than a new one.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    success = Column(Integer, default=1)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    request_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Job(Base):
    """
    Backs asynchronous upload processing (see routers/analysis.py). A row
    is created the instant a file is accepted, before any processing
    starts, so the frontend gets a job_id to poll immediately instead of
    the request blocking for however long training + SHAP takes.

    Uses FastAPI BackgroundTasks, not a separate worker/queue — see the
    "when to migrate to Celery + Redis" note in routers/analysis.py for
    why that's the right call at this scale and what would change it.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)

    status = Column(String, nullable=False, default="QUEUED", index=True)
    stage = Column(String, nullable=False, default="UPLOAD_VALIDATION")
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(String, nullable=True)

    filename = Column(String, nullable=False)
    row_count = Column(Integer, nullable=True)
    # Where the uploaded bytes are temporarily held so the background task
    # (which runs after the request/response cycle) can read them, and so
    # a failed job can be retried without asking the user to re-upload.
    # Deleted once the job reaches a terminal state and isn't retried
    # again within RETRY_RETENTION — see _cleanup_temp_file.
    temp_file_path = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class CustomerScore(Base):
    __tablename__ = "customer_scores"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), index=True)  # was missing an index despite being the column every dashboard query filters/sorts by
    customer_id = Column(String, index=True)
    churn_probability = Column(Float)
    churn_flag = Column(Integer)
    risk_tier = Column(String, index=True)
    # SHAP top-factor breakdown, persisted only for the top-explained rows
    # (see TOP_N_EXPLAIN in routers/analysis.py) — previously computed but
    # never stored, so GET /runs/{id} (a later request, possibly after a
    # background job) had no way to return it. NULL for the rows outside
    # the top-N explained set.
    top_factors = Column(JSON, nullable=True)

    run = relationship("AnalysisRun", back_populates="scores")
