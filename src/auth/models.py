"""Authentication data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="participant")  # organizer, judge, participant, admin
    is_active = Column(Boolean, default=True, nullable=False)
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
    organized_events = relationship("Event", back_populates="creator", foreign_keys="Event.created_by_id")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    judge_assignments = relationship("JudgeAssignment", back_populates="judge", cascade="all, delete-orphan")
    judge_scores = relationship("JudgeScore", back_populates="judge", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"
