"""Judging service implementing weighted rubrics, assignments, score submission, isolation, and CSV export."""

import csv
import hashlib
import hmac
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.audit.service import log_audit_event
from src.auth.models import User
from src.auth.service import hash_password, register_user
from src.config import get_settings
from src.events.models import Event
from src.judging.models import (
    JudgeAssignment,
    JudgeParticipationRecord,
    JudgeScore,
    Rubric,
    RubricCriterion,
)
from src.webhooks.service import emit_webhook
from src.judging.schemas import (
    AutoAssignResponse,
    EventResultsResponse,
    JudgeInviteResponse,
    JudgeProgressItem,
    JudgeQueueItemResponse,
    JudgingProgressResponse,
    ProjectCriterionScoreDetail,
    ProjectResultItem,
    ProjectScoreSubmissionRequest,
    RubricCreateRequest,
)
from src.submissions.models import Project


# ==============================================================================
# 1. RUBRICS & CRITERIA
# ==============================================================================

def get_or_create_default_rubric(db: Session, event_id: str) -> Rubric:
    """Retrieve event rubric or create standard default criteria if none exists."""
    rubric = db.query(Rubric).filter(Rubric.event_id == event_id).first()
    if not rubric:
        rubric = Rubric(
            event_id=event_id,
            name="Standard Hackathon Rubric",
            description="Evaluates technical execution, product design, innovation, and impact.",
        )
        db.add(rubric)
        db.flush()

        default_criteria = [
            RubricCriterion(
                rubric_id=rubric.id,
                name="Technical Execution",
                description="Code quality, architecture, completeness, and complexity.",
                weight=2.0,
                min_score=1.0,
                max_score=10.0,
                order_index=1,
            ),
            RubricCriterion(
                rubric_id=rubric.id,
                name="Impact & Innovation",
                description="Originality, problem significance, and value proposition.",
                weight=2.0,
                min_score=1.0,
                max_score=10.0,
                order_index=2,
            ),
            RubricCriterion(
                rubric_id=rubric.id,
                name="Design & Usability",
                description="UX/UI clarity, workflow smoothness, and polish.",
                weight=1.0,
                min_score=1.0,
                max_score=10.0,
                order_index=3,
            ),
        ]
        db.add_all(default_criteria)
        db.commit()
        db.refresh(rubric)

    return rubric


