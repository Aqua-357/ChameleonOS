"""Webhooks API endpoints and organizer management HTML views."""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event
from src.webhooks.models import WebhookDelivery, WebhookEndpoint
from src.webhooks.schemas import (
    WebhookCreateRequest,
    WebhookDeliveryResponse,
    WebhookResponse,
)
from src.webhooks.service import (
    create_webhook,
    delete_webhook,
    emit_webhook,
    list_deliveries,
    list_webhooks,
)

router = APIRouter(tags=["webhooks"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ==============================================================================
# JSON API ENDPOINTS - ORGANIZER / ADMIN ONLY
# ==============================================================================

@router.post("/api/v1/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def api_create_webhook(
    req: WebhookCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Register a new webhook endpoint."""
    return create_webhook(db, req)


@router.get("/api/v1/webhooks", response_model=List[WebhookResponse])
def api_list_webhooks(
    event_id: Optional[str] = Query(None),
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """List registered webhooks."""
    return list_webhooks(db, event_id=event_id)


@router.delete("/api/v1/webhooks/{endpoint_id}", status_code=status.HTTP_200_OK)
def api_delete_webhook(
    endpoint_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Remove a webhook endpoint."""
    delete_webhook(db, endpoint_id)
    return {"status": "deleted", "endpoint_id": endpoint_id}


@router.get("/api/v1/webhooks/{endpoint_id}/deliveries", response_model=List[WebhookDeliveryResponse])
def api_list_deliveries(
    endpoint_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Retrieve delivery history for a webhook endpoint."""
    return list_deliveries(db, endpoint_id=endpoint_id, limit=limit)


@router.post("/api/v1/webhooks/{endpoint_id}/test", response_model=List[WebhookDeliveryResponse])
def api_test_webhook(
    endpoint_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Dispatch a test ping event to the webhook endpoint."""
    endpoint = db.query(WebhookEndpoint).filter(WebhookEndpoint.id == endpoint_id).first()
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    deliveries = emit_webhook(
        db=db,
        event_type="webhook.test_ping",
        event_id=endpoint.event_id,
        resource_id=endpoint.id,
        resource_data={"message": "ChameleonOS test ping", "endpoint_id": endpoint.id},
    )
    return deliveries


# ==============================================================================
# HTML BROWSER VIEWS - ORGANIZER DASHBOARD
# ==============================================================================

@router.get("/events/{slug}/webhooks", response_class=HTMLResponse)
def organizer_webhooks_view(
    slug: str,
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Organizer Webhook Management Console."""
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    endpoints = list_webhooks(db, event_id=event.id)
    recent_deliveries = (
        db.query(WebhookDelivery)
        .order_by(WebhookDelivery.timestamp.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="webhooks_dashboard.html",
        context={
            "request": request,
            "user": user,
            "event": event,
            "endpoints": endpoints,
            "deliveries": recent_deliveries,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/events/{slug}/webhooks", response_class=HTMLResponse)
def organizer_create_webhook_post(
    slug: str,
    request: Request,
    url: str = Form(...),
    secret: Optional[str] = Form(None),
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle webhook creation form."""
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    req = WebhookCreateRequest(
        url=url.strip(),
        event_id=event.id,
        secret=secret.strip() if secret and secret.strip() else None,
        active=True,
    )
    try:
        create_webhook(db, req)
        return RedirectResponse(
            url=f"/events/{slug}/webhooks?success=Webhook+endpoint+registered+successfully!",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/events/{slug}/webhooks?error={str(e)}",
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/events/{slug}/webhooks/{endpoint_id}/delete", response_class=HTMLResponse)
def organizer_delete_webhook_post(
    slug: str,
    endpoint_id: str,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle webhook endpoint deletion."""
    delete_webhook(db, endpoint_id)
    return RedirectResponse(
        url=f"/events/{slug}/webhooks?success=Webhook+endpoint+deleted.",
        status_code=status.HTTP_302_FOUND,
    )
