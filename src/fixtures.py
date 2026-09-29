"""Idempotent fixture loader with timestamp normalization and fault tolerance."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from src.auth.models import User
from src.events.models import Event, Track, Prize
from src.submissions.models import Team, TeamMember, TeamInvite, Project
from src.judging.models import Rubric, RubricCriterion, JudgeAssignment, JudgeScore
from src.audit.models import AuditEvent
from src.auth.service import hash_password


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    """Parse ISO formatted datetime string and ensure timezone-aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        val = value.strip()
        if not val:
            return None
        # Normalize trailing Z to UTC offset
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def load_fixtures(
    filepath_or_data: Union[str, Path, Dict[str, Any]],
    db: Session,
) -> Dict[str, int]:
    """
    Load data fixtures into the database idempotently.
    
    Guarantees:
    - Preserves explicit fixture IDs
    - Parses all timestamps to ISO UTC
    - Tolerates missing score entries (score: null or omitted)
    - Tolerates duplicate submission/project data
    - Handles judges with identical numerical scores
    - Safe to execute repeatedly without raising primary key or unique errors
    """
    if isinstance(filepath_or_data, (str, Path)):
        path = Path(filepath_or_data)
        if not path.exists():
            raise FileNotFoundError(f"Fixture file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(filepath_or_data, dict):
        data = filepath_or_data
    else:
        raise ValueError("Invalid fixture input: expected Path, filepath string, or dict.")

    counts: Dict[str, int] = {}

    # 1. USERS
    raw_users: List[Dict[str, Any]] = data.get("users", [])
    user_count = 0
    for u in raw_users:
        uid = str(u["id"])
        user = db.query(User).filter(User.id == uid).first()
        created_at = parse_iso_datetime(u.get("created_at")) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(u.get("updated_at")) or datetime.now(timezone.utc)
        pwd = u.get("password", "changeme_default_2026")
        hashed = u.get("hashed_password") or hash_password(pwd)

        if not user:
            user = User(
                id=uid,
                username=u["username"],
                email=u["email"],
                hashed_password=hashed,
                role=u.get("role", "participant"),
                is_active=u.get("is_active", True),
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(user)
        else:
            user.username = u["username"]
            user.email = u["email"]
            user.role = u.get("role", user.role)
            user.is_active = u.get("is_active", user.is_active)
            user.updated_at = updated_at
        user_count += 1
    db.flush()
    counts["users"] = user_count

    # 2. EVENTS
    raw_events: List[Dict[str, Any]] = data.get("events", [])
    event_count = 0
    for ev in raw_events:
        eid = str(ev["id"])
        event = db.query(Event).filter(Event.id == eid).first()
        created_at = parse_iso_datetime(ev.get("created_at")) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(ev.get("updated_at")) or datetime.now(timezone.utc)
        start_time = parse_iso_datetime(ev.get("start_time"))
        end_time = parse_iso_datetime(ev.get("end_time"))

        if not event:
            event = Event(
                id=eid,
                title=ev["title"],
                slug=ev["slug"],
                description=ev.get("description"),
                theme_config=ev.get("theme_config"),
                phase=ev.get("phase", "pre-event"),
                start_time=start_time,
                end_time=end_time,
                created_by_id=ev.get("created_by_id"),
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(event)
        else:
            event.title = ev["title"]
            event.slug = ev["slug"]
            event.description = ev.get("description", event.description)
            event.theme_config = ev.get("theme_config", event.theme_config)
            event.phase = ev.get("phase", event.phase)
            event.start_time = start_time
            event.end_time = end_time
            event.created_by_id = ev.get("created_by_id", event.created_by_id)
            event.updated_at = updated_at
        event_count += 1
    db.flush()
    counts["events"] = event_count

    # 3. TRACKS
    raw_tracks: List[Dict[str, Any]] = data.get("tracks", [])
    track_count = 0
    for tr in raw_tracks:
        tid = str(tr["id"])
        track = db.query(Track).filter(Track.id == tid).first()
        created_at = parse_iso_datetime(tr.get("created_at")) or datetime.now(timezone.utc)
        if not track:
            track = Track(
                id=tid,
                event_id=tr["event_id"],
                title=tr["title"],
                description=tr.get("description"),
                created_at=created_at,
            )
            db.add(track)
        else:
            track.event_id = tr["event_id"]
            track.title = tr["title"]
            track.description = tr.get("description", track.description)
        track_count += 1
    db.flush()
    counts["tracks"] = track_count

    # 4. PRIZES
    raw_prizes: List[Dict[str, Any]] = data.get("prizes", [])
    prize_count = 0
    for pr in raw_prizes:
        pid = str(pr["id"])
        prize = db.query(Prize).filter(Prize.id == pid).first()
        created_at = parse_iso_datetime(pr.get("created_at")) or datetime.now(timezone.utc)
        if not prize:
            prize = Prize(
                id=pid,
                event_id=pr["event_id"],
                track_id=pr.get("track_id"),
                title=pr["title"],
                description=pr.get("description"),
                amount=pr.get("amount"),
                created_at=created_at,
            )
            db.add(prize)
        else:
            prize.event_id = pr["event_id"]
            prize.track_id = pr.get("track_id", prize.track_id)
            prize.title = pr["title"]
            prize.description = pr.get("description", prize.description)
            prize.amount = pr.get("amount", prize.amount)
        prize_count += 1
    db.flush()
    counts["prizes"] = prize_count

    # 5. TEAMS
    raw_teams: List[Dict[str, Any]] = data.get("teams", [])
    team_count = 0
    for tm in raw_teams:
        team_id = str(tm["id"])
        team = db.query(Team).filter(Team.id == team_id).first()
        created_at = parse_iso_datetime(tm.get("created_at")) or datetime.now(timezone.utc)
        if not team:
            team = Team(
                id=team_id,
                event_id=tm["event_id"],
                name=tm["name"],
                slug=tm.get("slug"),
                lead_id=tm.get("lead_id"),
                created_at=created_at,
            )
            db.add(team)
        else:
            team.event_id = tm["event_id"]
            team.name = tm["name"]
            team.slug = tm.get("slug", team.slug)
            team.lead_id = tm.get("lead_id", team.lead_id)
        team_count += 1
    db.flush()
    counts["teams"] = team_count

    # 6. TEAM MEMBERS
    raw_members: List[Dict[str, Any]] = data.get("team_members", [])
    member_count = 0
    for mb in raw_members:
        mid = str(mb["id"])
        member = db.query(TeamMember).filter(
            (TeamMember.id == mid) | 
            ((TeamMember.team_id == mb["team_id"]) & (TeamMember.user_id == mb["user_id"]))
        ).first()
        joined_at = parse_iso_datetime(mb.get("joined_at")) or datetime.now(timezone.utc)

        if not member:
            member = TeamMember(
                id=mid,
                team_id=mb["team_id"],
                user_id=mb["user_id"],
                role=mb.get("role", "member"),
                joined_at=joined_at,
            )
            db.add(member)
        else:
            member.role = mb.get("role", member.role)
        member_count += 1
    db.flush()
    counts["team_members"] = member_count

    # 7. TEAM INVITES
    raw_invites: List[Dict[str, Any]] = data.get("team_invites", [])
    invite_count = 0
    for inv in raw_invites:
        iid = str(inv["id"])
        invite = db.query(TeamInvite).filter(
            (TeamInvite.id == iid) | (TeamInvite.token == inv["token"])
        ).first()
        created_at = parse_iso_datetime(inv.get("created_at")) or datetime.now(timezone.utc)
        expires_at = parse_iso_datetime(inv.get("expires_at"))

        if not invite:
            invite = TeamInvite(
                id=iid,
                team_id=inv["team_id"],
                inviter_id=inv["inviter_id"],
                invitee_email=inv["invitee_email"],
                token=inv["token"],
                status=inv.get("status", "pending"),
                created_at=created_at,
                expires_at=expires_at,
            )
            db.add(invite)
        else:
            invite.status = inv.get("status", invite.status)
            invite.expires_at = expires_at
        invite_count += 1
    db.flush()
    counts["team_invites"] = invite_count

    # 8. PROJECTS (Tolerates duplicate submission data gracefully)
    raw_projects: List[Dict[str, Any]] = data.get("projects", [])
    project_count = 0
    batch_projects: Dict[str, Project] = {}

    for pj in raw_projects:
        pid = str(pj["id"])
        project = batch_projects.get(pid)
        if not project:
            project = db.query(Project).filter(Project.id == pid).first()

        if not project:
            for p in batch_projects.values():
                if p.event_id == pj["event_id"] and p.team_id == pj["team_id"]:
                    project = p
                    break

        if not project:
            project = db.query(Project).filter(
                Project.event_id == pj["event_id"],
                Project.team_id == pj["team_id"],
            ).first()

        submitted_at = parse_iso_datetime(pj.get("submitted_at"))
        created_at = parse_iso_datetime(pj.get("created_at")) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(pj.get("updated_at")) or datetime.now(timezone.utc)

        if not project:
            project = Project(
                id=pid,
                event_id=pj["event_id"],
                team_id=pj["team_id"],
                track_id=pj.get("track_id"),
                title=pj["title"],
                tagline=pj.get("tagline"),
                description=pj.get("description"),
                repository_url=pj.get("repository_url"),
                demo_url=pj.get("demo_url"),
                video_url=pj.get("video_url"),
                submitted_at=submitted_at,
                is_submitted=pj.get("is_submitted", True if submitted_at else False),
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(project)
        else:
            # Update existing project with latest submission data
            project.title = pj.get("title", project.title)
            project.tagline = pj.get("tagline", project.tagline)
            project.description = pj.get("description", project.description)
            project.track_id = pj.get("track_id", project.track_id)
            project.repository_url = pj.get("repository_url", project.repository_url)
            project.demo_url = pj.get("demo_url", project.demo_url)
            project.video_url = pj.get("video_url", project.video_url)
            project.submitted_at = submitted_at or project.submitted_at
            project.is_submitted = pj.get("is_submitted", project.is_submitted)
            project.updated_at = updated_at

        batch_projects[project.id] = project
        project_count += 1
    db.flush()
    counts["projects"] = project_count

    # 9. RUBRICS
    raw_rubrics: List[Dict[str, Any]] = data.get("rubrics", [])
    rubric_count = 0
    for rb in raw_rubrics:
        rid = str(rb["id"])
        rubric = db.query(Rubric).filter(Rubric.id == rid).first()
        created_at = parse_iso_datetime(rb.get("created_at")) or datetime.now(timezone.utc)
        if not rubric:
            rubric = Rubric(
                id=rid,
                event_id=rb["event_id"],
                name=rb["name"],
                description=rb.get("description"),
                created_at=created_at,
            )
            db.add(rubric)
        else:
            rubric.event_id = rb["event_id"]
            rubric.name = rb["name"]
            rubric.description = rb.get("description", rubric.description)
        rubric_count += 1
    db.flush()
    counts["rubrics"] = rubric_count

    # 10. RUBRIC CRITERIA
    raw_criteria: List[Dict[str, Any]] = data.get("rubric_criteria", [])
    criteria_count = 0
    for cr in raw_criteria:
        cid = str(cr["id"])
        criterion = db.query(RubricCriterion).filter(RubricCriterion.id == cid).first()
        if not criterion:
            criterion = RubricCriterion(
                id=cid,
                rubric_id=cr["rubric_id"],
                name=cr["name"],
                description=cr.get("description"),
                weight=float(cr.get("weight", 1.0)),
                min_score=float(cr.get("min_score", 1.0)),
                max_score=float(cr.get("max_score", 10.0)),
                order_index=int(cr.get("order_index", 0)),
            )
            db.add(criterion)
        else:
            criterion.name = cr["name"]
            criterion.description = cr.get("description", criterion.description)
            criterion.weight = float(cr.get("weight", criterion.weight))
            criterion.min_score = float(cr.get("min_score", criterion.min_score))
            criterion.max_score = float(cr.get("max_score", criterion.max_score))
            criterion.order_index = int(cr.get("order_index", criterion.order_index))
        criteria_count += 1
    db.flush()
    counts["rubric_criteria"] = criteria_count

    # 11. JUDGE ASSIGNMENTS
    raw_assignments: List[Dict[str, Any]] = data.get("judge_assignments", [])
    assignment_count = 0
    for ja in raw_assignments:
        jid = str(ja["id"])
        assignment = db.query(JudgeAssignment).filter(
            (JudgeAssignment.id == jid) |
            ((JudgeAssignment.judge_id == ja["judge_id"]) & (JudgeAssignment.project_id == ja["project_id"]))
        ).first()
        created_at = parse_iso_datetime(ja.get("created_at")) or datetime.now(timezone.utc)

        if not assignment:
            assignment = JudgeAssignment(
                id=jid,
                event_id=ja["event_id"],
                judge_id=ja["judge_id"],
                project_id=ja["project_id"],
                status=ja.get("status", "assigned"),
                created_at=created_at,
            )
            db.add(assignment)
        else:
            assignment.status = ja.get("status", assignment.status)
        assignment_count += 1
    db.flush()
    counts["judge_assignments"] = assignment_count

    # 12. JUDGE SCORES (Tolerates missing score entries & identical scores across judges)
    raw_scores: List[Dict[str, Any]] = data.get("judge_scores", [])
    score_count = 0
    for sc in raw_scores:
        sid = str(sc["id"])
        score_record = db.query(JudgeScore).filter(
            (JudgeScore.id == sid) |
            (
                (JudgeScore.judge_id == sc["judge_id"]) &
                (JudgeScore.project_id == sc["project_id"]) &
                (JudgeScore.criterion_id == sc["criterion_id"])
            )
        ).first()

        created_at = parse_iso_datetime(sc.get("created_at")) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(sc.get("updated_at")) or datetime.now(timezone.utc)

        # Parse numerical score safely; tolerate None/null or omitted
        raw_score_val = sc.get("score")
        score_val: Optional[float] = None
        if raw_score_val is not None and str(raw_score_val).strip() != "":
            try:
                score_val = float(raw_score_val)
            except (ValueError, TypeError):
                score_val = None

        if not score_record:
            score_record = JudgeScore(
                id=sid,
                assignment_id=sc.get("assignment_id"),
                judge_id=sc["judge_id"],
                project_id=sc["project_id"],
                criterion_id=sc["criterion_id"],
                score=score_val,
                feedback=sc.get("feedback"),
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(score_record)
        else:
            score_record.score = score_val
            score_record.feedback = sc.get("feedback", score_record.feedback)
            score_record.updated_at = updated_at
        score_count += 1
    db.flush()
    counts["judge_scores"] = score_count

    # 13. AUDIT EVENTS
    raw_audits: List[Dict[str, Any]] = data.get("audit_events", [])
    audit_count = 0
    for ae in raw_audits:
        aid = str(ae["id"])
        audit = db.query(AuditEvent).filter(AuditEvent.id == aid).first()
        timestamp = parse_iso_datetime(ae.get("timestamp")) or datetime.now(timezone.utc)
        if not audit:
            audit = AuditEvent(
                id=aid,
                event_type=ae["event_type"],
                entity_type=ae.get("entity_type"),
                entity_id=ae.get("entity_id"),
                user_id=ae.get("user_id"),
                payload=ae.get("payload"),
                timestamp=timestamp,
                ip_address=ae.get("ip_address"),
            )
            db.add(audit)
        else:
            audit.payload = ae.get("payload", audit.payload)
        audit_count += 1
    db.flush()
    counts["audit_events"] = audit_count

    db.commit()
    return counts
