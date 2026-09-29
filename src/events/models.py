"""Event, Track, and Prize data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Event(Base):
    __tablename__ = "events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    title = Column(String(128), nullable=False)
    slug = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    theme_config = Column(JSON, nullable=True)
    phase = Column(String(32), default="pre-event", nullable=False)
    start_time = Column(UTCDateTime, nullable=True)
    end_time = Column(UTCDateTime, nullable=True)
    created_by_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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
    creator = relationship("User", back_populates="organized_events", foreign_keys=[created_by_id])
    tracks = relationship("Track", back_populates="event", cascade="all, delete-orphan")
    prizes = relationship("Prize", back_populates="event", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="event", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="event", cascade="all, delete-orphan")
    rubrics = relationship("Rubric", back_populates="event", cascade="all, delete-orphan")
    judge_assignments = relationship("JudgeAssignment", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title} phase={self.phase}>"


class Track(Base):
    __tablename__ = "tracks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event", back_populates="tracks")
    projects = relationship("Project", back_populates="track")
    prizes = relationship("Prize", back_populates="track")

    def __repr__(self) -> str:
        return f"<Track id={self.id} title={self.title}>"


class Prize(Base):
    __tablename__ = "prizes"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    track_id = Column(String(64), ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(String(64), nullable=True)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event", back_populates="prizes")
    track = relationship("Track", back_populates="prizes")

    def __repr__(self) -> str:
        return f"<Prize id={self.id} title={self.title} amount={self.amount}>"
