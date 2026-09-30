"""Certificate and record generation data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    recipient = Column(String(128), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    award = Column(String(128), nullable=False)
    issued_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    verification_token = Column(String(128), unique=True, index=True, nullable=False)
    status = Column(String(32), default="valid", nullable=False)  # "valid", "revoked"

    # Relationships
    event = relationship("Event")
    project = relationship("Project")

    def __repr__(self) -> str:
        return f"<Certificate id={self.id} recipient={self.recipient} award={self.award} status={self.status}>"
