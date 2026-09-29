"""Audit API endpoints with strict organizer/admin authorization."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import require_role
from src.auth.models import User
from src.audit.schemas import AuditEventResponse
from src.audit.service import list_audit_events
from src.database import get_db

router = APIRouter(tags=["audit"])


@router.get("/api/v1/audit", response_model=List[AuditEventResponse])
def api_get_audit_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Retrieve tamper-evident audit logs.
    Restricted strictly to organizers and administrators.
    """
    return list_audit_events(
        db=db,
        limit=limit,
        offset=offset,
        event_type=event_type,
        entity_type=entity_type,
    )
