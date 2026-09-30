"""Rubric, RubricCriterion, JudgeAssignment, and JudgeScore data models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from src.database import Base, UTCDateTime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event", back_populates="rubrics")
    criteria = relationship("RubricCriterion", back_populates="rubric", cascade="all, delete-orphan", order_by="RubricCriterion.order_index")

    def __repr__(self) -> str:
        return f"<Rubric id={self.id} name={self.name}>"


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    rubric_id = Column(String(64), ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, default=1.0, nullable=False)
    min_score = Column(Float, default=1.0, nullable=False)
    max_score = Column(Float, default=10.0, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    # Relationships
    rubric = relationship("Rubric", back_populates="criteria")
    scores = relationship("JudgeScore", back_populates="criterion", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<RubricCriterion id={self.id} name={self.name} weight={self.weight}>"


class JudgeAssignment(Base):
    __tablename__ = "judge_assignments"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    judge_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(32), default="assigned", nullable=False)  # assigned, in_progress, completed
    created_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("judge_id", "project_id", name="uq_judge_project"),
    )

    # Relationships
    event = relationship("Event", back_populates="judge_assignments")
    judge = relationship("User", back_populates="judge_assignments")
    project = relationship("Project", back_populates="judge_assignments")
    scores = relationship("JudgeScore", back_populates="assignment")

    def __repr__(self) -> str:
        return f"<JudgeAssignment id={self.id} judge_id={self.judge_id} project_id={self.project_id}>"


class JudgeScore(Base):
    __tablename__ = "judge_scores"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    assignment_id = Column(String(64), ForeignKey("judge_assignments.id", ondelete="SET NULL"), nullable=True)
    judge_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    criterion_id = Column(String(64), ForeignKey("rubric_criteria.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=True)  # Nullable to tolerate missing score entries
    feedback = Column(Text, nullable=True)
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

    __table_args__ = (
        # Uniqueness ensures each judge scores a criterion for a project at most once,
        # while permitting identical scores across judges and criteria without collision.
        UniqueConstraint("judge_id", "project_id", "criterion_id", name="uq_judge_project_criterion"),
    )

    # Relationships
    assignment = relationship("JudgeAssignment", back_populates="scores")
    judge = relationship("User", back_populates="judge_scores")
    project = relationship("Project", back_populates="judge_scores")
    criterion = relationship("RubricCriterion", back_populates="scores")

    def __repr__(self) -> str:
        return f"<JudgeScore id={self.id} judge_id={self.judge_id} project_id={self.project_id} score={self.score}>"


class JudgeParticipationRecord(Base):
    __tablename__ = "judge_participation_records"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    event_id = Column(String(64), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    judge_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    judge_name = Column(String(128), nullable=False)
    judge_email = Column(String(255), nullable=False)
    total_assigned = Column(Integer, nullable=False)
    total_evaluated = Column(Integer, nullable=False)
    canonical_payload = Column(Text, nullable=False)
    signature = Column(String(128), nullable=False)
    issued_at = Column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = relationship("Event")
    judge = relationship("User")

    def __repr__(self) -> str:
        return f"<JudgeParticipationRecord id={self.id} judge_id={self.judge_id} evaluated={self.total_evaluated}/{self.total_assigned}>"

