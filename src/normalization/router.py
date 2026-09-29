"""Score Normalization API routes and the Organizer Normalization Lab."""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event
from src.normalization.schemas import NormalizationLabResponse
from src.normalization.service import calculate_normalization

router = APIRouter(tags=["normalization"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/api/v1/normalization/events/{event_id}", response_model=NormalizationLabResponse)
def api_get_normalization(
    event_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Compute and retrieve cross-judge score normalization and ranking shifts.
    Restricted strictly to organizers and administrators.
    """
    return calculate_normalization(db=db, event_id=event_id)


@router.get("/events/{slug}/normalization-lab", response_class=HTMLResponse)
def html_normalization_lab(
    slug: str,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Organizer Normalization Lab:
    Interactive dashboard showing raw scores, normalized scores, rank deltas,
    judge bias personas, and algorithmic explanations.
    """
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    lab_data = calculate_normalization(db=db, event_id=event.id)

    return templates.TemplateResponse(
        request=request,
        name="normalization_lab.html",
        context={
            "request": request,
            "user": current_user,
            "event": event,
            "lab": lab_data,
        },
    )
