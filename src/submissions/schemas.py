"""Submission schemas for teams, invites, and projects."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TeamCreateRequest(BaseModel):
    event_id: str
    name: str = Field(..., min_length=2, max_length=128)
    slug: Optional[str] = None


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    user_id: str
    role: str


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    name: str
    slug: Optional[str] = None
    lead_id: Optional[str] = None
    members: List[TeamMemberResponse] = []


class TeamInviteCreateRequest(BaseModel):
    invitee_email: str = Field(..., min_length=3, max_length=100)


class TeamInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    invitee_email: str
    token: str
    status: str
    invite_url: Optional[str] = None


class ProjectCreateDraftRequest(BaseModel):
    event_id: str
    team_id: str
    track_id: Optional[str] = None
    title: str = Field(..., min_length=2, max_length=128)
    tagline: Optional[str] = None
    description: Optional[str] = None
    repository_url: Optional[str] = None
    demo_url: Optional[str] = None
    video_url: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    track_id: Optional[str] = None
    title: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    repository_url: Optional[str] = None
    demo_url: Optional[str] = None
    video_url: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    team_id: str
    track_id: Optional[str] = None
    title: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    repository_url: Optional[str] = None
    demo_url: Optional[str] = None
    video_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    is_submitted: bool
    created_at: Optional[datetime] = None
