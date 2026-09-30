"""Pydantic schemas for certificate issuance and verification."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CertificateCreateRequest(BaseModel):
    event_id: str
    recipient: str = Field(..., min_length=2, max_length=128)
    award: str = Field(..., min_length=2, max_length=128)
    project_id: Optional[str] = None


class CertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    recipient: str
    award: str
    project_id: Optional[str] = None
    issued_at: datetime
    verification_token: str
    status: str
    verification_url: Optional[str] = None


class CertificateVerifyResponse(BaseModel):
    valid: bool
    certificate_id: Optional[str] = None
    recipient: Optional[str] = None
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    award: Optional[str] = None
    issued_at: Optional[datetime] = None
    status: Optional[str] = None
    detail: Optional[str] = None
