"""Event, Track, and Prize API and HTML routes."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_optional_user, require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event
from src.events.schemas import (
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
    PrizeCreateRequest,
    PrizeResponse,
    PrizeUpdateRequest,
    TrackCreateRequest,
    TrackResponse,
    TrackUpdateRequest,
)
from src.events.service import (
    create_event,
    create_prize,
    create_track,
    get_event_by_id_or_slug,
    list_events,
    list_prizes,
    list_tracks,
    update_event,
    update_prize,
    update_track,
)
from src.fixtures import parse_iso_datetime

router = APIRouter(tags=["events"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ==============================================================================
# JSON API ENDPOINTS
# ==============================================================================

@router.get("/api/v1/events", response_model=List[EventResponse])
def api_list_events(db: Session = Depends(get_db)):
    return list_events(db)


@router.post("/api/v1/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def api_create_event(
    req: EventCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    event = create_event(db, req, creator_id=current_user.id)
    return event


@router.get("/api/v1/events/{id_or_slug}", response_model=EventResponse)
def api_get_event(id_or_slug: str, db: Session = Depends(get_db)):
    event = get_event_by_id_or_slug(db, id_or_slug)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return event


@router.put("/api/v1/events/{id_or_slug}", response_model=EventResponse)
def api_update_event(
    id_or_slug: str,
    req: EventUpdateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Update event configuration, metadata, or phase."""
    return update_event(db, id_or_slug, req)


@router.get("/api/v1/events/{event_id}/tracks", response_model=List[TrackResponse])
def api_list_tracks(event_id: str, db: Session = Depends(get_db)):
    """List challenge tracks for an event."""
    return list_tracks(db, event_id)


@router.post("/api/v1/events/{event_id}/tracks", response_model=TrackResponse, status_code=status.HTTP_201_CREATED)
def api_create_track(
    event_id: str,
    req: TrackCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    return create_track(db, event_id, req)


@router.put("/api/v1/events/{event_id}/tracks/{track_id}", response_model=TrackResponse)
def api_update_track(
    event_id: str,
    track_id: str,
    req: TrackUpdateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Update challenge track details."""
    return update_track(db, event_id, track_id, req)


@router.get("/api/v1/events/{event_id}/prizes", response_model=List[PrizeResponse])
def api_list_prizes(event_id: str, db: Session = Depends(get_db)):
    """List prizes configured for an event."""
    return list_prizes(db, event_id)


@router.post("/api/v1/events/{event_id}/prizes", response_model=PrizeResponse, status_code=status.HTTP_201_CREATED)
def api_create_prize(
    event_id: str,
    req: PrizeCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    return create_prize(db, event_id, req)


@router.put("/api/v1/events/{event_id}/prizes/{prize_id}", response_model=PrizeResponse)
def api_update_prize(
    event_id: str,
    prize_id: str,
    req: PrizeUpdateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Update prize details."""
    return update_prize(db, event_id, prize_id, req)


# ==============================================================================
# HTML VIEW ROUTES
# ==============================================================================

@router.get("/events", response_class=HTMLResponse)
def events_list_view(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    events = list_events(db)
    return templates.TemplateResponse(
        request=request,
        name="events_list.html",
        context={"request": request, "events": events, "user": user},
    )


@router.get("/events/new", response_class=HTMLResponse)
def event_new_view(
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
):
    return templates.TemplateResponse(
        request=request,
        name="event_form.html",
        context={"request": request, "user": user, "error": None},
    )


@router.post("/events/new", response_class=HTMLResponse)
def event_new_post(
    request: Request,
    title: str = Form(...),
    slug: str = Form(...),
    description: Optional[str] = Form(None),
    phase: str = Form("pre-event"),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    archetype: Optional[str] = Form(None),
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    parsed_start = parse_iso_datetime(start_time)
    parsed_end = parse_iso_datetime(end_time)

    theme_cfg = None
    if archetype and archetype != "auto":
        from src.themes.archetypes import ARCHETYPES
        if archetype in ARCHETYPES:
            theme_cfg = {
                "archetype": archetype,
                "name": ARCHETYPES[archetype]["name"],
                "description": ARCHETYPES[archetype]["description"],
                "tokens": ARCHETYPES[archetype]["tokens"],
            }

    req = EventCreateRequest(
        title=title,
        slug=slug,
        description=description,
        theme_config=theme_cfg,
        phase=phase,
        start_time=parsed_start,
        end_time=parsed_end,
    )
    try:
        event = create_event(db, req, creator_id=user.id)
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="event_form.html",
            context={"request": request, "user": user, "error": e.detail},
            status_code=e.status_code,
        )

    return RedirectResponse(url=f"/events/{event.slug}", status_code=status.HTTP_302_FOUND)


@router.get("/events/{slug}", response_class=HTMLResponse)
def event_detail_view(
    slug: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    event = get_event_by_id_or_slug(db, slug)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    now_utc = datetime.now(timezone.utc)
    is_closed = False
    if event.end_time and now_utc > event.end_time:
        is_closed = True
    if event.phase == "closed":
        is_closed = True

    return templates.TemplateResponse(
        request=request,
        name="event_detail.html",
        context={
            "request": request,
            "event": event,
            "user": user,
            "is_closed": is_closed,
            "now_utc": now_utc,
        },
    )
