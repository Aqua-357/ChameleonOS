"""Voting and comments API routes and HTML view handlers."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_optional_user, require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event
from src.submissions.models import Project
from src.audit.models import AuditEvent
from src.voting.models import ProjectComment, Vote, VotingCampaign
from src.voting.schemas import (
    BallotProjectItem,
    BallotResponse,
    CampaignResultsResponse,
    EmailTokenConfirmRequest,
    EmailTokenRequest,
    EmailTokenResponse,
    ProjectCommentCreateRequest,
    ProjectCommentResponse,
    VoteCastRequest,
    VoteResponse,
    VotingCampaignCreateRequest,
    VotingCampaignResponse,
    VotingCampaignUpdateRequest,
)
from src.voting.service import (
    activate_voting_campaign,
    add_project_comment,
    cast_vote,
    close_voting_campaign,
    confirm_email_token,
    create_voting_campaign,
    get_campaign_results,
    get_deterministic_ballot,
    list_project_comments,
    moderate_project_comment,
    request_email_token,
    update_voting_campaign,
)

router = APIRouter(tags=["voting"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    if request.client:
        return request.client.host
    return "127.0.0.1"


# ==============================================================================
# JSON API - VOTING CAMPAIGN MANAGEMENT
# ==============================================================================

@router.post("/api/v1/voting/campaigns", response_model=VotingCampaignResponse, status_code=status.HTTP_201_CREATED)
def api_create_voting_campaign(
    req: VotingCampaignCreateRequest,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Create a new community voting campaign (Organizer/Admin only)."""
    campaign = create_voting_campaign(
        db=db,
        req=req,
        user=current_user,
        ip_address=get_client_ip(request),
    )
    return campaign


@router.get("/api/v1/voting/campaigns/{campaign_id}", response_model=VotingCampaignResponse)
def api_get_voting_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve details for a specific voting campaign."""
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")
    return campaign


@router.put("/api/v1/voting/campaigns/{campaign_id}", response_model=VotingCampaignResponse)
def api_update_voting_campaign(
    campaign_id: str,
    req: VotingCampaignUpdateRequest,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Update voting campaign settings (Organizer/Admin only)."""
    return update_voting_campaign(
        db=db,
        campaign_id=campaign_id,
        req=req,
        user=current_user,
        ip_address=get_client_ip(request),
    )


