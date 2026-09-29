"""Audit logging service for tamper-evident timeline integrity."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.audit.models import AuditEvent


def log_audit_event(
    db: Session,
    event_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditEvent:
    """Record an immutable audit event entry."""
    audit_entry = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
        ip_address=ip_address,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def list_audit_events(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[AuditEvent]:
    """Retrieve audit events chronologically (most recent first)."""
    query = db.query(AuditEvent)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditEvent.user_id == user_id)

    return query.order_by(AuditEvent.timestamp.desc()).offset(offset).limit(limit).all()
