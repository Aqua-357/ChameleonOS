"""Data exchange service: Bulk import and export for hackathon data."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.audit.models import AuditEvent
from src.audit.service import log_audit_event
from src.auth.models import User
from src.certificates.models import Certificate
from src.events.models import Event, Track, Prize
from src.judging.models import (
    JudgeAssignment,
    JudgeParticipationRecord,
    JudgeScore,
    Rubric,
    RubricCriterion,
)
from src.submissions.models import Project, Team, TeamMember
from src.voting.models import ProjectComment, Vote, VotingCampaign
from src.webhooks.service import emit_webhook


def parse_projects_csv(content: str) -> List[Dict[str, Any]]:
    """Parse a CSV string into project item dictionaries."""
    reader = csv.DictReader(io.StringIO(content.strip()))
    items = []
    for row in reader:
        # Strip keys and values
        clean_row = {k.strip(): v.strip() for k, v in row.items() if k is not None}
        items.append(clean_row)
    return items


def validate_and_import_projects(
    db: Session,
    event_id: str,
    items: List[Dict[str, Any]],
    creator_user: User,
) -> Tuple[int, List[str]]:
    """
    Validate all project rows first.
    If ANY row fails validation, return early with row-specific errors and rollback.
    If ALL rows pass, import atomically in a single transaction.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if not items:
        return 0, ["Import payload is empty."]

    errors: List[str] = []
    validated_rows: List[Dict[str, Any]] = []

    # Map of existing tracks for the event
    tracks = {t.title.lower(): t for t in db.query(Track).filter(Track.event_id == event_id).all()}

    for index, row in enumerate(items, start=1):
        title = row.get("title") or row.get("project_title")
        team_name = row.get("team_name") or row.get("team")
        track_name = row.get("track") or row.get("track_name")
        tagline = row.get("tagline")
        description = row.get("description")
        demo_url = row.get("demo_url")
        repository_url = row.get("repository_url")

        if not title or len(title.strip()) < 2:
            errors.append(f"Row {index}: Missing or invalid project 'title' (minimum 2 characters required).")
        if not team_name or len(team_name.strip()) < 2:
            errors.append(f"Row {index}: Missing or invalid 'team_name' (minimum 2 characters required).")

        validated_rows.append({
            "title": title.strip() if title else "",
            "team_name": team_name.strip() if team_name else "",
            "track_name": track_name.strip() if track_name else None,
            "tagline": tagline.strip() if tagline else None,
            "description": description.strip() if description else "Imported project.",
            "demo_url": demo_url.strip() if demo_url else None,
            "repository_url": repository_url.strip() if repository_url else None,
        })

    if errors:
        return 0, errors

    # Atomic transactional import
    imported_count = 0
    try:
        now_utc = datetime.now(timezone.utc)
        teams_cache: Dict[str, Team] = {
            t.name.lower(): t for t in db.query(Team).filter(Team.event_id == event_id).all()
        }

        for row_data in validated_rows:
            team_key = row_data["team_name"].lower()
            team = teams_cache.get(team_key)
            if not team:
                team = Team(
                    event_id=event_id,
                    name=row_data["team_name"],
                    lead_id=creator_user.id,
                )

                db.add(team)
                db.flush()
                teams_cache[team_key] = team

                # Add creator as team member
                member = TeamMember(
                    team_id=team.id,
                    user_id=creator_user.id,
                    role="lead",
                )
                db.add(member)

            # Match or create track if specified
            track_id = None
            if row_data["track_name"]:
                track_key = row_data["track_name"].lower()
                track = tracks.get(track_key)
                if not track:
                    track = Track(
                        event_id=event_id,
                        title=row_data["track_name"],
                        description=f"Track for {row_data['track_name']}",
                    )
                    db.add(track)
                    db.flush()
                    tracks[track_key] = track
                track_id = track.id

            project = Project(
                event_id=event_id,
                team_id=team.id,
                track_id=track_id,
                title=row_data["title"],
                tagline=row_data["tagline"],
                description=row_data["description"],
                demo_url=row_data["demo_url"],
                repository_url=row_data["repository_url"],
                is_submitted=True,
                submitted_at=now_utc,
            )
            db.add(project)
            imported_count += 1

        db.commit()

        log_audit_event(
            db=db,
            event_type="BULK_PROJECTS_IMPORTED",
            entity_type="Event",
            entity_id=event_id,
            user_id=creator_user.id,
            payload={"count": imported_count},
        )

        emit_webhook(
            db=db,
            event_type="projects.bulk_imported",
            event_id=event_id,
            resource_id=event_id,
            resource_data={"imported_count": imported_count},
        )

        return imported_count, []

    except Exception as e:
        db.rollback()
        return 0, [f"Database transaction error: {str(e)}"]


def export_projects_csv(db: Session, event_id: str) -> str:
    """Generate CSV string of projects for an event."""
    projects = db.query(Project).filter(Project.event_id == event_id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "title", "team_name", "track_title", "tagline",
        "description", "demo_url", "repository_url", "is_submitted", "submitted_at"
    ])
    for p in projects:
        writer.writerow([
            p.id,
            p.title,
            p.team.name if p.team else "",
            p.track.title if p.track else "",
            p.tagline or "",
            p.description or "",
            p.demo_url or "",
            p.repository_url or "",
            p.is_submitted,
            p.submitted_at.isoformat() if p.submitted_at else "",
        ])
    return output.getvalue()


