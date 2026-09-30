"""Team and Project API and HTML routes with search, filtering, and deadline enforcement."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_optional_user, require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event, Track
from src.submissions.models import Project, Team, TeamMember
from src.submissions.schemas import (
    ProjectCreateDraftRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    TeamCreateRequest,
    TeamInviteCreateRequest,
    TeamInviteResponse,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)
from src.submissions.service import (
    accept_team_invite,
    create_project_draft,
    create_team,
    create_team_invite,
    get_project,
    get_team,
    list_public_projects,
    submit_project,
    update_project_draft,
    update_team,
)

router = APIRouter(tags=["submissions"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ==============================================================================
# JSON API ENDPOINTS - PUBLIC GALLERY (NO AUTHENTICATION REQUIRED)
# ==============================================================================

@router.get("/api/v1/projects", response_model=List[ProjectResponse])
def api_list_projects(
    event_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    track_id: Optional[str] = Query(None),
    submitted_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Public Project Gallery query endpoint.
    MUST work without authentication for visitors.
    Supports text search and track filtering.
    """
    projects = list_public_projects(
        db=db,
        event_id=event_id,
        search=search,
        track_id=track_id,
        submitted_only=submitted_only,
    )
    return projects


# ==============================================================================
# JSON API ENDPOINTS - TEAMS & INVITES
# ==============================================================================

