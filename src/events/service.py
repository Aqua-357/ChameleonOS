"""Event, Track, and Prize business logic service."""

import re
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.events.models import Event, Track, Prize
from src.events.schemas import EventCreateRequest, TrackCreateRequest, PrizeCreateRequest


def slugify(text: str) -> str:
    """Generate URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text)


def create_event(
    db: Session,
    request: EventCreateRequest,
    creator_id: str,
) -> Event:
    """Create a new event with configurable dates and theme config."""
    slug = slugify(request.slug or request.title)
    existing = db.query(Event).filter(Event.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An event with slug '{slug}' already exists.",
        )

    event = Event(
        title=request.title.strip(),
        slug=slug,
        description=request.description,
        theme_config=request.theme_config or {},
        phase=request.phase or "pre-event",
        start_time=request.start_time,
        end_time=request.end_time,
        created_by_id=creator_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event_by_id_or_slug(db: Session, identifier: str) -> Optional[Event]:
    """Retrieve event by ID or unique slug."""
    return db.query(Event).filter(
        (Event.id == identifier) | (Event.slug == identifier)
    ).first()


def list_events(db: Session) -> List[Event]:
    """List all events ordered by creation date."""
    return db.query(Event).order_by(Event.created_at.desc()).all()


def create_track(
    db: Session,
    event_id: str,
    request: TrackCreateRequest,
) -> Track:
    """Add a challenge track to an event."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    track = Track(
        event_id=event.id,
        title=request.title.strip(),
        description=request.description,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def create_prize(
    db: Session,
    event_id: str,
    request: PrizeCreateRequest,
) -> Prize:
    """Add a prize/bounty to an event."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    prize = Prize(
        event_id=event.id,
        track_id=request.track_id,
        title=request.title.strip(),
        description=request.description,
        amount=request.amount,
    )
    db.add(prize)
    db.commit()
    db.refresh(prize)
    return prize
