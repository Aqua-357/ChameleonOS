"""AuditEvent data model for tamper-evident logging."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, ForeignKey, JSON, String
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_type = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=True, index=True)
    entity_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=True)
    timestamp = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    ip_address = Column(String(45), nullable=True)

    # Relationships
    user = relationship("User", back_populates="audit_events")

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} event_type={self.event_type} timestamp={self.timestamp}>"
