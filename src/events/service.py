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

    theme_cfg = request.theme_config
    if not theme_cfg:
        from src.themes.morph import magic_morph
        theme_cfg = magic_morph(event_name=request.title, event_purpose=request.description or "")

    event = Event(
        title=request.title.strip(),
        slug=slug,
        description=request.description,
        theme_config=theme_cfg,
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


def update_event(
    db: Session,
    identifier: str,
    request: "EventUpdateRequest",
) -> Event:
    """Update event metadata, dates, or theme configuration."""
    event = get_event_by_id_or_slug(db, identifier)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if request.title is not None:
        event.title = request.title.strip()
    if request.slug is not None:
        new_slug = slugify(request.slug)
        existing = db.query(Event).filter(Event.slug == new_slug, Event.id != event.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Slug '{new_slug}' is already taken.")
        event.slug = new_slug
    if request.description is not None:
        event.description = request.description
    if request.theme_config is not None:
        event.theme_config = request.theme_config
    if request.phase is not None:
        event.phase = request.phase
    if request.start_time is not None:
        event.start_time = request.start_time
    if request.end_time is not None:
        event.end_time = request.end_time

    db.commit()
    db.refresh(event)
    return event


def list_tracks(db: Session, event_id: str) -> List[Track]:
    """Retrieve tracks for an event."""
    event = get_event_by_id_or_slug(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return db.query(Track).filter(Track.event_id == event.id).all()


def update_track(
    db: Session,
    event_id: str,
    track_id: str,
    request: "TrackUpdateRequest",
) -> Track:
    """Update track details."""
    event = get_event_by_id_or_slug(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    track = db.query(Track).filter(Track.id == track_id, Track.event_id == event.id).first()
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    if request.title is not None:
        track.title = request.title.strip()
    if request.description is not None:
        track.description = request.description

    db.commit()
    db.refresh(track)
    return track


def list_prizes(db: Session, event_id: str) -> List[Prize]:
    """Retrieve prizes for an event."""
    event = get_event_by_id_or_slug(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return db.query(Prize).filter(Prize.event_id == event.id).all()


def update_prize(
    db: Session,
    event_id: str,
    prize_id: str,
    request: "PrizeUpdateRequest",
) -> Prize:
    """Update prize details."""
    event = get_event_by_id_or_slug(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    prize = db.query(Prize).filter(Prize.id == prize_id, Prize.event_id == event.id).first()
    if not prize:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prize not found.")

    if request.title is not None:
        prize.title = request.title.strip()
    if request.description is not None:
        prize.description = request.description
    if request.amount is not None:
        prize.amount = request.amount
    if request.track_id is not None:
        prize.track_id = request.track_id

    db.commit()
    db.refresh(prize)
    return prize

