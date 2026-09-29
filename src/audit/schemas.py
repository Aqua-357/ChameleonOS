"""Audit Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    timestamp: datetime
    ip_address: Optional[str] = None
