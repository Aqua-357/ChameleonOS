"""Judging schemas for rubrics, assignments, score submissions, and results."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# RUBRIC & CRITERIA SCHEMAS
# ==============================================================================

class CriterionCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.1, le=10.0)
    min_score: float = Field(default=1.0, ge=0.0)
    max_score: float = Field(default=10.0, ge=1.0)
    order_index: int = Field(default=0, ge=0)


class CriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rubric_id: str
    name: str
    description: Optional[str] = None
    weight: float
    min_score: float
    max_score: float
    order_index: int


class RubricCreateRequest(BaseModel):
    name: str = Field(default="Default Judging Rubric", min_length=2, max_length=128)
    description: Optional[str] = None
    criteria: List[CriterionCreateRequest] = []


class RubricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    name: str
    description: Optional[str] = None
    criteria: List[CriterionResponse] = []


# ==============================================================================
# JUDGE INVITATION & ASSIGNMENT SCHEMAS
# ==============================================================================

class JudgeInviteRequest(BaseModel):
    event_id: str
    email: str = Field(..., min_length=3, max_length=100)
    username: Optional[str] = None


class JudgeInviteResponse(BaseModel):
    user_id: str
    email: str
    username: str
    role: str
    message: str


class AssignmentCreateRequest(BaseModel):
    event_id: str
    judge_id: str
    project_id: str


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    judge_id: str
    project_id: str
    status: str
    created_at: datetime


class AutoAssignRequest(BaseModel):
    judges_per_project: int = Field(default=2, ge=1, le=10)


class AutoAssignResponse(BaseModel):
    event_id: str
    total_assigned: int
    judges_count: int
    projects_count: int


# ==============================================================================
# SCORE SUBMISSION & QUEUE SCHEMAS
# ==============================================================================

class CriterionScoreInput(BaseModel):
    criterion_id: str
    score: float
    feedback: Optional[str] = None


class ProjectScoreSubmissionRequest(BaseModel):
    scores: List[CriterionScoreInput]
    general_feedback: Optional[str] = None


class JudgeScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: Optional[str] = None
    judge_id: str
    project_id: str
    criterion_id: str
    score: Optional[float] = None
    feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JudgeQueueItemResponse(BaseModel):
    assignment_id: str
    project_id: str
    project_title: str
    project_tagline: Optional[str] = None
    track_title: Optional[str] = None
    team_name: Optional[str] = None
    status: str
    demo_url: Optional[str] = None
    repository_url: Optional[str] = None
    scored_criteria_count: int
    total_criteria_count: int


# ==============================================================================
# PROGRESS & RESULTS SCHEMAS
# ==============================================================================

class JudgeProgressItem(BaseModel):
    judge_id: str
    username: str
    total_assigned: int
    completed: int
    in_progress: int
    completion_rate: float


class JudgingProgressResponse(BaseModel):
    event_id: str
    total_assignments: int
    completed_assignments: int
    in_progress_assignments: int
    pending_assignments: int
    completion_percentage: float
    judge_breakdown: List[JudgeProgressItem] = []


class ProjectCriterionScoreDetail(BaseModel):
    criterion_id: str
    criterion_name: str
    weight: float
    average_score: Optional[float] = None


class ProjectResultItem(BaseModel):
    rank: int
    project_id: str
    project_title: str
    team_name: str
    track_title: Optional[str] = None
    weighted_score: float
    evaluations_count: int
    criteria_scores: List[ProjectCriterionScoreDetail] = []


class EventResultsResponse(BaseModel):
    event_id: str
    event_title: str
    total_projects: int
    results: List[ProjectResultItem] = []
