"""Team, TeamMember, TeamInvite, and Project data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Team(Base):
    __tablename__ = "teams"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    slug = Column(String(128), nullable=True)
    lead_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event", back_populates="teams")
    lead = relationship("User", foreign_keys=[lead_id])
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    invites = relationship("TeamInvite", back_populates="team", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="team", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name}>"


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    team_id = Column(String(64), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), default="member", nullable=False)  # lead, member
    joined_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

    # Relationships
    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")

    def __repr__(self) -> str:
        return f"<TeamMember id={self.id} team_id={self.team_id} user_id={self.user_id} role={self.role}>"


class TeamInvite(Base):
    __tablename__ = "team_invites"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    team_id = Column(String(64), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_email = Column(String(128), nullable=False)
    token = Column(String(128), unique=True, index=True, nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # pending, accepted, declined, expired
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at = Column(UTCDateTime, nullable=True)

    # Relationships
    team = relationship("Team", back_populates="invites")
    inviter = relationship("User", foreign_keys=[inviter_id])

    def __repr__(self) -> str:
        return f"<TeamInvite id={self.id} email={self.invitee_email} status={self.status}>"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(String(64), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    track_id = Column(String(64), ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(128), nullable=False)
    tagline = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)
    repository_url = Column(String(256), nullable=True)
    demo_url = Column(String(256), nullable=True)
    video_url = Column(String(256), nullable=True)
    submitted_at = Column(UTCDateTime, nullable=True)
    is_submitted = Column(Boolean, default=False, nullable=False)
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
    event = relationship("Event", back_populates="projects")
    team = relationship("Team", back_populates="projects")
    track = relationship("Track", back_populates="projects")
    judge_assignments = relationship("JudgeAssignment", back_populates="project", cascade="all, delete-orphan")
    judge_scores = relationship("JudgeScore", back_populates="project", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="project", cascade="all, delete-orphan")
    comments = relationship("ProjectComment", back_populates="project", cascade="all, delete-orphan", order_by="ProjectComment.created_at.desc()")

    def __repr__(self) -> str:
        return f"<Project id={self.id} title={self.title} is_submitted={self.is_submitted}>"
