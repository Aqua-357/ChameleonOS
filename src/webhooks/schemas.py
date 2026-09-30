"""Pydantic schemas for webhooks subsystem."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=256)
    event_id: Optional[str] = None
    secret: Optional[str] = Field(None, max_length=128)
    active: bool = True


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: Optional[str] = None
    url: str
    secret: str
    active: bool
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    endpoint_id: str
    event_type: str
    payload: Dict[str, Any]
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    success: bool
    timestamp: datetime
