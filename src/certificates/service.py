"""Certificate generation, issuance, and cryptographic verification service."""

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.audit.service import log_audit_event
from src.auth.models import User
from src.certificates.models import Certificate
from src.certificates.schemas import CertificateCreateRequest
from src.events.models import Event
from src.submissions.models import Project
from src.webhooks.service import emit_webhook


def issue_certificate(
    db: Session,
    req: CertificateCreateRequest,
    user: User,
) -> Certificate:
    """Issue a verified certificate for a team or participant."""
    event = db.query(Event).filter(Event.id == req.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if req.project_id:
        project = db.query(Project).filter(Project.id == req.project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    token = secrets.token_urlsafe(32)

    cert = Certificate(
        event_id=req.event_id,
        recipient=req.recipient.strip(),
        award=req.award.strip(),
        project_id=req.project_id or None,
        issued_at=datetime.now(timezone.utc),
        verification_token=token,
        status="valid",
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)

    # Log audit event
    log_audit_event(
        db=db,
        event_type="CERTIFICATE_ISSUED",
        entity_type="Certificate",
        entity_id=cert.id,
        user_id=user.id,
        payload={
            "recipient": cert.recipient,
            "award": cert.award,
            "event_id": cert.event_id,
            "token": cert.verification_token,
        },
    )

    # Emit webhook notification
    emit_webhook(
        db=db,
        event_type="certificate.issued",
        event_id=cert.event_id,
        resource_id=cert.id,
        resource_data={
            "certificate_id": cert.id,
            "recipient": cert.recipient,
            "award": cert.award,
            "verification_token": cert.verification_token,
        },
    )

    return cert


def get_certificate(db: Session, cert_id: str) -> Certificate:
    """Retrieve certificate by ID."""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found.")
    return cert


def verify_certificate(db: Session, token: str) -> Dict[str, Any]:
    """Public verification of a certificate token."""
    cert = db.query(Certificate).filter(Certificate.verification_token == token.strip()).first()
    if not cert:
        return {
            "valid": False,
            "detail": "Certificate token not found or invalid.",
        }

    is_valid = (cert.status == "valid")
    event_title = cert.event.title if cert.event else "Unknown Event"

    return {
        "valid": is_valid,
        "certificate_id": cert.id,
        "recipient": cert.recipient,
        "event_id": cert.event_id,
        "event_title": event_title,
        "award": cert.award,
        "issued_at": cert.issued_at,
        "status": cert.status,
        "detail": "Certificate is genuine and officially registered." if is_valid else "Certificate has been revoked.",
    }


def list_certificates_for_event(db: Session, event_id: str) -> List[Certificate]:
    """List all certificates issued for an event."""
    return (
        db.query(Certificate)
        .filter(Certificate.event_id == event_id)
        .order_by(Certificate.issued_at.desc())
        .all()
    )


def revoke_certificate(db: Session, cert_id: str, user: User) -> Certificate:
    """Revoke a certificate."""
    cert = get_certificate(db, cert_id)
    cert.status = "revoked"
    db.commit()
    db.refresh(cert)

    log_audit_event(
        db=db,
        event_type="CERTIFICATE_REVOKED",
        entity_type="Certificate",
        entity_id=cert.id,
        user_id=user.id,
        payload={"recipient": cert.recipient, "award": cert.award},
    )

    return cert
