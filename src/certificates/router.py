"""Router for certificate issuance, verification, and printable views."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.auth.dependencies import get_current_user, get_optional_user
from src.auth.models import User
from src.config import get_settings
from src.database import get_db
from src.events.models import Event
from src.submissions.models import Project
from src.certificates.models import Certificate
from src.certificates.schemas import (
    CertificateCreateRequest,
    CertificateResponse,
    CertificateVerifyResponse,
)
from src.certificates.service import (
    issue_certificate,
    get_certificate,
    verify_certificate,
    list_certificates_for_event,
    revoke_certificate,
)

router = APIRouter(tags=["certificates"])
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# --- REST API Endpoints ---

@router.post("/api/v1/certificates", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
def api_issue_certificate(
    req: CertificateCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a new certificate (organizer only)."""
    event = db.query(Event).filter(Event.id == req.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if current_user.role != "organizer" and event.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required.")

    cert = issue_certificate(db, req, current_user)
    return CertificateResponse(
        id=cert.id,
        event_id=cert.event_id,
        recipient=cert.recipient,
        award=cert.award,
        project_id=cert.project_id,
        issued_at=cert.issued_at,
        verification_token=cert.verification_token,
        status=cert.status,
        verification_url=f"/verify/certificate/{cert.verification_token}",
    )


@router.get("/api/v1/certificates/{cert_id}", response_model=CertificateResponse)
def api_get_certificate(
    cert_id: str,
    db: Session = Depends(get_db),
):
    """Get certificate details by ID."""
    cert = get_certificate(db, cert_id)
    return CertificateResponse(
        id=cert.id,
        event_id=cert.event_id,
        recipient=cert.recipient,
        award=cert.award,
        project_id=cert.project_id,
        issued_at=cert.issued_at,
        verification_token=cert.verification_token,
        status=cert.status,
        verification_url=f"/verify/certificate/{cert.verification_token}",
    )


@router.get("/api/v1/certificates/events/{event_id}", response_model=List[CertificateResponse])
def api_list_certificates(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all certificates for an event."""
    certs = list_certificates_for_event(db, event_id)
    return [
        CertificateResponse(
            id=c.id,
            event_id=c.event_id,
            recipient=c.recipient,
            award=c.award,
            project_id=c.project_id,
            issued_at=c.issued_at,
            verification_token=c.verification_token,
            status=c.status,
            verification_url=f"/verify/certificate/{c.verification_token}",
        )
        for c in certs
    ]


@router.post("/api/v1/certificates/{cert_id}/revoke", response_model=CertificateResponse)
def api_revoke_certificate(
    cert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a certificate (organizer only)."""
    cert = get_certificate(db, cert_id)
    event = db.query(Event).filter(Event.id == cert.event_id).first()
    if current_user.role != "organizer" and (not event or event.organizer_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required.")

    revoked = revoke_certificate(db, cert_id, current_user)
    return CertificateResponse(
        id=revoked.id,
        event_id=revoked.event_id,
        recipient=revoked.recipient,
        award=revoked.award,
        project_id=revoked.project_id,
        issued_at=revoked.issued_at,
        verification_token=revoked.verification_token,
        status=revoked.status,
        verification_url=f"/verify/certificate/{revoked.verification_token}",
    )


@router.get("/api/v1/certificates/verify/{token}", response_model=CertificateVerifyResponse)
def api_verify_certificate(
    token: str,
    db: Session = Depends(get_db),
):
    """Public JSON API to cryptographically verify a certificate token."""
    res = verify_certificate(db, token)
    return CertificateVerifyResponse(**res)


# --- HTML Verification and Printable Views ---

@router.get("/verify/certificate/{token}", response_class=HTMLResponse)
def html_verify_certificate(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """Public verification page for certificates."""
    result = verify_certificate(db, token)
    return templates.TemplateResponse(
        request=request,
        name="certificate_verify.html",
        context={
            "request": request,
            "settings": settings,
            "user": user,
            "result": result,
            "token": token,
        },
    )


@router.get("/certificates/{cert_id}/printable", response_class=HTMLResponse)
def html_printable_certificate(
    cert_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """Printable offline-first HTML certificate."""
    cert = get_certificate(db, cert_id)
    event = db.query(Event).filter(Event.id == cert.event_id).first()

    return templates.TemplateResponse(
        request=request,
        name="certificate_printable.html",
        context={
            "request": request,
            "settings": settings,
            "user": user,
            "cert": cert,
            "event": event,
        },
    )


@router.get("/events/{slug}/certificates", response_class=HTMLResponse)
def html_certificates_dashboard(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Organizer certificate management dashboard."""
    event = db.query(Event).filter((Event.slug == slug) | (Event.id == slug)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    if current_user.role != "organizer" and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Organizer access required.")

    certificates = list_certificates_for_event(db, event.id)
    projects = db.query(Project).filter(Project.event_id == event.id, Project.is_submitted.is_(True)).all()

    return templates.TemplateResponse(
        request=request,
        name="certificates_dashboard.html",
        context={
            "request": request,
            "settings": settings,
            "user": current_user,
            "event": event,
            "certificates": certificates,
            "projects": projects,
        },
    )


@router.post("/events/{slug}/certificates")
def html_create_certificate(
    slug: str,
    recipient: str = Form(...),
    award: str = Form(...),
    project_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue certificate from organizer dashboard form."""
    event = db.query(Event).filter((Event.slug == slug) | (Event.id == slug)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    if current_user.role != "organizer" and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Organizer access required.")

    req = CertificateCreateRequest(
        event_id=event.id,
        recipient=recipient,
        award=award,
        project_id=project_id if project_id else None,
    )
    issue_certificate(db, req, current_user)
    return RedirectResponse(url=f"/events/{event.slug}/certificates", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/events/{slug}/certificates/{cert_id}/revoke")
def html_revoke_certificate(
    slug: str,
    cert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke certificate from organizer dashboard."""
    event = db.query(Event).filter((Event.slug == slug) | (Event.id == slug)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    if current_user.role != "organizer" and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Organizer access required.")

    revoke_certificate(db, cert_id, current_user)
    return RedirectResponse(url=f"/events/{event.slug}/certificates", status_code=status.HTTP_303_SEE_OTHER)