def create_or_update_rubric(
    db: Session,
    event_id: str,
    req: RubricCreateRequest,
    user_id: str,
) -> Rubric:
    """Create or replace an event's rubric and criteria."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    rubric = db.query(Rubric).filter(Rubric.event_id == event_id).first()
    if rubric:
        rubric.name = req.name
        rubric.description = req.description
        # Clear existing criteria and recreate
        db.query(RubricCriterion).filter(RubricCriterion.rubric_id == rubric.id).delete()
    else:
        rubric = Rubric(
            event_id=event_id,
            name=req.name,
            description=req.description,
        )
        db.add(rubric)
        db.flush()

    for idx, c in enumerate(req.criteria):
        criterion = RubricCriterion(
            rubric_id=rubric.id,
            name=c.name,
            description=c.description,
            weight=c.weight,
            min_score=c.min_score,
            max_score=c.max_score,
            order_index=c.order_index if c.order_index else idx,
        )
        db.add(criterion)

    db.commit()
    db.refresh(rubric)

    log_audit_event(
        db=db,
        event_type="rubric_configured",
        entity_type="rubric",
        entity_id=rubric.id,
        user_id=user_id,
        payload={"event_id": event_id, "criteria_count": len(req.criteria)},
    )
    return rubric


# ==============================================================================
# 2. JUDGE INVITATION & ASSIGNMENT
# ==============================================================================

def invite_or_register_judge(
    db: Session,
    event_id: str,
    email: str,
    username: Optional[str],
    inviter_id: str,
) -> JudgeInviteResponse:
    """Invite or designate a user as a judge for the hackathon."""
    clean_email = email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user:
        uname = username.strip().lower() if username else clean_email.split("@")[0]
        # ensure unique username
        existing_uname = db.query(User).filter(User.username == uname).first()
        if existing_uname:
            uname = f"{uname}_{int(datetime.now(timezone.utc).timestamp()) % 10000}"

        user = User(
            username=uname,
            email=clean_email,
            hashed_password=hash_password("judge_initial_pass_2026"),
            role="judge",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        msg = "Judge user created and registered."
    else:
        if user.role != "admin":
            user.role = "judge"
            db.commit()
        msg = f"User '{user.username}' updated with judge role."

    log_audit_event(
        db=db,
        event_type="judge_invited",
        entity_type="user",
        entity_id=user.id,
        user_id=inviter_id,
        payload={"event_id": event_id, "judge_email": clean_email},
    )

    return JudgeInviteResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        message=msg,
    )


def create_assignment(
    db: Session,
    event_id: str,
    judge_id: str,
    project_id: str,
    assigner_id: str,
) -> JudgeAssignment:
    """Assign a judge to evaluate a specific submitted project."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    judge = db.query(User).filter(User.id == judge_id).first()
    if not judge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge user not found.")
    if judge.role not in ["judge", "admin", "organizer"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user does not have judge role.")

    project = db.query(Project).filter(Project.id == project_id, Project.event_id == event_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found in this event.")
    if not project.is_submitted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign unsubmitted draft project to judging.")

    existing = db.query(JudgeAssignment).filter(
        JudgeAssignment.judge_id == judge_id,
        JudgeAssignment.project_id == project_id,
    ).first()
    if existing:
        return existing

    assignment = JudgeAssignment(
        event_id=event_id,
        judge_id=judge_id,
        project_id=project_id,
        status="assigned",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    log_audit_event(
        db=db,
        event_type="judge_assigned",
        entity_type="judge_assignment",
        entity_id=assignment.id,
        user_id=assigner_id,
        payload={"judge_id": judge_id, "project_id": project_id, "event_id": event_id},
    )

    emit_webhook(
        db=db,
        event_type="judge.assigned",
        event_id=event_id,
        resource_id=assignment.id,
        resource_data={"judge_id": judge_id, "project_id": project_id, "assignment_id": assignment.id},
    )

    return assignment



def auto_assign_projects(
    db: Session,
    event_id: str,
    judges_per_project: int,
    assigner_id: str,
) -> AutoAssignResponse:
    """Evenly distribute all submitted projects across all available judges."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    projects = db.query(Project).filter(
        Project.event_id == event_id,
        Project.is_submitted.is_(True),
    ).all()
    if not projects:
        return AutoAssignResponse(event_id=event_id, total_assigned=0, judges_count=0, projects_count=0)

    # Find judges: all users with role 'judge' or who already have assignments
    judges = db.query(User).filter(User.role == "judge", User.is_active.is_(True)).all()
    if not judges:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active judges found in system.")

    total_assigned = 0
    num_judges = len(judges)

    for p_idx, project in enumerate(projects):
        for k in range(min(judges_per_project, num_judges)):
            judge = judges[(p_idx + k) % num_judges]
            existing = db.query(JudgeAssignment).filter(
                JudgeAssignment.judge_id == judge.id,
                JudgeAssignment.project_id == project.id,
            ).first()
            if not existing:
                assignment = JudgeAssignment(
                    event_id=event_id,
                    judge_id=judge.id,
                    project_id=project.id,
                    status="assigned",
                )
                db.add(assignment)
                total_assigned += 1

    db.commit()

    log_audit_event(
        db=db,
        event_type="auto_assign_executed",
        entity_type="event",
        entity_id=event_id,
        user_id=assigner_id,
        payload={"total_assigned": total_assigned, "judges_per_project": judges_per_project},
    )

    return AutoAssignResponse(
        event_id=event_id,
        total_assigned=total_assigned,
        judges_count=num_judges,
        projects_count=len(projects),
    )


# ==============================================================================
# 3. JUDGE QUEUE & PROJECT ACCESS (CRITICAL SECURITY)
# ==============================================================================

def get_judge_queue(
    db: Session,
    judge_id: str,
    event_id: Optional[str] = None,
) -> List[JudgeQueueItemResponse]:
    """Retrieve queue of projects assigned to a specific judge."""
    query = db.query(JudgeAssignment).filter(JudgeAssignment.judge_id == judge_id)
    if event_id:
        query = query.filter(JudgeAssignment.event_id == event_id)

    assignments = query.all()
    results: List[JudgeQueueItemResponse] = []

    for assign in assignments:
        project = assign.project
        event = assign.event
        rubric = get_or_create_default_rubric(db, event.id)
        total_criteria = len(rubric.criteria)

        scored_count = db.query(JudgeScore).filter(
            JudgeScore.judge_id == judge_id,
            JudgeScore.project_id == project.id,
            JudgeScore.score.isnot(None),
        ).count()

        results.append(
            JudgeQueueItemResponse(
                assignment_id=assign.id,
                project_id=project.id,
                project_title=project.title,
                project_tagline=project.tagline,
                track_title=project.track.title if project.track else "General",
                team_name=project.team.name if project.team else "Solo",
                status=assign.status,
                demo_url=project.demo_url,
                repository_url=project.repository_url,
                scored_criteria_count=scored_count,
                total_criteria_count=total_criteria,
            )
        )

    return results


def verify_judge_project_access(
    db: Session,
    project_id: str,
    user: User,
) -> Tuple[Project, Rubric, Optional[JudgeAssignment]]:
    """
    CRITICAL SECURITY CHECK:
    A judge can ONLY access projects assigned to that judge.
    If the project is not assigned to the judge, raises HTTP 403 Forbidden.
    Organizers and Admins have oversight and can inspect any project.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    rubric = get_or_create_default_rubric(db, project.event_id)

    # Organizers and Admins bypass assignment check
    if user.role in ["organizer", "admin"]:
        assignment = db.query(JudgeAssignment).filter(
            JudgeAssignment.project_id == project_id,
            JudgeAssignment.judge_id == user.id,
        ).first()
        return project, rubric, assignment

    # For Judge role: strict assignment verification
    assignment = db.query(JudgeAssignment).filter(
        JudgeAssignment.project_id == project_id,
        JudgeAssignment.judge_id == user.id,
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not assigned to evaluate this project.",
        )

    return project, rubric, assignment


# ==============================================================================
# 4. SCORE SUBMISSION & STRICT ISOLATION (CRITICAL SECURITY)
# ==============================================================================

def submit_project_scores(
    db: Session,
    project_id: str,
    judge_user: User,
    req: ProjectScoreSubmissionRequest,
    ip_address: Optional[str] = None,
) -> List[JudgeScore]:
    """
    Submit or update scores for a project.
    CRITICAL SECURITY:
    Judge must be assigned to the project.
    Scores are strictly recorded under judge_user.id.
    """
    project, rubric, assignment = verify_judge_project_access(db, project_id, judge_user)

    criteria_map = {c.id: c for c in rubric.criteria}
    saved_scores: List[JudgeScore] = []

    for score_in in req.scores:
        criterion = criteria_map.get(score_in.criterion_id)
        if not criterion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Criterion '{score_in.criterion_id}' is not part of this event's rubric.",
            )

        if score_in.score is not None:
            if score_in.score < criterion.min_score or score_in.score > criterion.max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Score {score_in.score} for '{criterion.name}' out of bounds [{criterion.min_score}, {criterion.max_score}].",
                )

        existing_score = db.query(JudgeScore).filter(
            JudgeScore.judge_id == judge_user.id,
            JudgeScore.project_id == project_id,
            JudgeScore.criterion_id == score_in.criterion_id,
        ).first()

        feedback_val = score_in.feedback or req.general_feedback

        if existing_score:
            existing_score.score = score_in.score
            if feedback_val:
                existing_score.feedback = feedback_val
            existing_score.updated_at = datetime.now(timezone.utc)
            saved_scores.append(existing_score)
        else:
            new_score = JudgeScore(
                assignment_id=assignment.id if assignment else None,
                judge_id=judge_user.id,
                project_id=project_id,
                criterion_id=score_in.criterion_id,
                score=score_in.score,
                feedback=feedback_val,
            )
            db.add(new_score)
            saved_scores.append(new_score)

    if assignment:
        assignment.status = "completed"

    db.commit()

    log_audit_event(
        db=db,
        event_type="scores_submitted",
        entity_type="project",
        entity_id=project_id,
        user_id=judge_user.id,
        payload={"scores_count": len(saved_scores), "assignment_id": assignment.id if assignment else None},
        ip_address=ip_address,
    )

    emit_webhook(
        db=db,
        event_type="score.submitted",
        event_id=project.event_id,
        resource_id=project_id,
        resource_data={
            "project_id": project_id,
            "judge_id": judge_user.id,
            "scores_count": len(saved_scores),
        },
    )

    return saved_scores



def get_project_scores_for_user(
    db: Session,
    project_id: str,
    current_user: User,
    requested_judge_id: Optional[str] = None,
) -> List[JudgeScore]:
    """
    CRITICAL SECURITY ENFORCEMENT:
    - A judge may read ONLY their own score records.
    - A judge must never retrieve another judge's scores,
      even when the other judge ID is manually supplied to the API.
    - If a judge manually requests another judge ID, raise HTTP 403 Forbidden.
    - Organizers and admins may access all score records or filter by judge.
    - Participants must NOT access scores (HTTP 403 Forbidden).
    """
    if current_user.role == "participant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Participants are not permitted to access judge score records.",
        )

    query = db.query(JudgeScore).filter(JudgeScore.project_id == project_id)

    if current_user.role == "judge":
        # Check if judge manually supplied another judge ID to tamper or leak
        if requested_judge_id and requested_judge_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Judges are strictly prohibited from viewing other judges' scores.",
            )
        # Strictly enforce judge's own ID regardless of inputs
        query = query.filter(JudgeScore.judge_id == current_user.id)
    else:
        # Organizer / Admin can view all or filter by requested judge
        if requested_judge_id:
            query = query.filter(JudgeScore.judge_id == requested_judge_id)

    return query.all()


