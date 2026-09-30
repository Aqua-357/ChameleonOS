"""Voting and comments domain service implementing anti-abuse, ballot randomization, and result secrecy."""

import hashlib
import random
import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.audit.service import log_audit_event
from src.auth.models import User
from src.events.models import Event
from src.submissions.models import Project
from src.voting.models import EmailVoterToken, ProjectComment, Vote, VotingCampaign
from src.voting.schemas import (
    VotingCampaignCreateRequest,
    VotingCampaignUpdateRequest,
)


# ==============================================================================
# IN-MEMORY SLIDING WINDOW RATE LIMITER (ANTI-ABUSE)
# ==============================================================================

class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter for voting actions."""

    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(deque)

    def is_allowed(self, identifier: str, max_requests: int = 5, window_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        with self._lock:
            timestamps = self._history[identifier]
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_requests:
                return False

            timestamps.append(now)
            return True

    def reset(self, identifier: Optional[str] = None):
        """Reset rate limiter state (useful for test isolation)."""
        with self._lock:
            if identifier:
                self._history.pop(identifier, None)
            else:
                self._history.clear()


rate_limiter = SlidingWindowRateLimiter()


# ==============================================================================
# VOTING CAMPAIGN MANAGEMENT
# ==============================================================================

def create_voting_campaign(
    db: Session,
    req: VotingCampaignCreateRequest,
    user: User,
    ip_address: Optional[str] = None,
) -> VotingCampaign:
    """Create a new voting campaign for an event."""
    event = db.query(Event).filter(Event.id == req.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    campaign = VotingCampaign(
        event_id=req.event_id,
        title=req.title,
        description=req.description,
        starts_at=req.starts_at,
        ends_at=req.ends_at,
        access_mode=req.access_mode,
        voting_method=req.voting_method,
        results_visibility=req.results_visibility,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    log_audit_event(
        db=db,
        event_type="VOTING_CAMPAIGN_CREATED",
        entity_type="VotingCampaign",
        entity_id=campaign.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={
            "event_id": campaign.event_id,
            "title": campaign.title,
            "access_mode": campaign.access_mode,
            "voting_method": campaign.voting_method,
        },
    )

    return campaign


def update_voting_campaign(
    db: Session,
    campaign_id: str,
    req: VotingCampaignUpdateRequest,
    user: User,
    ip_address: Optional[str] = None,
) -> VotingCampaign:
    """Update voting campaign settings."""
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    if req.title is not None:
        campaign.title = req.title
    if req.description is not None:
        campaign.description = req.description
    if req.starts_at is not None:
        campaign.starts_at = req.starts_at
    if req.ends_at is not None:
        campaign.ends_at = req.ends_at
    if req.access_mode is not None:
        campaign.access_mode = req.access_mode
    if req.voting_method is not None:
        campaign.voting_method = req.voting_method
    if req.results_visibility is not None:
        campaign.results_visibility = req.results_visibility
    if req.status is not None:
        campaign.status = req.status

    db.commit()
    db.refresh(campaign)

    log_audit_event(
        db=db,
        event_type="VOTING_CAMPAIGN_UPDATED",
        entity_type="VotingCampaign",
        entity_id=campaign.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={"status": campaign.status, "access_mode": campaign.access_mode},
    )

    return campaign


def activate_voting_campaign(
    db: Session,
    campaign_id: str,
    user: User,
    ip_address: Optional[str] = None,
) -> VotingCampaign:
    """Activate a voting campaign, opening it for voter participation."""
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    campaign.status = "active"
    if not campaign.starts_at:
        campaign.starts_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(campaign)

    log_audit_event(
        db=db,
        event_type="VOTING_CAMPAIGN_ACTIVATED",
        entity_type="VotingCampaign",
        entity_id=campaign.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={"starts_at": campaign.starts_at.isoformat() if campaign.starts_at else None},
    )

    return campaign


def close_voting_campaign(
    db: Session,
    campaign_id: str,
    user: User,
    ip_address: Optional[str] = None,
) -> VotingCampaign:
    """Close an active voting campaign and finalize tally."""
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    campaign.status = "closed"
    if not campaign.ends_at:
        campaign.ends_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(campaign)

    log_audit_event(
        db=db,
        event_type="VOTING_CAMPAIGN_CLOSED",
        entity_type="VotingCampaign",
        entity_id=campaign.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={"ends_at": campaign.ends_at.isoformat() if campaign.ends_at else None},
    )

    return campaign


# ==============================================================================
# DETERMINISTIC BALLOT RANDOMIZATION (SERVER-DERIVED SEED)
# ==============================================================================

def get_deterministic_ballot(
    db: Session,
    campaign_id: str,
    voter_key: str,
) -> Tuple[VotingCampaign, List[Dict[str, Any]]]:
    """
    Produce a deterministic pseudo-random ordered project ballot for a voter.
    Uses SHA-256 hash of (campaign_id:voter_key) as PRNG seed.
    Guarantees page refresh stability while neutralizing project position bias.
    """
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    # Retrieve all submitted projects for the campaign's event
    projects = (
        db.query(Project)
        .filter(Project.event_id == campaign.event_id, Project.is_submitted.is_(True))
        .all()
    )

    # Deterministic server seed
    seed_str = f"{campaign.id}:{voter_key}"
    seed_int = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)

    shuffled_projects = list(projects)
    rng.shuffle(shuffled_projects)

    # Determine voter's existing votes
    voted_project_ids = set()
    if voter_key:
        votes = (
            db.query(Vote.project_id)
            .filter(Vote.campaign_id == campaign.id, Vote.voter_key == voter_key)
            .all()
        )
        voted_project_ids = {v[0] for v in votes}

    items = []
    for p in shuffled_projects:
        items.append({
            "project_id": p.id,
            "title": p.title,
            "tagline": p.tagline,
            "description": p.description,
            "team_name": p.team.name if p.team else "Independent",
            "track_title": p.track.title if p.track else None,
            "demo_url": p.demo_url,
            "repository_url": p.repository_url,
            "video_url": p.video_url,
            "has_voted": p.id in voted_project_ids,
        })

    return campaign, items


# ==============================================================================
# OFFLINE EMAIL VERIFICATION FLOW
# ==============================================================================

def request_email_token(
    db: Session,
    campaign_id: str,
    email: str,
    ip_address: Optional[str] = None,
) -> EmailVoterToken:
    """
    Generate an offline-compatible email verification token and 6-digit code.
    No external SMTP or network service required.
    """
    email_clean = email.strip().lower()
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    # Check if there is an existing verified token for this email
    existing = (
        db.query(EmailVoterToken)
        .filter(EmailVoterToken.campaign_id == campaign_id, EmailVoterToken.email == email_clean)
        .first()
    )

    if existing and existing.is_verified:
        return existing

    token = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    if existing:
        existing.token = token
        existing.verification_code = code
        existing.expires_at = expires_at
        existing.is_verified = False
        tok = existing
    else:
        tok = EmailVoterToken(
            campaign_id=campaign_id,
            email=email_clean,
            token=token,
            verification_code=code,
            is_verified=False,
            expires_at=expires_at,
        )
        db.add(tok)

    db.commit()
    db.refresh(tok)

    log_audit_event(
        db=db,
        event_type="VOTER_EMAIL_TOKEN_GENERATED",
        entity_type="VotingCampaign",
        entity_id=campaign_id,
        ip_address=ip_address,
        payload={"email": email_clean, "code": code, "token": token},
    )

    return tok


def confirm_email_token(
    db: Session,
    campaign_id: str,
    token: Optional[str] = None,
    code: Optional[str] = None,
    email: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> EmailVoterToken:
    """Verify an offline email voter token via token string or email+code combination."""
    query = db.query(EmailVoterToken).filter(EmailVoterToken.campaign_id == campaign_id)

    if token:
        query = query.filter(EmailVoterToken.token == token.strip())
    elif email and code:
        query = query.filter(
            EmailVoterToken.email == email.strip().lower(),
            EmailVoterToken.verification_code == code.strip(),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either verification token or email + verification code must be provided.",
        )

    tok = query.first()
    if not tok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification token or code not found.",
        )

    now = datetime.now(timezone.utc)
    if tok.expires_at and now > tok.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new token.",
        )

    tok.is_verified = True
    db.commit()
    db.refresh(tok)

    log_audit_event(
        db=db,
        event_type="VOTER_EMAIL_VERIFIED",
        entity_type="VotingCampaign",
        entity_id=campaign_id,
        ip_address=ip_address,
        payload={"email": tok.email, "token": tok.token},
    )

    return tok


# ==============================================================================
# VOTE CASTING WITH REAL ANTI-ABUSE & AUDIT INTEGRATION
# ==============================================================================

def cast_vote(
    db: Session,
    campaign_id: str,
    project_id: str,
    voter_key: Optional[str] = None,
    user: Optional[User] = None,
    ip_address: Optional[str] = None,
    weight: float = 1.0,
) -> Vote:
    """
    Cast a community vote with strict anti-abuse enforcement:
    1. Campaign active window check
    2. Access mode authorization (open, email, authenticated)
    3. Server-side rate limiting per voter identity & IP
    4. Duplicate vote rejection (single or approval method)
    5. Immutable tamper-evident audit logging for both accepted and rejected attempts
    """
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    now = datetime.now(timezone.utc)

    # 1. Campaign status check
    if campaign.status != "active":
        log_audit_event(
            db=db,
            event_type="VOTE_REJECTED_CAMPAIGN_INACTIVE",
            entity_type="VotingCampaign",
            entity_id=campaign_id,
            user_id=user.id if user else None,
            ip_address=ip_address,
            payload={"status": campaign.status, "project_id": project_id},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Voting campaign is currently {campaign.status}.",
        )

    if campaign.starts_at and now < campaign.starts_at:
        log_audit_event(
            db=db,
            event_type="VOTE_REJECTED_WINDOW",
            entity_type="VotingCampaign",
            entity_id=campaign_id,
            user_id=user.id if user else None,
            ip_address=ip_address,
            payload={"reason": "Campaign has not started yet"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voting campaign has not started yet.",
        )

    if campaign.ends_at and now > campaign.ends_at:
        log_audit_event(
            db=db,
            event_type="VOTE_REJECTED_WINDOW",
            entity_type="VotingCampaign",
            entity_id=campaign_id,
            user_id=user.id if user else None,
            ip_address=ip_address,
            payload={"reason": "Campaign has ended"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voting campaign deadline has passed.",
        )

    # 2. Project check
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.event_id == campaign.event_id, Project.is_submitted.is_(True))
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or not submitted for this event.",
        )

    # 3. Access Mode Authorization & Identity Derivation
    if campaign.access_mode == "authenticated":
        if not user:
            log_audit_event(
                db=db,
                event_type="VOTE_REJECTED_UNAUTHORIZED",
                entity_type="VotingCampaign",
                entity_id=campaign_id,
                ip_address=ip_address,
                payload={"reason": "Authentication required for this campaign"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to participate in this voting campaign.",
            )
        effective_voter_key = f"auth:{user.id}"

    elif campaign.access_mode == "email":
        if not voter_key:
            log_audit_event(
                db=db,
                event_type="VOTE_REJECTED_UNAUTHORIZED",
                entity_type="VotingCampaign",
                entity_id=campaign_id,
                ip_address=ip_address,
                payload={"reason": "Missing email verification token"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required to participate in this voting campaign.",
            )

        # Verify email token
        tok_clean = voter_key.strip()
        tok = (
            db.query(EmailVoterToken)
            .filter(
                EmailVoterToken.campaign_id == campaign_id,
                EmailVoterToken.token == tok_clean,
                EmailVoterToken.is_verified.is_(True),
            )
            .first()
        )
        if not tok:
            log_audit_event(
                db=db,
                event_type="VOTE_REJECTED_UNAUTHORIZED",
                entity_type="VotingCampaign",
                entity_id=campaign_id,
                ip_address=ip_address,
                payload={"voter_key": voter_key, "reason": "Unverified or invalid email token"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or unverified email token for this campaign.",
            )
        effective_voter_key = f"email:{tok.email}"

    elif campaign.access_mode == "open":
        if voter_key and voter_key.strip():
            effective_voter_key = f"open:{voter_key.strip()}"
        else:
            effective_voter_key = f"ip:{ip_address or 'anonymous'}"
    else:
        effective_voter_key = f"key:{voter_key or 'anonymous'}"

    # 4. Anti-Abuse: Server-side Rate Limiting
    rate_limit_id = f"{campaign_id}:{effective_voter_key}:{ip_address or '0.0.0.0'}"
    if not rate_limiter.is_allowed(rate_limit_id, max_requests=5, window_seconds=60):
        log_audit_event(
            db=db,
            event_type="VOTE_RATE_LIMITED",
            entity_type="VotingCampaign",
            entity_id=campaign_id,
            user_id=user.id if user else None,
            ip_address=ip_address,
            payload={"voter_key": effective_voter_key, "rate_limit_id": rate_limit_id},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: Too many voting attempts. Please wait before retrying.",
        )

    # 5. Anti-Abuse: Duplicate Vote Detection
    if campaign.voting_method == "single":
        existing_vote = (
            db.query(Vote)
            .filter(Vote.campaign_id == campaign_id, Vote.voter_key == effective_voter_key)
            .first()
        )
        if existing_vote:
            log_audit_event(
                db=db,
                event_type="VOTE_DUPLICATE_REJECTED",
                entity_type="VotingCampaign",
                entity_id=campaign_id,
                user_id=user.id if user else None,
                ip_address=ip_address,
                payload={
                    "voter_key": effective_voter_key,
                    "attempted_project_id": project_id,
                    "existing_project_id": existing_vote.project_id,
                    "reason": "Single-choice ballot already submitted",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate vote rejected: You have already cast your ballot in this campaign.",
            )
    elif campaign.voting_method == "approval":
        existing_vote = (
            db.query(Vote)
            .filter(
                Vote.campaign_id == campaign_id,
                Vote.project_id == project_id,
                Vote.voter_key == effective_voter_key,
            )
            .first()
        )
        if existing_vote:
            log_audit_event(
                db=db,
                event_type="VOTE_DUPLICATE_REJECTED",
                entity_type="VotingCampaign",
                entity_id=campaign_id,
                user_id=user.id if user else None,
                ip_address=ip_address,
                payload={
                    "voter_key": effective_voter_key,
                    "project_id": project_id,
                    "reason": "Approval vote already recorded for this project",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate vote rejected: You have already voted for this project.",
            )

    # 6. Record Vote and Audit Event
    vote = Vote(
        campaign_id=campaign_id,
        project_id=project_id,
        voter_key=effective_voter_key,
        user_id=user.id if user else None,
        weight=weight,
        ip_address=ip_address,
    )
    db.add(vote)
    db.commit()
    db.refresh(vote)

    log_audit_event(
        db=db,
        event_type="VOTE_ACCEPTED",
        entity_type="VotingCampaign",
        entity_id=campaign_id,
        user_id=user.id if user else None,
        ip_address=ip_address,
        payload={
            "vote_id": vote.id,
            "project_id": project_id,
            "voter_key": effective_voter_key,
            "weight": weight,
        },
    )

    return vote


# ==============================================================================
# RESULT SECRECY & AGGREGATE CALCULATION
# ==============================================================================

def get_campaign_results(
    db: Session,
    campaign_id: str,
    user: Optional[User] = None,
) -> Dict[str, Any]:
    """
    Retrieve aggregated voting campaign results with strict result secrecy:
    - During active voting:
      * Organizers & Admins CAN view live aggregate progress.
      * Visitors, participants, and judges CANNOT view results (HTTP 403 Forbidden).
    - After voting closes:
      * Results become publicly visible according to campaign configuration
        ('public_after_close' vs 'organizers_only').
    """
    campaign = db.query(VotingCampaign).filter(VotingCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voting campaign not found.")

    is_organizer = user and user.role in ["organizer", "admin"]

    # Secrecy gate during active / draft voting
    if campaign.status != "closed":
        if not is_organizer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voting results are sealed while campaign is active. Only organizers may inspect live tally.",
            )
    else:
        # Campaign is closed: check configured visibility
        if campaign.results_visibility == "organizers_only" and not is_organizer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Campaign results are restricted to organizers only.",
            )

    # Compute tally
    projects = (
        db.query(Project)
        .filter(Project.event_id == campaign.event_id, Project.is_submitted.is_(True))
        .all()
    )

    vote_counts = (
        db.query(
            Vote.project_id,
            func.count(Vote.id).label("votes_count"),
            func.sum(Vote.weight).label("votes_weight"),
        )
        .filter(Vote.campaign_id == campaign_id)
        .group_by(Vote.project_id)
        .all()
    )

    tally_map = {vc[0]: (vc[1], float(vc[2] or 0.0)) for vc in vote_counts}

    total_votes = sum(t[0] for t in tally_map.values())
    total_weight = sum(t[1] for t in tally_map.values())

    unique_voters_count = (
        db.query(func.count(func.distinct(Vote.voter_key)))
        .filter(Vote.campaign_id == campaign_id)
        .scalar()
        or 0
    )

    project_results = []
    for p in projects:
        c, w = tally_map.get(p.id, (0, 0.0))
        pct = (w / total_weight * 100.0) if total_weight > 0 else 0.0
        project_results.append({
            "project_id": p.id,
            "project_title": p.title,
            "team_name": p.team.name if p.team else "Independent",
            "track_title": p.track.title if p.track else None,
            "votes_count": c,
            "votes_weight": round(w, 2),
            "percentage": round(pct, 1),
        })

    # Sort descending by votes weight, then votes count, then project title
    project_results.sort(key=lambda x: (x["votes_weight"], x["votes_count"], x["project_title"]), reverse=True)

    # Assign ranks
    for rank, item in enumerate(project_results, start=1):
        item["rank"] = rank

    return {
        "campaign_id": campaign.id,
        "campaign_title": campaign.title,
        "event_id": campaign.event_id,
        "status": campaign.status,
        "results_visibility": campaign.results_visibility,
        "total_votes": total_votes,
        "total_unique_voters": unique_voters_count,
        "results": project_results,
    }


# ==============================================================================
# PROJECT COMMENTS & MODERATION SYSTEM
# ==============================================================================

def add_project_comment(
    db: Session,
    project_id: str,
    body: str,
    user: User,
    ip_address: Optional[str] = None,
) -> ProjectComment:
    """Post an authenticated comment on a public submitted project."""
    project = db.query(Project).filter(Project.id == project_id, Project.is_submitted.is_(True)).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or not submitted.",
        )

    clean_body = body.strip()
    if not clean_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment body cannot be empty.")

    comment = ProjectComment(
        project_id=project_id,
        author_id=user.id,
        author_name=user.username,
        body=clean_body,
        is_deleted=False,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    log_audit_event(
        db=db,
        event_type="COMMENT_POSTED",
        entity_type="ProjectComment",
        entity_id=comment.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={"project_id": project_id, "comment_length": len(clean_body)},
    )

    return comment


def list_project_comments(
    db: Session,
    project_id: str,
    include_deleted: bool = False,
) -> List[ProjectComment]:
    """Retrieve comments for a project, omitting moderated/deleted comments by default."""
    query = db.query(ProjectComment).filter(ProjectComment.project_id == project_id)
    if not include_deleted:
        query = query.filter(ProjectComment.is_deleted.is_(False))
    return query.order_by(ProjectComment.created_at.asc()).all()


def moderate_project_comment(
    db: Session,
    project_id: str,
    comment_id: str,
    user: User,
    ip_address: Optional[str] = None,
) -> ProjectComment:
    """Moderate and soft-delete a project comment (Organizers/Admins only)."""
    comment = (
        db.query(ProjectComment)
        .filter(ProjectComment.id == comment_id, ProjectComment.project_id == project_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")

    comment.is_deleted = True
    comment.moderated_by_id = user.id
    comment.moderated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(comment)

    log_audit_event(
        db=db,
        event_type="COMMENT_MODERATED",
        entity_type="ProjectComment",
        entity_id=comment.id,
        user_id=user.id,
        ip_address=ip_address,
        payload={"project_id": project_id, "moderated_by": user.username},
    )

    return comment
