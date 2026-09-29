"""Team, Invite, and Project business logic with deadline enforcement and search."""

import secrets
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.auth.models import User
from src.events.models import Event
from src.submissions.models import Team, TeamMember, TeamInvite, Project
from src.submissions.schemas import (
    ProjectCreateDraftRequest,
    ProjectUpdateRequest,
    TeamCreateRequest,
)


def create_team(
    db: Session,
    request: TeamCreateRequest,
    lead_user: User,
) -> Team:
    """Create a new team and assign the creator as the lead member."""
    event = db.query(Event).filter(Event.id == request.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    team = Team(
        event_id=event.id,
        name=request.name.strip(),
        slug=request.slug or request.name.lower().replace(" ", "-"),
        lead_id=lead_user.id,
    )
    db.add(team)
    db.flush()

    lead_member = TeamMember(
        team_id=team.id,
        user_id=lead_user.id,
        role="lead",
    )
    db.add(lead_member)
    db.commit()
    db.refresh(team)
    return team


def create_team_invite(
    db: Session,
    team_id: str,
    inviter: User,
    invitee_email: str,
) -> TeamInvite:
    """Create a shareable team invite token."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    # Verify inviter is in the team or is admin
    is_member = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.user_id == inviter.id,
    ).first()
    if not is_member and inviter.role not in ("admin", "organizer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only team members can create invites.")

    token = secrets.token_urlsafe(24)
    invite = TeamInvite(
        team_id=team.id,
        inviter_id=inviter.id,
        invitee_email=invitee_email.strip().lower(),
        token=token,
        status="pending",
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def accept_team_invite(
    db: Session,
    token: str,
    user: User,
) -> TeamMember:
    """Accept an invite token and join the team."""
    invite = db.query(TeamInvite).filter(TeamInvite.token == token.strip()).first()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite link.")
    if invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invite has already been {invite.status}.")

    existing_member = db.query(TeamMember).filter(
        TeamMember.team_id == invite.team_id,
        TeamMember.user_id == user.id,
    ).first()
    if existing_member:
        invite.status = "accepted"
        db.commit()
        return existing_member

    member = TeamMember(
        team_id=invite.team_id,
        user_id=user.id,
        role="member",
    )
    invite.status = "accepted"
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def create_project_draft(
    db: Session,
    request: ProjectCreateDraftRequest,
    user: User,
) -> Project:
    """Create an initial draft project for a team."""
    team = db.query(Team).filter(Team.id == request.team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    # Verify user is a member of the team
    is_member = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == user.id,
    ).first()
    if not is_member and user.role not in ("admin", "organizer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be a member of the team to draft a project.")

    project = Project(
        event_id=request.event_id,
        team_id=request.team_id,
        track_id=request.track_id,
        title=request.title.strip(),
        tagline=request.tagline,
        description=request.description,
        repository_url=request.repository_url,
        demo_url=request.demo_url,
        video_url=request.video_url,
        is_submitted=False,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project_draft(
    db: Session,
    project_id: str,
    request: ProjectUpdateRequest,
    user: User,
) -> Project:
    """Update fields on an existing project draft."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Verify user is team member or admin
    is_member = db.query(TeamMember).filter(
        TeamMember.team_id == project.team_id,
        TeamMember.user_id == user.id,
    ).first()
    if not is_member and user.role not in ("admin", "organizer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be a member of the team to edit this project.")

    if request.title is not None:
        project.title = request.title.strip()
    if request.track_id is not None:
        project.track_id = request.track_id
    if request.tagline is not None:
        project.tagline = request.tagline
    if request.description is not None:
        project.description = request.description
    if request.repository_url is not None:
        project.repository_url = request.repository_url
    if request.demo_url is not None:
        project.demo_url = request.demo_url
    if request.video_url is not None:
        project.video_url = request.video_url

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


def submit_project(
    db: Session,
    project_id: str,
    user: User,
) -> Project:
    """
    Submit a project draft, enforcing strict event deadline check.
    
    IMPORTANT: The participant cannot submit after the configured deadline.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Verify team membership
    is_member = db.query(TeamMember).filter(
        TeamMember.team_id == project.team_id,
        TeamMember.user_id == user.id,
    ).first()
    if not is_member and user.role not in ("admin", "organizer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only team members can submit the project.")

    event = db.query(Event).filter(Event.id == project.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    # STRICT DEADLINE ENFORCEMENT
    now_utc = datetime.now(timezone.utc)
    if event.end_time is not None:
        event_end = event.end_time
        if event_end.tzinfo is None:
            event_end = event_end.replace(tzinfo=timezone.utc)
        if now_utc > event_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Submission closed: The deadline for this event has passed.",
            )

    if event.phase == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission closed: This event is currently closed to submissions.",
        )

    project.is_submitted = True
    project.submitted_at = now_utc
    project.updated_at = now_utc

    db.commit()
    db.refresh(project)
    return project


def list_public_projects(
    db: Session,
    event_id: Optional[str] = None,
    search: Optional[str] = None,
    track_id: Optional[str] = None,
    submitted_only: bool = True,
) -> List[Project]:
    """
    Query projects for the public gallery with search and track filtering.
    Must work without authentication.
    """
    query = db.query(Project).join(Team, Project.team_id == Team.id).options(
        joinedload(Project.team),
        joinedload(Project.track),
        joinedload(Project.event),
    )

    if submitted_only:
        query = query.filter(Project.is_submitted.is_(True))

    if event_id:
        query = query.filter(Project.event_id == event_id)

    if track_id:
        query = query.filter(Project.track_id == track_id)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Project.title.ilike(search_term),
                Project.tagline.ilike(search_term),
                Project.description.ilike(search_term),
                Team.name.ilike(search_term),
            )
        )

    return query.order_by(Project.submitted_at.desc(), Project.created_at.desc()).all()
