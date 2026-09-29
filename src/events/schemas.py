"""Event, Track, and Prize Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrackCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = None


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    title: str
    description: Optional[str] = None


class PrizeCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=128)
    track_id: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[str] = None


class PrizeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    track_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    amount: Optional[str] = None


class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=128)
    slug: str = Field(..., min_length=3, max_length=64)
    description: Optional[str] = None
    theme_config: Optional[Dict[str, Any]] = None
    phase: str = Field(default="pre-event")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None  # Submission deadline


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    slug: str
    description: Optional[str] = None
    theme_config: Optional[Dict[str, Any]] = None
    phase: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_by_id: Optional[str] = None
    tracks: List[TrackResponse] = []
    prizes: List[PrizeResponse] = []