@router.post("/api/v1/voting/campaigns/{campaign_id}/activate", response_model=VotingCampaignResponse)
def api_activate_voting_campaign(
    campaign_id: str,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Activate a voting campaign (Organizer/Admin only)."""
    return activate_voting_campaign(
        db=db,
        campaign_id=campaign_id,
        user=current_user,
        ip_address=get_client_ip(request),
    )


@router.post("/api/v1/voting/campaigns/{campaign_id}/close", response_model=VotingCampaignResponse)
def api_close_voting_campaign(
    campaign_id: str,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Close an active voting campaign (Organizer/Admin only)."""
    return close_voting_campaign(
        db=db,
        campaign_id=campaign_id,
        user=current_user,
        ip_address=get_client_ip(request),
    )


# ==============================================================================
# JSON API - DETERMINISTIC BALLOT
# ==============================================================================

@router.get("/api/v1/voting/campaigns/{campaign_id}/ballot", response_model=BallotResponse)
def api_get_ballot(
    campaign_id: str,
    request: Request,
    voter_key: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve deterministic pseudo-random ordered project ballot.
    Seed is derived on the server from (campaign_id:voter_key).
    """
    effective_key = voter_key or request.headers.get("X-Voter-Key") or request.cookies.get("voter_token")
    if not effective_key:
        if current_user:
            effective_key = f"auth:{current_user.id}"
        else:
            effective_key = f"anon:{get_client_ip(request)}"

    campaign, items = get_deterministic_ballot(db, campaign_id, effective_key)

    project_items = [BallotProjectItem(**item) for item in items]
    return BallotResponse(
        campaign_id=campaign.id,
        campaign_title=campaign.title,
        event_id=campaign.event_id,
        status=campaign.status,
        access_mode=campaign.access_mode,
        voting_method=campaign.voting_method,
        voter_key=effective_key,
        projects=project_items,
    )


# ==============================================================================
# JSON API - OFFLINE EMAIL VERIFICATION
# ==============================================================================

@router.post("/api/v1/voting/campaigns/{campaign_id}/request-email-token", response_model=EmailTokenResponse)
def api_request_email_token(
    campaign_id: str,
    req: EmailTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Request an offline-compatible email verification code/token."""
    tok = request_email_token(
        db=db,
        campaign_id=campaign_id,
        email=req.email,
        ip_address=get_client_ip(request),
    )
    return EmailTokenResponse(
        token=tok.token,
        email=tok.email,
        verification_code=tok.verification_code,
        is_verified=tok.is_verified,
        instructions=f"Offline Mode: Use verification code '{tok.verification_code}' or token to confirm.",
    )


@router.post("/api/v1/voting/campaigns/{campaign_id}/verify-email", response_model=EmailTokenResponse)
def api_verify_email_token(
    campaign_id: str,
    req: EmailTokenConfirmRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Confirm email token or verification code (offline verification)."""
    tok = confirm_email_token(
        db=db,
        campaign_id=campaign_id,
        token=req.token,
        code=req.code,
        email=req.email,
        ip_address=get_client_ip(request),
    )
    # Set cookie for easy browser access
    response.set_cookie(
        key="voter_token",
        value=tok.token,
        httponly=False,
        max_age=86400,
        samesite="lax",
    )
    return EmailTokenResponse(
        token=tok.token,
        email=tok.email,
        verification_code=tok.verification_code,
        is_verified=tok.is_verified,
        instructions="Email successfully verified for this voting campaign.",
    )


# ==============================================================================
# JSON API - VOTE CASTING (ANTI-ABUSE)
# ==============================================================================

@router.post("/api/v1/voting/campaigns/{campaign_id}/votes", response_model=VoteResponse, status_code=status.HTTP_201_CREATED)
def api_cast_vote(
    campaign_id: str,
    req: VoteCastRequest,
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Cast a community ballot vote with strict anti-abuse enforcement:
    - Rate limiting
    - Duplicate detection
    - Access mode check (open, email, authenticated)
    - Full audit logging
    """
    voter_key = req.voter_key or request.headers.get("X-Voter-Key") or request.cookies.get("voter_token")

    # If open voting and no voter key supplied, generate persistent client key
    if not voter_key and not current_user:
        voter_key = secrets.token_urlsafe(16)
        response.set_cookie(key="voter_token", value=voter_key, max_age=86400 * 30, samesite="lax")

    vote = cast_vote(
        db=db,
        campaign_id=campaign_id,
        project_id=req.project_id,
        voter_key=voter_key,
        user=current_user,
        ip_address=get_client_ip(request),
        weight=req.weight,
    )
    return vote


# ==============================================================================
# JSON API - RESULTS (RESULT SECRECY ENFORCED)
# ==============================================================================

@router.get("/api/v1/voting/campaigns/{campaign_id}/results", response_model=CampaignResultsResponse)
def api_get_campaign_results(
    campaign_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve voting results with strict result secrecy:
    - While active: ONLY organizers/admins can view live tally (HTTP 403 for others).
    - When closed: Public if configured as 'public_after_close', otherwise organizer-only.
    """
    return get_campaign_results(
        db=db,
        campaign_id=campaign_id,
        user=current_user,
    )


# ==============================================================================
# JSON API - PROJECT COMMENTS & MODERATION
# ==============================================================================

@router.post("/api/v1/projects/{project_id}/comments", response_model=ProjectCommentResponse, status_code=status.HTTP_201_CREATED)
def api_create_comment(
    project_id: str,
    req: ProjectCommentCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Post an authenticated comment on a public project."""
    comment = add_project_comment(
        db=db,
        project_id=project_id,
        body=req.body,
        user=current_user,
        ip_address=get_client_ip(request),
    )
    return comment


@router.get("/api/v1/projects/{project_id}/comments", response_model=List[ProjectCommentResponse])
def api_list_comments(
    project_id: str,
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
):
    """List comments on a project."""
    return list_project_comments(db, project_id, include_deleted=include_deleted)


@router.delete("/api/v1/projects/{project_id}/comments/{comment_id}", response_model=ProjectCommentResponse)
def api_moderate_comment(
    project_id: str,
    comment_id: str,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Moderate and soft-delete a project comment (Organizers/Admins only)."""
    return moderate_project_comment(
        db=db,
        project_id=project_id,
        comment_id=comment_id,
        user=current_user,
        ip_address=get_client_ip(request),
    )


# ==============================================================================
# HTML BROWSER VIEWS - ORGANIZER CONTROLS & DASHBOARD
# ==============================================================================

@router.get("/events/{slug}/voting", response_class=HTMLResponse)
def organizer_voting_dashboard_view(
    slug: str,
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Organizer Voting Management & Anti-Abuse Audit Console."""
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    campaigns = (
        db.query(VotingCampaign)
        .filter(VotingCampaign.event_id == event.id)
        .order_by(VotingCampaign.created_at.desc())
        .all()
    )

    # Active campaign results preview (Organizers can see live progress)
    active_campaign = next((c for c in campaigns if c.status == "active"), None) or (campaigns[0] if campaigns else None)
    results_data = None
    if active_campaign:
        results_data = get_campaign_results(db, active_campaign.id, user=user)

    # Fetch voting audit records
    audit_logs = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.entity_type == "VotingCampaign",
            AuditEvent.event_type.in_([
                "VOTE_ACCEPTED",
                "VOTE_DUPLICATE_REJECTED",
                "VOTE_RATE_LIMITED",
                "VOTE_REJECTED_UNAUTHORIZED",
                "VOTE_REJECTED_CAMPAIGN_INACTIVE",
                "VOTE_REJECTED_WINDOW",
                "VOTING_CAMPAIGN_CREATED",
                "VOTING_CAMPAIGN_ACTIVATED",
                "VOTING_CAMPAIGN_CLOSED",
            ]),
        )
        .order_by(AuditEvent.timestamp.desc())
        .limit(50)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="voting_dashboard.html",
        context={
            "request": request,
            "user": user,
            "event": event,
            "campaigns": campaigns,
            "active_campaign": active_campaign,
            "results_data": results_data,
            "audit_logs": audit_logs,
            "error": None,
            "success": None,
        },
    )


@router.post("/events/{slug}/voting/campaigns", response_class=HTMLResponse)
def organizer_create_campaign_post(
    slug: str,
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    access_mode: str = Form("open"),
    voting_method: str = Form("single"),
    results_visibility: str = Form("public_after_close"),
    starts_at: Optional[str] = Form(None),
    ends_at: Optional[str] = Form(None),
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle organizer campaign creation form."""
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    dt_start = None
    if starts_at and starts_at.strip():
        try:
            dt_start = datetime.fromisoformat(starts_at.strip()).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    dt_end = None
    if ends_at and ends_at.strip():
        try:
            dt_end = datetime.fromisoformat(ends_at.strip()).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    req = VotingCampaignCreateRequest(
        event_id=event.id,
        title=title,
        description=description,
        access_mode=access_mode,
        voting_method=voting_method,
        results_visibility=results_visibility,
        starts_at=dt_start,
        ends_at=dt_end,
    )
    create_voting_campaign(db, req, user, ip_address=get_client_ip(request))
    return RedirectResponse(url=f"/events/{slug}/voting", status_code=status.HTTP_302_FOUND)


@router.post("/events/{slug}/voting/campaigns/{campaign_id}/activate", response_class=HTMLResponse)
def organizer_activate_campaign_post(
    slug: str,
    campaign_id: str,
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle organizer activation action."""
    activate_voting_campaign(db, campaign_id, user, ip_address=get_client_ip(request))
    return RedirectResponse(url=f"/events/{slug}/voting", status_code=status.HTTP_302_FOUND)


@router.post("/events/{slug}/voting/campaigns/{campaign_id}/close", response_class=HTMLResponse)
def organizer_close_campaign_post(
    slug: str,
    campaign_id: str,
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle organizer close action."""
    close_voting_campaign(db, campaign_id, user, ip_address=get_client_ip(request))
    return RedirectResponse(url=f"/events/{slug}/voting", status_code=status.HTTP_302_FOUND)


# ==============================================================================
# HTML BROWSER VIEWS - PUBLIC BALLOT & VOTING EXPERIENCE
# ==============================================================================

@router.get("/voting/campaigns/{campaign_id}/ballot", response_class=HTMLResponse)
def public_ballot_view(
    campaign_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Public Voting Ballot with deterministic randomized project ordering."""
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    voter_key = request.cookies.get("voter_token")
    if not voter_key:
        if user:
            voter_key = f"auth:{user.id}"
        else:
            voter_key = f"anon:{get_client_ip(request)}"

    campaign, items = get_deterministic_ballot(db, campaign_id, voter_key)

    # Check if results are viewable
    results_data = None
    results_sealed = False
    if campaign.status == "closed":
        if campaign.results_visibility == "public_after_close" or (user and user.role in ["organizer", "admin"]):
            results_data = get_campaign_results(db, campaign_id, user=user)
    else:
        # Campaign active / draft: sealed to public
        if user and user.role in ["organizer", "admin"]:
            results_data = get_campaign_results(db, campaign_id, user=user)
        else:
            results_sealed = True

    return templates.TemplateResponse(
        request=request,
        name="voting_ballot.html",
        context={
            "request": request,
            "user": user,
            "campaign": campaign,
            "projects": items,
            "voter_key": voter_key,
            "results_data": results_data,
            "results_sealed": results_sealed,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/voting/campaigns/{campaign_id}/vote", response_class=HTMLResponse)
def public_ballot_vote_post(
    campaign_id: str,
    request: Request,
    project_id: str = Form(...),
    voter_key: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Handle ballot vote submission from HTML form."""
    effective_key = voter_key or request.cookies.get("voter_token")
    if not effective_key and not user:
        effective_key = secrets.token_urlsafe(16)

    try:
        vote = cast_vote(
            db=db,
            campaign_id=campaign_id,
            project_id=project_id,
            voter_key=effective_key,
            user=user,
            ip_address=get_client_ip(request),
        )
        resp = RedirectResponse(
            url=f"/voting/campaigns/{campaign_id}/ballot?success=Your+vote+was+successfully+recorded!",
            status_code=status.HTTP_302_FOUND,
        )
        if effective_key:
            resp.set_cookie(key="voter_token", value=effective_key, max_age=86400 * 30, samesite="lax")
        return resp
    except HTTPException as e:
        resp = RedirectResponse(
            url=f"/voting/campaigns/{campaign_id}/ballot?error={e.detail}",
            status_code=status.HTTP_302_FOUND,
        )
        if effective_key:
            resp.set_cookie(key="voter_token", value=effective_key, max_age=86400 * 30, samesite="lax")
        return resp


# ==============================================================================
# HTML BROWSER VIEWS - PUBLIC PROJECT DETAIL & COMMENTS
# ==============================================================================

@router.get("/projects/{project_id}", response_class=HTMLResponse)
def public_project_detail_view(
    project_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Public Project Detail Page with External Deliverables,
    Community Comments, and Live Voting Widget.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Retrieve non-deleted comments (or all if organizer/admin)
    is_organizer = user and user.role in ["organizer", "admin"]
    comments = list_project_comments(db, project_id, include_deleted=is_organizer)

    # Retrieve any active voting campaigns for this project's event
    active_campaign = (
        db.query(VotingCampaign)
        .filter(VotingCampaign.event_id == project.event_id, VotingCampaign.status.in_(["active", "closed"]))
        .first()
    )

    # Check if current voter has voted
    has_voted = False
    voter_key = request.cookies.get("voter_token")
    if active_campaign:
        query_voter = None
        if user:
            query_voter = f"auth:{user.id}"
        elif voter_key:
            if active_campaign.access_mode == "email":
                # Find verified email
                email_tok = db.query(EmailVoterToken).filter(EmailVoterToken.token == voter_key, EmailVoterToken.is_verified.is_(True)).first()
                if email_tok:
                    query_voter = f"email:{email_tok.email}"
            else:
                query_voter = f"open:{voter_key}"

        if query_voter:
            existing = (
                db.query(Vote)
                .filter(Vote.campaign_id == active_campaign.id, Vote.project_id == project_id, Vote.voter_key == query_voter)
                .first()
            )
            has_voted = existing is not None

    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={
            "request": request,
            "project": project,
            "user": user,
            "comments": comments,
            "active_campaign": active_campaign,
            "has_voted": has_voted,
            "is_organizer": is_organizer,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/projects/{project_id}/comments", response_class=HTMLResponse)
def public_project_add_comment_post(
    project_id: str,
    request: Request,
    body: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle comment submission from project detail page."""
    try:
        add_project_comment(
            db=db,
            project_id=project_id,
            body=body,
            user=user,
            ip_address=get_client_ip(request),
        )
        return RedirectResponse(
            url=f"/projects/{project_id}?success=Comment+posted+successfully!",
            status_code=status.HTTP_302_FOUND,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/projects/{project_id}?error={e.detail}",
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/projects/{project_id}/comments/{comment_id}/moderate", response_class=HTMLResponse)
def public_project_moderate_comment_post(
    project_id: str,
    comment_id: str,
    request: Request,
    user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Handle comment moderation/deletion from project detail page."""
    moderate_project_comment(
        db=db,
        project_id=project_id,
        comment_id=comment_id,
        user=user,
        ip_address=get_client_ip(request),
    )
    return RedirectResponse(
        url=f"/projects/{project_id}?success=Comment+moderated+successfully.",
        status_code=status.HTTP_302_FOUND,
    )
