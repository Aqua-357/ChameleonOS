"""Webhook service handling endpoint registration, HMAC signing, and safe non-blocking delivery."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.webhooks.models import WebhookDelivery, WebhookEndpoint
from src.webhooks.schemas import WebhookCreateRequest


def create_webhook(
    db: Session,
    req: WebhookCreateRequest,
) -> WebhookEndpoint:
    """Register a new webhook endpoint with an optional event scope and signing secret."""
    secret = req.secret or secrets.token_hex(24)
    endpoint = WebhookEndpoint(
        event_id=req.event_id or None,
        url=req.url.strip(),
        secret=secret,
        active=req.active,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return endpoint


def list_webhooks(
    db: Session,
    event_id: Optional[str] = None,
) -> List[WebhookEndpoint]:
    """List registered webhooks, optionally filtered by event."""
    query = db.query(WebhookEndpoint)
    if event_id:
        query = query.filter((WebhookEndpoint.event_id == event_id) | (WebhookEndpoint.event_id.is_(None)))
    return query.order_by(WebhookEndpoint.created_at.desc()).all()


def delete_webhook(
    db: Session,
    endpoint_id: str,
) -> bool:
    """Delete a webhook endpoint."""
    endpoint = db.query(WebhookEndpoint).filter(WebhookEndpoint.id == endpoint_id).first()
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")
    db.delete(endpoint)
    db.commit()
    return True


def list_deliveries(
    db: Session,
    endpoint_id: str,
    limit: int = 50,
) -> List[WebhookDelivery]:
    """Retrieve delivery history for a specific endpoint."""
    return (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.timestamp.desc())
        .limit(limit)
        .all()
    )


def emit_webhook(
    db: Session,
    event_type: str,
    event_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_data: Optional[Dict[str, Any]] = None,
) -> List[WebhookDelivery]:
    """
    Emit a webhook event to all matching active endpoints.
    Payload is signed with HMAC-SHA256 using the endpoint's secret.
    Delivery failures are recorded in the database and NEVER crash the main transaction.
    """
    query = db.query(WebhookEndpoint).filter(WebhookEndpoint.active.is_(True))
    if event_id:
        query = query.filter((WebhookEndpoint.event_id == event_id) | (WebhookEndpoint.event_id.is_(None)))
    else:
        query = query.filter(WebhookEndpoint.event_id.is_(None))

    endpoints = query.all()
    if not endpoints:
        return []

    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "event": event_type,
        "timestamp": timestamp,
        "event_id": event_id,
        "resource_id": resource_id,
        "data": resource_data or {},
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    deliveries = []
    for endpoint in endpoints:
        sig = hmac.new(endpoint.secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ChameleonOS-Webhooks/1.0",
            "X-Chameleon-Signature": f"sha256={sig}",
            "X-Chameleon-Event": event_type,
        }

        status_code = None
        response_body = None
        success = False

        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.post(endpoint.url, content=payload_bytes, headers=headers)
                status_code = res.status_code
                response_body = res.text[:500]
                success = (200 <= res.status_code < 300)
        except Exception as exc:
            status_code = None
            response_body = f"Delivery failed: {str(exc)}"[:500]
            success = False

        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
            status_code=status_code,
            response_body=response_body,
            success=success,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(delivery)
        deliveries.append(delivery)

    try:
        db.commit()
    except Exception:
        db.rollback()

    return deliveries