@router.post("/api/v1/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def api_create_team(
    req: TeamCreateRequest,
    current_user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    return create_team(db, req, lead_user=current_user)


@router.get("/api/v1/teams/{team_id}", response_model=TeamResponse)
def api_get_team(team_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific team."""
    return get_team(db, team_id)


@router.put("/api/v1/teams/{team_id}", response_model=TeamResponse)
def api_update_team(
    team_id: str,
    req: TeamUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update team name (Team lead or Organizer only)."""
    return update_team(db, team_id, req, current_user)


@router.post("/api/v1/teams/{team_id}/invites", response_model=TeamInviteResponse, status_code=status.HTTP_201_CREATED)
def api_create_invite(
    team_id: str,
    req: TeamInviteCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invite = create_team_invite(db, team_id, current_user, req.invitee_email)
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/teams/join?token={invite.token}"
    resp = TeamInviteResponse.model_validate(invite)
    resp.invite_url = invite_url
    return resp


@router.post("/api/v1/teams/join", response_model=TeamMemberResponse)
def api_join_team(
    token: str = Query(...),
    current_user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    member = accept_team_invite(db, token, current_user)
    return member


# ==============================================================================
# JSON API ENDPOINTS - PROJECT DRAFTS & SUBMISSION (WITH DEADLINE ENFORCEMENT)
# ==============================================================================

@router.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
def api_get_project(project_id: str, db: Session = Depends(get_db)):
    """Retrieve single project by ID (public access)."""
    return get_project(db, project_id)

@router.post("/api/v1/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def api_create_draft(
    req: ProjectCreateDraftRequest,
    current_user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    return create_project_draft(db, req, user=current_user)


@router.put("/api/v1/projects/{project_id}", response_model=ProjectResponse)
def api_update_draft(
    project_id: str,
    req: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_project_draft(db, project_id, req, user=current_user)


@router.post("/api/v1/projects/{project_id}/submit", response_model=ProjectResponse)
def api_submit_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a project draft, enforcing event deadline check."""
    return submit_project(db, project_id, user=current_user)


# ==============================================================================
# HTML VIEW ROUTES - PUBLIC GALLERY & PROJECT MANAGEMENT
# ==============================================================================

@router.get("/gallery", response_class=HTMLResponse)
def gallery_view(
    request: Request,
    event_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    track_id: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Public Project Gallery HTML Page.
    Accessible by all visitors without authentication.
    """
    projects = list_public_projects(
        db=db,
        event_id=event_id,
        search=search,
        track_id=track_id,
        submitted_only=True,
    )
    events = db.query(Event).all()
    tracks = db.query(Track).all()

    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
        context={
            "request": request,
            "projects": projects,
            "events": events,
            "tracks": tracks,
            "active_event_id": event_id,
            "active_track_id": track_id,
            "search_query": search or "",
            "user": user,
        },
    )


@router.get("/projects/new", response_class=HTMLResponse)
def project_new_view(
    request: Request,
    event_id: Optional[str] = Query(None),
    user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    # Find teams where user is member
    memberships = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    user_team_ids = [m.team_id for m in memberships]
    teams = db.query(Team).filter(Team.id.in_(user_team_ids)).all() if user_team_ids else []

    events = db.query(Event).all()
    tracks = db.query(Track).all()

    return templates.TemplateResponse(
        request=request,
        name="project_form.html",
        context={
            "request": request,
            "user": user,
            "teams": teams,
            "events": events,
            "tracks": tracks,
            "project": None,
            "error": None,
        },
    )


@router.post("/projects/new", response_class=HTMLResponse)
def project_new_post(
    request: Request,
    event_id: str = Form(...),
    team_id: str = Form(...),
    title: str = Form(...),
    track_id: Optional[str] = Form(None),
    tagline: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    repository_url: Optional[str] = Form(None),
    demo_url: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    req = ProjectCreateDraftRequest(
        event_id=event_id,
        team_id=team_id,
        track_id=track_id or None,
        title=title,
        tagline=tagline,
        description=description,
        repository_url=repository_url,
        demo_url=demo_url,
        video_url=video_url,
    )
    try:
        project = create_project_draft(db, req, user)
        return RedirectResponse(url=f"/projects/{project.id}/edit", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        memberships = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
        user_team_ids = [m.team_id for m in memberships]
        teams = db.query(Team).filter(Team.id.in_(user_team_ids)).all() if user_team_ids else []
        events = db.query(Event).all()
        tracks = db.query(Track).all()

        return templates.TemplateResponse(
            request=request,
            name="project_form.html",
            context={
                "request": request,
                "user": user,
                "teams": teams,
                "events": events,
                "tracks": tracks,
                "project": None,
                "error": e.detail,
            },
            status_code=e.status_code,
        )


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
def project_edit_view(
    project_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    event = project.event
    tracks = db.query(Track).filter(Track.event_id == project.event_id).all()

    now_utc = datetime.now(timezone.utc)
    is_closed = False
    if event.end_time and now_utc > event.end_time:
        is_closed = True
    if event.phase == "closed":
        is_closed = True

    return templates.TemplateResponse(
        request=request,
        name="project_form.html",
        context={
            "request": request,
            "user": user,
            "project": project,
            "event": event,
            "tracks": tracks,
            "teams": [project.team],
            "is_closed": is_closed,
            "error": None,
            "success": None,
        },
    )


@router.post("/projects/{project_id}/edit", response_class=HTMLResponse)
def project_edit_post(
    project_id: str,
    request: Request,
    title: str = Form(...),
    track_id: Optional[str] = Form(None),
    tagline: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    repository_url: Optional[str] = Form(None),
    demo_url: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    action: str = Form("save"),  # "save" or "submit"
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = ProjectUpdateRequest(
        title=title,
        track_id=track_id or None,
        tagline=tagline,
        description=description,
        repository_url=repository_url,
        demo_url=demo_url,
        video_url=video_url,
    )
    try:
        project = update_project_draft(db, project_id, req, user)
        if action == "submit":
            project = submit_project(db, project_id, user)
            return RedirectResponse(url="/gallery", status_code=status.HTTP_302_FOUND)
        
        return RedirectResponse(url=f"/projects/{project.id}/edit", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        project = db.query(Project).filter(Project.id == project_id).first()
        event = project.event if project else None
        tracks = db.query(Track).filter(Track.event_id == project.event_id).all() if project else []
        return templates.TemplateResponse(
            request=request,
            name="project_form.html",
            context={
                "request": request,
                "user": user,
                "project": project,
                "event": event,
                "tracks": tracks,
                "teams": [project.team] if project else [],
                "is_closed": True if "deadline" in str(e.detail).lower() else False,
                "error": e.detail,
                "success": None,
            },
            status_code=e.status_code,
        )


@router.get("/teams/new", response_class=HTMLResponse)
def team_new_view(
    request: Request,
    event_id: Optional[str] = Query(None),
    user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    events = db.query(Event).all()
    return templates.TemplateResponse(
        request=request,
        name="team_form.html",
        context={"request": request, "user": user, "events": events, "active_event_id": event_id, "error": None},
    )


@router.post("/teams/new", response_class=HTMLResponse)
def team_new_post(
    request: Request,
    event_id: str = Form(...),
    name: str = Form(...),
    user: User = Depends(require_role("participant", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    try:
        team = create_team(db, TeamCreateRequest(event_id=event_id, name=name), lead_user=user)
        return RedirectResponse(url=f"/teams/{team.id}", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        events = db.query(Event).all()
        return templates.TemplateResponse(
            request=request,
            name="team_form.html",
            context={"request": request, "user": user, "events": events, "active_event_id": event_id, "error": e.detail},
            status_code=e.status_code,
        )


@router.get("/teams/{team_id}", response_class=HTMLResponse)
def team_detail_view(
    team_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    base_url = str(request.base_url).rstrip("/")
    invites = [
        {
            "id": inv.id,
            "email": inv.invitee_email,
            "status": inv.status,
            "url": f"{base_url}/teams/join?token={inv.token}",
        }
        for inv in team.invites
    ]

    return templates.TemplateResponse(
        request=request,
        name="team_detail.html",
        context={
            "request": request,
            "team": team,
            "user": user,
            "invites": invites,
            "error": None,
        },
    )


@router.post("/teams/{team_id}/invites", response_class=HTMLResponse)
def team_invite_post(
    team_id: str,
    request: Request,
    invitee_email: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        create_team_invite(db, team_id, user, invitee_email)
        return RedirectResponse(url=f"/teams/{team_id}", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        team = db.query(Team).filter(Team.id == team_id).first()
        base_url = str(request.base_url).rstrip("/")
        invites = [
            {
                "id": inv.id,
                "email": inv.invitee_email,
                "status": inv.status,
                "url": f"{base_url}/teams/join?token={inv.token}",
            }
            for inv in (team.invites if team else [])
        ]
        return templates.TemplateResponse(
            request=request,
            name="team_detail.html",
            context={
                "request": request,
                "team": team,
                "user": user,
                "invites": invites,
                "error": e.detail,
            },
            status_code=e.status_code,
        )


@router.get("/teams/join", response_class=HTMLResponse)
def team_join_view(
    token: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse(url=f"/login?next=/teams/join?token={token}", status_code=status.HTTP_302_FOUND)

    try:
        member = accept_team_invite(db, token, user)
        return RedirectResponse(url=f"/teams/{member.team_id}", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="team_join_error.html",
            context={"request": request, "user": user, "error": e.detail},
            status_code=e.status_code,
        )
