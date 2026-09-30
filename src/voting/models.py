"""Voting campaign, vote records, email verification, and project comments data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class VotingCampaign(Base):
    __tablename__ = "voting_campaigns"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(128), default="Community Choice Awards", nullable=False)
    description = Column(Text, nullable=True)
    starts_at = Column(UTCDateTime, nullable=True)
    ends_at = Column(UTCDateTime, nullable=True)
    access_mode = Column(String(32), default="open", nullable=False)  # "open", "email", "authenticated"
    status = Column(String(32), default="draft", nullable=False)  # "draft", "active", "closed"
    results_visibility = Column(String(32), default="public_after_close", nullable=False)  # "public_after_close", "organizers_only"
    voting_method = Column(String(32), default="single", nullable=False)  # "single", "approval"
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
    event = relationship("Event", back_populates="voting_campaigns")
    votes = relationship("Vote", back_populates="campaign", cascade="all, delete-orphan")
    email_tokens = relationship("EmailVoterToken", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<VotingCampaign id={self.id} title={self.title} status={self.status} access_mode={self.access_mode}>"


class Vote(Base):
    __tablename__ = "votes"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(64), ForeignKey("voting_campaigns.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    voter_key = Column(String(128), index=True, nullable=False)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    weight = Column(Float, default=1.0, nullable=False)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    campaign = relationship("VotingCampaign", back_populates="votes")
    project = relationship("Project", back_populates="votes")
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<Vote id={self.id} campaign_id={self.campaign_id} project_id={self.project_id} voter_key={self.voter_key}>"


class EmailVoterToken(Base):
    __tablename__ = "email_voter_tokens"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    campaign_id = Column(String(64), ForeignKey("voting_campaigns.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(128), index=True, nullable=False)
    token = Column(String(128), unique=True, index=True, nullable=False)
    verification_code = Column(String(8), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at = Column(UTCDateTime, nullable=True)

    # Relationships
    campaign = relationship("VotingCampaign", back_populates="email_tokens")

    def __repr__(self) -> str:
        return f"<EmailVoterToken id={self.id} email={self.email} is_verified={self.is_verified}>"


class ProjectComment(Base):
    __tablename__ = "project_comments"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    author_name = Column(String(64), nullable=False)
    body = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    moderated_by_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    moderated_at = Column(UTCDateTime, nullable=True)
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
    project = relationship("Project", back_populates="comments")
    author = relationship("User", foreign_keys=[author_id])
    moderator = relationship("User", foreign_keys=[moderated_by_id])

    def __repr__(self) -> str:
        return f"<ProjectComment id={self.id} project_id={self.project_id} author={self.author_name} is_deleted={self.is_deleted}>"
