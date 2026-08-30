"""
Queryable audit trail — see AuditLog in models_db.py for why this exists
alongside (not instead of) app logging. `log_event` is the single entry
point every router should call so the shape stays consistent as event
coverage grows in later phases.

Never pass secrets (passwords, tokens, full JWTs) into `metadata` — this
table is not append-only-encrypted and is meant to be admin-readable.
"""
import logging

from fastapi import Request
from sqlalchemy.orm import Session

from .models_db import AuditLog

logger = logging.getLogger("churn_platform.audit")


def log_event(
    db: Session,
    request: Request | None,
    event_type: str,
    *,
    user_id: int | None = None,
    org_id: int | None = None,
    success: bool = True,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    request_id = getattr(request.state, "request_id", None) if request else None

    entry = AuditLog(
        org_id=org_id,
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        success=1 if success else 0,
        ip_address=ip,
        user_agent=user_agent,
        event_metadata=metadata or {},
        request_id=request_id,
    )
    db.add(entry)
    # Deliberately committed immediately rather than left for the caller's
    # eventual db.commit(): an audit entry for an event that already
    # happened (e.g. a failed login) must survive even if the rest of the
    # request's transaction later rolls back.
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("audit.log_event_failed event_type=%s", event_type)
