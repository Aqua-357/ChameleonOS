"""Judging API endpoints and HTML views with strict security authorization boundaries."""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_optional_user, require_role
from src.auth.models import User
from src.database import get_db
from src.events.models import Event
from src.judging.models import JudgeScore
from src.judging.schemas import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AutoAssignRequest,
    AutoAssignResponse,
    CriterionScoreInput,
    EventResultsResponse,
    JudgeInviteRequest,
    JudgeInviteResponse,
    JudgeQueueItemResponse,
    JudgeRecordResponse,
    JudgeRecordVerifyResponse,
    JudgeScoreResponse,
    JudgingProgressResponse,
    ProjectScoreSubmissionRequest,
    RubricCreateRequest,
    RubricResponse,
)
from src.judging.service import (
    auto_assign_projects,
    calculate_event_results,
    create_assignment,
    create_or_update_rubric,
    generate_judge_participation_record,
    generate_results_csv,
    get_judge_participation_record,
    get_judging_progress,
    get_or_create_default_rubric,
    get_judge_queue,
    get_project_scores_for_user,
    get_score_by_id,
    invite_or_register_judge,
    submit_project_scores,
    verify_judge_participation_record,
    verify_judge_project_access,
)
from src.submissions.models import Project


router = APIRouter(tags=["judging"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ==============================================================================
# 1. RUBRICS (ORGANIZER / ADMIN)
# ==============================================================================

@router.post("/api/v1/judging/events/{event_id}/rubric", response_model=RubricResponse)
def api_configure_rubric(
    event_id: str,
    req: RubricCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Create or update judging rubric for an event."""
    return create_or_update_rubric(db, event_id, req, user_id=current_user.id)


@router.get("/api/v1/judging/events/{event_id}/rubric", response_model=RubricResponse)
def api_get_rubric(
    event_id: str,
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Retrieve event judging rubric."""
    return get_or_create_default_rubric(db, event_id)


# ==============================================================================
# 2. JUDGE INVITATIONS & ASSIGNMENTS (ORGANIZER / ADMIN)
# ==============================================================================

@router.post("/api/v1/judging/invites", response_model=JudgeInviteResponse)
def api_invite_judge(
    req: JudgeInviteRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Invite or register an authorized judge for the event."""
    return invite_or_register_judge(
        db=db,
        event_id=req.event_id,
        email=req.email,
        username=req.username,
        inviter_id=current_user.id,
    )


@router.post("/api/v1/judging/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def api_create_assignment(
    req: AssignmentCreateRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Assign a judge to evaluate a specific submitted project."""
    return create_assignment(
        db=db,
        event_id=req.event_id,
        judge_id=req.judge_id,
        project_id=req.project_id,
        assigner_id=current_user.id,
    )


@router.post("/api/v1/judging/events/{event_id}/auto-assign", response_model=AutoAssignResponse)
def api_auto_assign(
    event_id: str,
    req: AutoAssignRequest,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Evenly auto-distribute submitted projects across judges."""
    return auto_assign_projects(
        db=db,
        event_id=event_id,
        judges_per_project=req.judges_per_project,
        assigner_id=current_user.id,
    )


# ==============================================================================
# 3. JUDGE QUEUE & PROJECT EVALUATION (CRITICAL SECURITY)
# ==============================================================================

@router.get("/api/v1/judging/queue", response_model=List[JudgeQueueItemResponse])
def api_judge_queue(
    event_id: Optional[str] = Query(None),
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Retrieve project queue for the calling judge.
    Participants cannot access this endpoint (403).
    """
    return get_judge_queue(db, judge_id=current_user.id, event_id=event_id)


@router.get("/api/v1/judging/projects/{project_id}")
def api_judge_project_detail(
    project_id: str,
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Retrieve project details and rubric for scoring.
    CRITICAL SECURITY:
    A judge can ONLY access projects assigned to that judge.
    If not assigned, returns HTTP 403 Forbidden.
    """
    project, rubric, assignment = verify_judge_project_access(db, project_id, current_user)
    my_scores = db.query(JudgeScore).filter(
        JudgeScore.project_id == project_id,
        JudgeScore.judge_id == current_user.id,
    ).all()

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "tagline": project.tagline,
            "description": project.description,
            "demo_url": project.demo_url,
            "repository_url": project.repository_url,
            "video_url": project.video_url,
            "team_name": project.team.name if project.team else "Solo",
            "track_title": project.track.title if project.track else "General",
        },
        "rubric": RubricResponse.model_validate(rubric),
        "assignment_status": assignment.status if assignment else "admin_view",
        "existing_scores": [JudgeScoreResponse.model_validate(s) for s in my_scores],
    }


@router.post("/api/v1/judging/projects/{project_id}/scores", response_model=List[JudgeScoreResponse])
def api_submit_scores(
    project_id: str,
    req: ProjectScoreSubmissionRequest,
    request: Request,
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Submit criterion scores and feedback for an assigned project.
    CRITICAL SECURITY:
    Judge must be assigned to project.
    Scores strictly recorded under calling user's ID.
    """
    ip_addr = request.client.host if request.client else None
    scores = submit_project_scores(db, project_id, current_user, req, ip_address=ip_addr)
    return scores


# ==============================================================================
# 4. SCORE RETRIEVAL & ISOLATION (CRITICAL SECURITY)
# ==============================================================================

@router.get("/api/v1/judging/projects/{project_id}/scores", response_model=List[JudgeScoreResponse])
def api_get_project_scores(
    project_id: str,
    judge_id: Optional[str] = Query(None),
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    CRITICAL SECURITY ENFORCEMENT:
    - A judge may read ONLY their own score records.
    - A judge must never retrieve another judge's scores,
      even when the other judge ID is manually supplied to the API.
    - If a judge manually requests another judge ID, HTTP 403 Forbidden is returned.
    - Participants cannot access this endpoint (403).
    - Organizers and admins can view all scores.
    """
    return get_project_scores_for_user(db, project_id, current_user, requested_judge_id=judge_id)


@router.get("/api/v1/judging/scores/{score_id}", response_model=JudgeScoreResponse)
def api_get_score_by_id(
    score_id: str,
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    CRITICAL SECURITY ENFORCEMENT:
    - A judge reading a single score by ID must only access their own score.
    - If the score belongs to another judge, returns HTTP 403 Forbidden.
    """
    return get_score_by_id(db, score_id, current_user)


# ==============================================================================
# 5. JUDGING PROGRESS & ORGANIZER RESULTS (ORGANIZER / ADMIN ONLY)
# ==============================================================================

@router.get("/api/v1/judging/events/{event_id}/progress", response_model=JudgingProgressResponse)
def api_get_progress(
    event_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Retrieve overall judging progress metrics.
    Restricted strictly to organizers and admins. Judges and participants receive 403.
    """
    return get_judging_progress(db, event_id)


@router.get("/api/v1/judging/events/{event_id}/results", response_model=EventResultsResponse)
def api_get_results(
    event_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Retrieve aggregate weighted scores and rankings.
    Restricted strictly to organizers and admins. Judges and participants receive 403.
    """
    return calculate_event_results(db, event_id)


@router.get("/api/v1/judging/events/{event_id}/export.csv")
def api_export_results_csv(
    event_id: str,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Export event judging results in CSV format.
    Restricted strictly to organizers and admins. Judges and participants receive 403.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    csv_data = generate_results_csv(db, event_id)
    filename = f"results_{event.slug}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# 6. HTML VIEWS - DASHBOARD, EVALUATION, AND RESULTS
# ==============================================================================

@router.get("/judging", response_class=HTMLResponse)
def html_judge_dashboard(
    request: Request,
    event_id: Optional[str] = Query(None),
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Judge Dashboard displaying assigned projects queue and progress stats."""
    queue = get_judge_queue(db, judge_id=current_user.id, event_id=event_id)
    events = db.query(Event).all()
    total_assigned = len(queue)
    completed_count = sum(1 for q in queue if q.status == "completed")
    pct = round((completed_count / total_assigned * 100.0) if total_assigned > 0 else 0.0, 1)

    return templates.TemplateResponse(
        request=request,
        name="judge_dashboard.html",
        context={
            "request": request,
            "user": current_user,
            "queue": queue,
            "events": events,
            "active_event_id": event_id,
            "total_assigned": total_assigned,
            "completed_count": completed_count,
            "completion_percentage": pct,
        },
    )


@router.get("/judging/projects/{project_id}", response_class=HTMLResponse)
def html_judge_evaluate(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Dedicated project scoring interface with weighted rubric criteria."""
    project, rubric, assignment = verify_judge_project_access(db, project_id, current_user)
    my_scores = db.query(JudgeScore).filter(
        JudgeScore.project_id == project_id,
        JudgeScore.judge_id == current_user.id,
    ).all()
    score_map = {s.criterion_id: s for s in my_scores}

    general_feedback = None
    for s in my_scores:
        if s.feedback:
            general_feedback = s.feedback
            break

    return templates.TemplateResponse(
        request=request,
        name="judge_evaluate.html",
        context={
            "request": request,
            "user": current_user,
            "project": project,
            "rubric": rubric,
            "assignment": assignment,
            "score_map": score_map,
            "general_feedback": general_feedback,
            "error": None,
            "success": None,
        },
    )


@router.post("/judging/projects/{project_id}", response_class=HTMLResponse)
async def html_judge_submit_scores(
    project_id: str,
    request: Request,
    general_feedback: Optional[str] = Form(None),
    current_user: User = Depends(require_role("judge", "organizer", "admin")),
    db: Session = Depends(get_db),
):
    """Process evaluation form submission."""
    form_data = await request.form()
    project, rubric, assignment = verify_judge_project_access(db, project_id, current_user)

    score_inputs: List[CriterionScoreInput] = []
    for criterion in rubric.criteria:
        field_name = f"criterion_{criterion.id}"
        val = form_data.get(field_name)
        if val is not None and str(val).strip():
            try:
                numeric_val = float(str(val).strip())
                score_inputs.append(CriterionScoreInput(criterion_id=criterion.id, score=numeric_val))
            except ValueError:
                pass

    req = ProjectScoreSubmissionRequest(scores=score_inputs, general_feedback=general_feedback)
    try:
        ip_addr = request.client.host if request.client else None
        submit_project_scores(db, project_id, current_user, req, ip_address=ip_addr)
        return RedirectResponse(url="/judging", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        my_scores = db.query(JudgeScore).filter(
            JudgeScore.project_id == project_id,
            JudgeScore.judge_id == current_user.id,
        ).all()
        score_map = {s.criterion_id: s for s in my_scores}
        return templates.TemplateResponse(
            request=request,
            name="judge_evaluate.html",
            context={
                "request": request,
                "user": current_user,
                "project": project,
                "rubric": rubric,
                "assignment": assignment,
                "score_map": score_map,
                "general_feedback": general_feedback,
                "error": e.detail,
                "success": None,
            },
            status_code=e.status_code,
        )


@router.get("/events/{slug}/results", response_class=HTMLResponse)
def html_event_results(
    slug: str,
    request: Request,
    current_user: User = Depends(require_role("organizer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Organizer Results & Leaderboard Page.
    Restricted strictly to organizers and admins.
    """
    event = db.query(Event).filter(Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    results_data = calculate_event_results(db, event.id)
    progress_data = get_judging_progress(db, event.id)
    rubric = get_or_create_default_rubric(db, event.id)

    return templates.TemplateResponse(
        request=request,
        name="event_results.html",
        context={
            "request": request,
            "user": current_user,
            "event": event,
            "rubric": rubric,
            "results": results_data.results,
            "progress": progress_data,
        },
    )


# ==============================================================================
# 5. SIGNED JUDGE PARTICIPATION RECORDS (T4.4)
# ==============================================================================

@router.post("/api/v1/judging/events/{event_id}/judges/{judge_id}/record", response_model=JudgeRecordResponse, status_code=status.HTTP_201_CREATED)
def api_issue_judge_record(
    event_id: str,
    judge_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate and cryptographically sign a participation record (organizer, admin, or the judge themself)."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    is_organizer = current_user.role in ["organizer", "admin"] or event.organizer_id == current_user.id
    is_self = current_user.id == judge_id

    if not (is_organizer or is_self):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized to issue judge record.")

    record = generate_judge_participation_record(db, event_id, judge_id)
    return JudgeRecordResponse(
        id=record.id,
        event_id=record.event_id,
        judge_id=record.judge_id,
        judge_name=record.judge_name,
        judge_email=record.judge_email,
        total_assigned=record.total_assigned,
        total_evaluated=record.total_evaluated,
        canonical_payload=record.canonical_payload,
        signature=record.signature,
        issued_at=record.issued_at,
        verification_url=f"/verify/judge/{record.id}",
    )


@router.get("/api/v1/judging/records/{record_id}", response_model=JudgeRecordResponse)
def api_get_judge_record(
    record_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve judge participation record details."""
    record = get_judge_participation_record(db, record_id)
    return JudgeRecordResponse(
        id=record.id,
        event_id=record.event_id,
        judge_id=record.judge_id,
        judge_name=record.judge_name,
        judge_email=record.judge_email,
        total_assigned=record.total_assigned,
        total_evaluated=record.total_evaluated,
        canonical_payload=record.canonical_payload,
        signature=record.signature,
        issued_at=record.issued_at,
        verification_url=f"/verify/judge/{record.id}",
    )


@router.get("/api/v1/judging/records/verify/{record_id}", response_model=JudgeRecordVerifyResponse)
@router.get("/api/v1/judging/records/{record_id}/verify", response_model=JudgeRecordVerifyResponse)
def api_verify_judge_record(
    record_id: str,
    db: Session = Depends(get_db),
):
    """Cryptographically verify judge participation record."""
    res = verify_judge_participation_record(db, record_id)
    return JudgeRecordVerifyResponse(**res)


@router.get("/verify/judge/{record_id}", response_class=HTMLResponse)
def html_verify_judge_record(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """Public verification page for signed judge participation record."""
    from src.config import get_settings
    settings = get_settings()

    res = verify_judge_participation_record(db, record_id)
    event = None
    if res.get("valid") and res.get("event_id"):
        event = db.query(Event).filter(Event.id == res["event_id"]).first()

    return templates.TemplateResponse(
        request=request,
        name="judge_record_verify.html",
        context={
            "request": request,
            "settings": settings,
            "user": user,
            "result": res,
            "record_id": record_id,
            "event": event,
        },
    )