def export_teams_csv(db: Session, event_id: str) -> str:
    """Generate CSV string of teams for an event."""
    teams = db.query(Team).filter(Team.event_id == event_id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "leader_email", "members_count", "created_at"])
    for t in teams:
        writer.writerow([
            t.id,
            t.name,
            t.lead.email if t.lead else "",
            len(t.members),
            t.created_at.isoformat() if t.created_at else "",
        ])
    return output.getvalue()


def export_scores_csv(db: Session, event_id: str) -> str:
    """Generate CSV string of judge scores for an event."""
    scores = (
        db.query(JudgeScore)
        .join(Project, JudgeScore.project_id == Project.id)
        .filter(Project.event_id == event_id)
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "score_id", "judge_name", "judge_email", "project_id",
        "project_title", "criterion_name", "score", "feedback", "created_at"
    ])
    for s in scores:
        writer.writerow([
            s.id,
            s.judge.username if s.judge else "",
            s.judge.email if s.judge else "",
            s.project_id,
            s.project.title if s.project else "",
            s.criterion.name if s.criterion else "",
            s.score,
            s.feedback or "",
            s.created_at.isoformat() if s.created_at else "",
        ])
    return output.getvalue()


def export_votes_csv(db: Session, event_id: str) -> str:
    """Generate CSV string of community votes for an event."""
    votes = (
        db.query(Vote)
        .join(VotingCampaign, Vote.campaign_id == VotingCampaign.id)
        .filter(VotingCampaign.event_id == event_id)
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "vote_id", "campaign_id", "project_id", "project_title",
        "voter_identifier", "voter_type", "created_at"
    ])
    for v in votes:
        writer.writerow([
            v.id,
            v.campaign_id,
            v.project_id,
            v.project.title if v.project else "",
            v.voter_identifier,
            v.voter_type,
            v.created_at.isoformat() if v.created_at else "",
        ])
    return output.getvalue()


def export_event_bundle_json(db: Session, event_id: str) -> Dict[str, Any]:
    """Generate a complete JSON bundle of all event data."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    tracks = db.query(Track).filter(Track.event_id == event_id).all()
    prizes = db.query(Prize).filter(Prize.event_id == event_id).all()
    teams = db.query(Team).filter(Team.event_id == event_id).all()
    projects = db.query(Project).filter(Project.event_id == event_id).all()
    rubrics = db.query(Rubric).filter(Rubric.event_id == event_id).all()
    campaigns = db.query(VotingCampaign).filter(VotingCampaign.event_id == event_id).all()
    certificates = db.query(Certificate).filter(Certificate.event_id == event_id).all()
    audit_events = db.query(AuditEvent).filter(AuditEvent.entity_id == event_id).limit(100).all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "event": {
            "id": event.id,
            "title": event.title,
            "slug": event.slug,
            "description": event.description,
            "phase": event.phase,
            "theme_config": event.theme_config,
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "end_time": event.end_time.isoformat() if event.end_time else None,
        },
        "tracks": [
            {"id": t.id, "title": t.title, "description": t.description}
            for t in tracks
        ],
        "prizes": [
            {"id": p.id, "title": p.title, "amount": p.amount, "description": p.description}
            for p in prizes
        ],
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "lead_id": t.lead_id,
                "members": [{"user_id": m.user_id, "role": m.role} for m in t.members],
            }
            for t in teams
        ],
        "projects": [
            {
                "id": p.id,
                "team_id": p.team_id,
                "track_id": p.track_id,
                "title": p.title,
                "tagline": p.tagline,
                "description": p.description,
                "demo_url": p.demo_url,
                "repository_url": p.repository_url,
                "is_submitted": p.is_submitted,
                "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            }
            for p in projects
        ],
        "rubrics": [
            {
                "id": r.id,
                "name": r.name,
                "criteria": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "weight": c.weight,
                        "min_score": c.min_score,
                        "max_score": c.max_score,
                    }
                    for c in r.criteria
                ],
            }
            for r in rubrics
        ],
        "voting_campaigns": [
            {
                "id": vc.id,
                "title": vc.title,
                "access_mode": vc.access_mode,
                "status": vc.status,
                "starts_at": vc.starts_at.isoformat() if vc.starts_at else None,
                "ends_at": vc.ends_at.isoformat() if vc.ends_at else None,
            }
            for vc in campaigns
        ],

        "certificates": [
            {
                "id": c.id,
                "recipient": c.recipient,
                "award": c.award,
                "issued_at": c.issued_at.isoformat() if c.issued_at else None,
                "verification_token": c.verification_token,
                "status": c.status,
            }
            for c in certificates
        ],
        "audit_logs_sample": [
            {
                "id": a.id,
                "event_type": a.event_type,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "payload": a.payload,
            }
            for a in audit_events
        ],
    }