def get_score_by_id(
    db: Session,
    score_id: str,
    current_user: User,
) -> JudgeScore:
    """
    CRITICAL SECURITY ENFORCEMENT:
    - A judge reading a single score by ID must only access their own score.
    - If score belongs to another judge, raise HTTP 403 Forbidden.
    - Participants cannot access (403).
    """
    if current_user.role == "participant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Participants are not permitted to access judge score records.",
        )

    score = db.query(JudgeScore).filter(JudgeScore.id == score_id).first()
    if not score:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score record not found.")

    if current_user.role == "judge" and score.judge_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only read your own score records.",
        )

    return score


# ==============================================================================
# 5. JUDGING PROGRESS & ORGANIZER RESULTS
# ==============================================================================

def get_judging_progress(db: Session, event_id: str) -> JudgingProgressResponse:
    """Calculate judging completion metrics across the event and per judge."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    assignments = db.query(JudgeAssignment).filter(JudgeAssignment.event_id == event_id).all()
    total = len(assignments)
    completed = sum(1 for a in assignments if a.status == "completed")
    in_progress = sum(1 for a in assignments if a.status == "in_progress")
    pending = sum(1 for a in assignments if a.status == "assigned")
    pct = (completed / total * 100.0) if total > 0 else 0.0

    # Group by judge
    judge_map: Dict[str, Dict[str, Any]] = {}
    for a in assignments:
        jid = a.judge_id
        if jid not in judge_map:
            judge_map[jid] = {
                "judge_id": jid,
                "username": a.judge.username if a.judge else jid,
                "total": 0,
                "completed": 0,
                "in_progress": 0,
            }
        judge_map[jid]["total"] += 1
        if a.status == "completed":
            judge_map[jid]["completed"] += 1
        elif a.status == "in_progress":
            judge_map[jid]["in_progress"] += 1

    breakdown = [
        JudgeProgressItem(
            judge_id=v["judge_id"],
            username=v["username"],
            total_assigned=v["total"],
            completed=v["completed"],
            in_progress=v["in_progress"],
            completion_rate=(v["completed"] / v["total"] * 100.0) if v["total"] > 0 else 0.0,
        )
        for v in judge_map.values()
    ]

    return JudgingProgressResponse(
        event_id=event_id,
        total_assignments=total,
        completed_assignments=completed,
        in_progress_assignments=in_progress,
        pending_assignments=pending,
        completion_percentage=round(pct, 1),
        judge_breakdown=breakdown,
    )


def calculate_event_results(db: Session, event_id: str) -> EventResultsResponse:
    """
    Calculate aggregate weighted scores and rankings for an event.
    Only organizers and admins can access this data.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    rubric = get_or_create_default_rubric(db, event_id)
    criteria = rubric.criteria

    projects = db.query(Project).filter(
        Project.event_id == event_id,
        Project.is_submitted.is_(True),
    ).all()

    project_results: List[Dict[str, Any]] = []

    for project in projects:
        # Collect all valid scores for this project
        scores = db.query(JudgeScore).filter(
            JudgeScore.project_id == project.id,
            JudgeScore.score.isnot(None),
        ).all()

        distinct_judges = len(set(s.judge_id for s in scores))

        crit_scores_map: Dict[str, List[float]] = {c.id: [] for c in criteria}
        for s in scores:
            if s.criterion_id in crit_scores_map:
                crit_scores_map[s.criterion_id].append(float(s.score))

        crit_details: List[ProjectCriterionScoreDetail] = []
        weighted_sum = 0.0
        total_weight = 0.0

        for c in criteria:
            c_scores = crit_scores_map[c.id]
            avg_score = (sum(c_scores) / len(c_scores)) if c_scores else None
            crit_details.append(
                ProjectCriterionScoreDetail(
                    criterion_id=c.id,
                    criterion_name=c.name,
                    weight=c.weight,
                    average_score=round(avg_score, 2) if avg_score is not None else None,
                )
            )
            if avg_score is not None:
                weighted_sum += avg_score * c.weight
                total_weight += c.weight

        final_score = (weighted_sum / total_weight) if total_weight > 0 else 0.0

        project_results.append({
            "project_id": project.id,
            "project_title": project.title,
            "team_name": project.team.name if project.team else "Solo",
            "track_title": project.track.title if project.track else "General",
            "weighted_score": round(final_score, 2),
            "evaluations_count": distinct_judges,
            "criteria_scores": crit_details,
        })

    # Sort descending by weighted score
    project_results.sort(key=lambda x: (x["weighted_score"], x["evaluations_count"]), reverse=True)

    ranked_items: List[ProjectResultItem] = []
    for rank, p in enumerate(project_results, start=1):
        ranked_items.append(
            ProjectResultItem(
                rank=rank,
                project_id=p["project_id"],
                project_title=p["project_title"],
                team_name=p["team_name"],
                track_title=p["track_title"],
                weighted_score=p["weighted_score"],
                evaluations_count=p["evaluations_count"],
                criteria_scores=p["criteria_scores"],
            )
        )

    return EventResultsResponse(
        event_id=event_id,
        event_title=event.title,
        total_projects=len(projects),
        results=ranked_items,
    )


