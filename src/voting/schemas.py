"""Pydantic schemas for voting campaigns, votes, comments, and results."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class VotingCampaignCreateRequest(BaseModel):
    event_id: str
    title: str = Field(default="Community Choice Awards", min_length=2, max_length=128)
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    access_mode: str = Field(default="open", pattern="^(open|email|authenticated)$")
    status: Optional[str] = Field(default="draft", pattern="^(draft|active|closed)$")
    voting_method: str = Field(default="single", pattern="^(single|approval)$")
    results_visibility: str = Field(default="public_after_close", pattern="^(public_after_close|organizers_only)$")


class VotingCampaignUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    access_mode: Optional[str] = Field(None, pattern="^(open|email|authenticated)$")
    status: Optional[str] = Field(None, pattern="^(draft|active|closed)$")
    voting_method: Optional[str] = Field(None, pattern="^(single|approval)$")
    results_visibility: Optional[str] = Field(None, pattern="^(public_after_close|organizers_only)$")


class VotingCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    title: str
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    access_mode: str
    status: str
    voting_method: str
    results_visibility: str
    created_at: datetime
    updated_at: datetime


class VoteCastRequest(BaseModel):
    project_id: str
    voter_key: Optional[str] = None
    weight: float = 1.0


class VoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    project_id: str
    voter_key: str
    weight: float
    created_at: datetime


class EmailTokenRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=128)


class EmailTokenConfirmRequest(BaseModel):
    email: Optional[str] = None
    token: Optional[str] = None
    code: Optional[str] = None


class EmailTokenResponse(BaseModel):
    token: str
    email: str
    verification_code: str
    is_verified: bool
    instructions: str


class ProjectCommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class ProjectCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    author_id: str
    author_name: str
    body: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class BallotProjectItem(BaseModel):
    project_id: str
    title: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    team_name: Optional[str] = None
    track_title: Optional[str] = None
    demo_url: Optional[str] = None
    repository_url: Optional[str] = None
    video_url: Optional[str] = None
    has_voted: bool = False


class BallotResponse(BaseModel):
    campaign_id: str
    campaign_title: str
    event_id: str
    status: str
    access_mode: str
    voting_method: str
    voter_key: str
    projects: List[BallotProjectItem]


class CampaignProjectResult(BaseModel):
    rank: int
    project_id: str
    project_title: str
    team_name: Optional[str] = None
    track_title: Optional[str] = None
    votes_count: int
    votes_weight: float
    percentage: float


class CampaignResultsResponse(BaseModel):
    campaign_id: str
    campaign_title: str
    event_id: str
    status: str
    results_visibility: str
    total_votes: int
    total_unique_voters: int
    results: List[CampaignProjectResult]
