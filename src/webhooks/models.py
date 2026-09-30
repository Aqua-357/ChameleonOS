"""Webhook endpoint and delivery data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=True)
    url = Column(String(256), nullable=False)
    secret = Column(String(128), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event")
    deliveries = relationship("WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<WebhookEndpoint id={self.id} url={self.url} active={self.active}>"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    endpoint_id = Column(String(64), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, default=False, nullable=False)
    timestamp = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")

    def __repr__(self) -> str:
        return f"<WebhookDelivery id={self.id} event={self.event_type} success={self.success}>"
