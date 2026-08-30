"""
Minimal admin audit viewer — owner-only, scoped to the caller's own org.
A full filterable UI is Phase 2 scope (per the roadmap); this is the
smallest useful version: list, with basic filters, enough to answer "who
did what and when" for the caller's org right now.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_owner
from ..models_db import AuditLog, User
from ..schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    event_type: Optional[str] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    query = db.query(AuditLog).filter(AuditLog.org_id == current_user.org_id)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        AuditLogOut(
            id=r.id, user_id=r.user_id, event_type=r.event_type,
            resource_type=r.resource_type, resource_id=r.resource_id,
            success=bool(r.success), ip_address=r.ip_address,
            created_at=r.created_at.isoformat(), event_metadata=r.event_metadata,
        )
        for r in rows
    ]