def generate_results_csv(db: Session, event_id: str) -> str:
    """Generate RFC 4180 compliant CSV export for event judging results."""
    event_results = calculate_event_results(db, event_id)
    rubric = get_or_create_default_rubric(db, event_id)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    header = ["Rank", "Project Title", "Team Name", "Track", "Final Weighted Score", "Total Evaluations"]
    for c in rubric.criteria:
        header.append(f"{c.name} (w={c.weight})")
    writer.writerow(header)

    # Rows
    for item in event_results.results:
        crit_map = {cs.criterion_id: cs.average_score for cs in item.criteria_scores}
        row = [
            item.rank,
            item.project_title,
            item.team_name,
            item.track_title or "General",
            f"{item.weighted_score:.2f}",
            item.evaluations_count,
        ]
        for c in rubric.criteria:
            val = crit_map.get(c.id)
            row.append(f"{val:.2f}" if val is not None else "N/A")
        writer.writerow(row)

    return output.getvalue()


# ==============================================================================
# 7. SIGNED JUDGE PARTICIPATION RECORDS
# ==============================================================================

def generate_judge_participation_record(
    db: Session,
    event_id: str,
    judge_id: str,
) -> JudgeParticipationRecord:
    """Generate and cryptographically sign a participation record for a judge upon completing evaluations."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    judge = db.query(User).filter(User.id == judge_id).first()
    if not judge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge not found.")

    assignments = db.query(JudgeAssignment).filter(
        JudgeAssignment.event_id == event_id,
        JudgeAssignment.judge_id == judge_id,
    ).all()

    total_assigned = len(assignments)
    if total_assigned == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Judge has no assigned projects for this event.",
        )

    completed_assignments = [a for a in assignments if a.status == "completed"]
    total_evaluated = len(completed_assignments)

    if total_evaluated < total_assigned:
        pending = total_assigned - total_evaluated
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Judge has pending evaluations ({pending} remaining). Record can only be issued upon 100% completion.",
        )

    settings = get_settings()
    now_utc = datetime.now(timezone.utc)

    # Canonical dictionary format with sorted keys and compact serialization
    canonical_data = {
        "event_id": event.id,
        "event_title": event.title,
        "issued_at": now_utc.isoformat(),
        "judge_email": judge.email,
        "judge_id": judge.id,
        "judge_name": judge.username,
        "total_assigned": total_assigned,
        "total_evaluated": total_evaluated,
    }
    canonical_payload = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        canonical_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    record = db.query(JudgeParticipationRecord).filter(
        JudgeParticipationRecord.event_id == event_id,
        JudgeParticipationRecord.judge_id == judge_id,
    ).first()

    if not record:
        record = JudgeParticipationRecord(
            event_id=event.id,
            judge_id=judge.id,
            judge_name=judge.username,
            judge_email=judge.email,
            total_assigned=total_assigned,
            total_evaluated=total_evaluated,
            canonical_payload=canonical_payload,
            signature=signature,
            issued_at=now_utc,
        )
        db.add(record)
    else:
        record.judge_name = judge.username
        record.judge_email = judge.email
        record.total_assigned = total_assigned
        record.total_evaluated = total_evaluated
        record.canonical_payload = canonical_payload
        record.signature = signature
        record.issued_at = now_utc

    db.commit()
    db.refresh(record)

    log_audit_event(
        db=db,
        event_type="JUDGE_RECORD_ISSUED",
        entity_type="JudgeParticipationRecord",
        entity_id=record.id,
        user_id=judge.id,
        payload={
            "judge_id": judge.id,
            "event_id": event.id,
            "total_evaluated": total_evaluated,
            "signature": signature,
        },
    )

    emit_webhook(
        db=db,
        event_type="judge.record_issued",
        event_id=event.id,
        resource_id=record.id,
        resource_data={
            "record_id": record.id,
            "judge_id": judge.id,
            "judge_name": judge.username,
            "total_evaluated": total_evaluated,
            "signature": signature,
        },
    )

    return record


def get_judge_participation_record(db: Session, record_id: str) -> JudgeParticipationRecord:
    """Retrieve judge participation record by ID."""
    record = db.query(JudgeParticipationRecord).filter(JudgeParticipationRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge record not found.")
    return record


def verify_judge_participation_record(db: Session, record_id: str) -> Dict[str, Any]:
    """Cryptographically verify the authenticity and signature of a judge record."""
    record = db.query(JudgeParticipationRecord).filter(JudgeParticipationRecord.id == record_id).first()
    if not record:
        return {
            "valid": False,
            "record_id": record_id,
            "detail": "Record not found.",
        }

    settings = get_settings()
    expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        record.canonical_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    is_valid = hmac.compare_digest(record.signature, expected_sig)

    return {
        "valid": is_valid,
        "record_id": record.id,
        "event_id": record.event_id,
        "judge_name": record.judge_name,
        "total_evaluated": record.total_evaluated,
        "issued_at": record.issued_at,
        "signature": record.signature,
        "detail": "Participation record is authentic and verified." if is_valid else "Cryptographic signature mismatch - record has been tampered with.",
    }

