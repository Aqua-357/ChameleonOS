"""Data exchange router for bulk import and export endpoints and dashboard."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.config import get_settings
from src.database import get_db
from src.events.models import Event
from src.data_exchange.service import (
    export_event_bundle_json,
    export_projects_csv,
    export_scores_csv,
    export_teams_csv,
    export_votes_csv,
    parse_projects_csv,
    validate_and_import_projects,
)

router = APIRouter(tags=["data_exchange"])
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def check_organizer_access(db: Session, event_id_or_slug: str, user: User) -> Event:
    event = db.query(Event).filter((Event.id == event_id_or_slug) | (Event.slug == event_id_or_slug)).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if user.role != "organizer" and event.organizer_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required.")
    return event


# --- REST API Endpoints ---

@router.post("/api/v1/events/{event_id}/import/projects")
async def api_bulk_import_projects(
    event_id: str,
    payload: Union[List[Dict[str, Any]], Dict[str, Any]] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk import projects via JSON payload (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)

    items = payload if isinstance(payload, list) else payload.get("projects", [])
    count, errors = validate_and_import_projects(db, event.id, items, current_user)

    if errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "imported_count": 0, "errors": errors},
        )

    return {"success": True, "imported_count": count, "errors": []}


@router.get("/api/v1/events/{event_id}/export/projects.csv")
def api_export_projects_csv(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all projects as CSV (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)
    csv_content = export_projects_csv(db, event.id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}-projects.csv"'},
    )


@router.get("/api/v1/events/{event_id}/export/teams.csv")
def api_export_teams_csv(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all teams as CSV (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)
    csv_content = export_teams_csv(db, event.id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}-teams.csv"'},
    )


@router.get("/api/v1/events/{event_id}/export/scores.csv")
def api_export_scores_csv(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all judge scores as CSV (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)
    csv_content = export_scores_csv(db, event.id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}-scores.csv"'},
    )


@router.get("/api/v1/events/{event_id}/export/votes.csv")
def api_export_votes_csv(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all community votes as CSV (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)
    csv_content = export_votes_csv(db, event.id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}-votes.csv"'},
    )


@router.get("/api/v1/events/{event_id}/export/bundle.json")
def api_export_bundle_json(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export complete event bundle as JSON (organizer only)."""
    event = check_organizer_access(db, event_id, current_user)
    bundle = export_event_bundle_json(db, event.id)
    return bundle


# --- HTML Dashboard Views ---

@router.get("/events/{slug}/data", response_class=HTMLResponse)
def html_data_exchange_dashboard(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Organizer data exchange dashboard for bulk import and export."""
    event = check_organizer_access(db, slug, current_user)

    return templates.TemplateResponse(
        request=request,
        name="data_exchange.html",
        context={
            "request": request,
            "settings": settings,
            "user": current_user,
            "event": event,
            "message": None,
            "errors": None,
        },
    )


@router.post("/events/{slug}/data/import", response_class=HTMLResponse)
async def html_data_import_submit(
    slug: str,
    request: Request,
    import_type: str = Form(...),  # 'csv' or 'json'
    raw_content: Optional[str] = Form(None),
    file_upload: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process file or text upload for bulk project import."""
    event = check_organizer_access(db, slug, current_user)

    content = ""
    if file_upload and file_upload.filename:
        file_bytes = await file_upload.read()
        content = file_bytes.decode("utf-8", errors="replace")
    elif raw_content:
        content = raw_content

    items: List[Dict[str, Any]] = []
    errors: List[str] = []

    if not content.strip():
        errors.append("No file uploaded or data provided.")
    else:
        try:
            if import_type == "json":
                parsed = json.loads(content)
                items = parsed if isinstance(parsed, list) else parsed.get("projects", [])
            else:
                items = parse_projects_csv(content)
        except Exception as e:
            errors.append(f"Format parsing error: {str(e)}")

    count = 0
    if not errors:
        count, import_errors = validate_and_import_projects(db, event.id, items, current_user)
        if import_errors:
            errors.extend(import_errors)

    message = f"Successfully imported {count} project(s)." if count > 0 and not errors else None

    return templates.TemplateResponse(
        request=request,
        name="data_exchange.html",
        context={
            "request": request,
            "settings": settings,
            "user": current_user,
            "event": event,
            "message": message,
            "errors": errors if errors else None,
        },
    )
