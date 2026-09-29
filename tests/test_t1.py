"""Milestone T1 Tests for ChameleonOS.

Tests cover:
1. Role permissions (visitor, participant, judge, organizer, admin)
2. Event creation & configurable dates (tracks and prizes)
3. Team creation and tokenized invite links
4. Project draft creation and editing
5. Strict submission deadline enforcement (participant cannot submit after deadline)
6. Public project gallery access without authentication
7. Project search and filtering (keyword and track)
8. HTML view routes and cookie-based session handling
"""

from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.service import create_access_token, SESSION_COOKIE_NAME
from src.events.models import Event, Track, Prize
from src.submissions.models import Project, Team, TeamMember


# ==============================================================================
# 1. ROLE PERMISSIONS
# ==============================================================================

def test_role_permissions(client: TestClient, auth_tokens: Dict[str, str], test_db: Session):
    """
    Verify role-based access control:
    - Visitor (no auth) cannot create events, teams, or drafts.
    - Participant can create teams and drafts, but cannot create events or tracks.
    - Judge cannot create events.
    - Organizer and Admin can create events, tracks, and prizes.
    """
    visitor_headers = {}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    admin_headers = {"Authorization": f"Bearer {auth_tokens['admin']}"}

    event_payload = {
        "title": "Role Test Event",
        "slug": "role-test-event",
        "description": "Testing permissions",
        "phase": "active",
    }

    # Visitor cannot create event
    res = client.post("/api/v1/events", json=event_payload, headers=visitor_headers)
    assert res.status_code == 401

    # Participant cannot create event
    res = client.post("/api/v1/events", json=event_payload, headers=participant_headers)
    assert res.status_code == 403

    # Judge cannot create event
    res = client.post("/api/v1/events", json=event_payload, headers=judge_headers)
    assert res.status_code == 403

    # Organizer CAN create event
    res = client.post("/api/v1/events", json=event_payload, headers=organizer_headers)
    assert res.status_code == 201
    event_id = res.json()["id"]

    # Participant cannot create track on event
    track_payload = {"title": "AI Track", "description": "AI systems"}
    res = client.post(f"/api/v1/events/{event_id}/tracks", json=track_payload, headers=participant_headers)
    assert res.status_code == 403

    # Organizer CAN create track
    res = client.post(f"/api/v1/events/{event_id}/tracks", json=track_payload, headers=organizer_headers)
    assert res.status_code == 201
    track_id = res.json()["id"]

    # Admin CAN create prize
    prize_payload = {"title": "First Prize", "track_id": track_id, "amount": "$5,000"}
    res = client.post(f"/api/v1/events/{event_id}/prizes", json=prize_payload, headers=admin_headers)
    assert res.status_code == 201

    # Participant CAN create team
    team_payload = {"event_id": event_id, "name": "Team Participant"}
    res = client.post("/api/v1/teams", json=team_payload, headers=participant_headers)
    assert res.status_code == 201
    team_id = res.json()["id"]

    # Participant CAN create project draft
    draft_payload = {
        "event_id": event_id,
        "team_id": team_id,
        "track_id": track_id,
        "title": "Participant Project Draft",
    }
    res = client.post("/api/v1/projects", json=draft_payload, headers=participant_headers)
    assert res.status_code == 201


# ==============================================================================
# 2. EVENT CREATION & CONFIGURABLE DATES
# ==============================================================================

def test_event_creation_and_dates(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify event creation stores configurable UTC start_time and end_time deadlines."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    start = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
    deadline = datetime(2026, 10, 3, 18, 0, 0, tzinfo=timezone.utc)

    event_payload = {
        "title": "Global Hackathon 2026",
        "slug": "global-hack-2026",
        "description": "Adaptive event platform dogfood",
        "phase": "active",
        "start_time": start.isoformat(),
        "end_time": deadline.isoformat(),
    }

    res = client.post("/api/v1/events", json=event_payload, headers=organizer_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Global Hackathon 2026"
    assert data["slug"] == "global-hack-2026"
    assert "2026-10-01" in data["start_time"]
    assert "2026-10-03" in data["end_time"]

    # Retrieve event by slug
    get_res = client.get("/api/v1/events/global-hack-2026")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == data["id"]


# ==============================================================================
# 3. TEAM CREATION & INVITE LINKS
# ==============================================================================

def test_team_creation_and_invites(client: TestClient, auth_tokens: Dict[str, str], test_db: Session):
    """Verify team creation, auto-lead assignment, invite generation, and token acceptance."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    lead_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Create event
    ev_res = client.post("/api/v1/events", json={
        "title": "Teaming Event",
        "slug": "teaming-event",
        "phase": "active",
    }, headers=organizer_headers)
    event_id = ev_res.json()["id"]

    # 2. Lead creates team
    team_res = client.post("/api/v1/teams", json={
        "event_id": event_id,
        "name": "Alpha Squad",
    }, headers=lead_headers)
    assert team_res.status_code == 201
    team_data = team_res.json()
    team_id = team_data["id"]
    assert len(team_data["members"]) == 1
    assert team_data["members"][0]["role"] == "lead"

    # 3. Lead creates invite for a collaborator
    invite_res = client.post(
        f"/api/v1/teams/{team_id}/invites",
        json={"invitee_email": "newdev@example.com"},
        headers=lead_headers,
    )
    assert invite_res.status_code == 201
    invite_data = invite_res.json()
    assert invite_data["status"] == "pending"
    token = invite_data["token"]
    assert invite_data["invite_url"] is not None
    assert token in invite_data["invite_url"]

    # 4. Create a second participant to accept the invite
    collaborator_res = client.post("/api/v1/auth/register", json={
        "username": "collaborator",
        "email": "newdev@example.com",
        "password": "collab_secret",
        "role": "participant",
    })
    assert collaborator_res.status_code == 200
    collab_token = collaborator_res.json()["access_token"]
    collab_headers = {"Authorization": f"Bearer {collab_token}"}

    # 5. Collaborator joins team with token
    join_res = client.post(f"/api/v1/teams/join?token={token}", headers=collab_headers)
    assert join_res.status_code == 200
    member_data = join_res.json()
    assert member_data["team_id"] == team_id
    assert member_data["role"] == "member"

    # 6. Attempting to reuse the same token raises 400
    reuse_res = client.post(f"/api/v1/teams/join?token={token}", headers=collab_headers)
    assert reuse_res.status_code == 400
    assert "already been accepted" in reuse_res.json()["detail"]


# ==============================================================================
# 4. PROJECT DRAFT & EDITING
# ==============================================================================

def test_draft_editing(client: TestClient, auth_tokens: Dict[str, str], test_db: Session):
    """Verify that drafts can be created and edited, and non-members cannot edit them."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    lead_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Setup event, track, team
    ev_res = client.post("/api/v1/events", json={
        "title": "Editing Test Event",
        "slug": "edit-event",
        "phase": "active",
    }, headers=organizer_headers)
    event_id = ev_res.json()["id"]

    tr_res = client.post(f"/api/v1/events/{event_id}/tracks", json={"title": "Systems Track"}, headers=organizer_headers)
    track_id = tr_res.json()["id"]

    team_res = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Builders"}, headers=lead_headers)
    team_id = team_res.json()["id"]

    # 2. Create Draft
    draft_res = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_id,
        "track_id": track_id,
        "title": "Draft Initial Version",
        "tagline": "Initial Tagline",
    }, headers=lead_headers)
    assert draft_res.status_code == 201
    project_id = draft_res.json()["id"]
    assert draft_res.json()["is_submitted"] is False
    assert draft_res.json()["submitted_at"] is None

    # 3. Update Draft
    update_payload = {
        "title": "Chameleon Platform V2",
        "tagline": "Adaptive Hackathon OS",
        "description": "Comprehensive self-hosted architecture.",
        "repository_url": "https://github.com/Aqua-357/ChameleonOS",
        "demo_url": "https://chameleon.local",
    }
    put_res = client.put(f"/api/v1/projects/{project_id}", json=update_payload, headers=lead_headers)
    assert put_res.status_code == 200
    updated_data = put_res.json()
    assert updated_data["title"] == "Chameleon Platform V2"
    assert updated_data["tagline"] == "Adaptive Hackathon OS"
    assert updated_data["repository_url"] == "https://github.com/Aqua-357/ChameleonOS"
    assert updated_data["is_submitted"] is False

    # 4. Another participant (not on team) cannot edit this draft
    other_user_res = client.post("/api/v1/auth/register", json={
        "username": "unauthorized_user",
        "email": "unauth@example.com",
        "password": "unauth_secret",
        "role": "participant",
    })
    other_headers = {"Authorization": f"Bearer {other_user_res.json()['access_token']}"}

    forbidden_res = client.put(f"/api/v1/projects/{project_id}", json={"title": "Hacked Title"}, headers=other_headers)
    assert forbidden_res.status_code == 403


# ==============================================================================
# 5. SUBMISSION DEADLINE ENFORCEMENT
# ==============================================================================

def test_closed_submission_deadline(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Verify strict deadline enforcement:
    - If deadline has passed (end_time < now_utc), participant CANNOT submit (400 Bad Request).
    - If event phase is 'closed', participant CANNOT submit (400 Bad Request).
    - If deadline is in future (end_time > now_utc) and phase is 'active', participant CAN submit.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # --------------------------------------------------------------------------
    # Scenario A: Past Deadline (Closed)
    # --------------------------------------------------------------------------
    past_deadline = datetime.now(timezone.utc) - timedelta(hours=2)
    ev_past = client.post("/api/v1/events", json={
        "title": "Expired Hackathon",
        "slug": "expired-hack",
        "phase": "active",
        "end_time": past_deadline.isoformat(),
    }, headers=organizer_headers)
    assert ev_past.status_code == 201
    past_event_id = ev_past.json()["id"]

    team_past = client.post("/api/v1/teams", json={
        "event_id": past_event_id,
        "name": "Late Submitter Team",
    }, headers=participant_headers)
    team_past_id = team_past.json()["id"]

    draft_past = client.post("/api/v1/projects", json={
        "event_id": past_event_id,
        "team_id": team_past_id,
        "title": "Late Project",
    }, headers=participant_headers)
    draft_past_id = draft_past.json()["id"]

    # Submission MUST fail because deadline has passed
    submit_fail_res = client.post(f"/api/v1/projects/{draft_past_id}/submit", headers=participant_headers)
    assert submit_fail_res.status_code == 400
    assert "deadline" in submit_fail_res.json()["detail"].lower() and "passed" in submit_fail_res.json()["detail"].lower()

    # --------------------------------------------------------------------------
    # Scenario B: Phase Closed
    # --------------------------------------------------------------------------
    future_deadline = datetime.now(timezone.utc) + timedelta(days=5)
    ev_closed = client.post("/api/v1/events", json={
        "title": "Phase Closed Hackathon",
        "slug": "phase-closed-hack",
        "phase": "closed",
        "end_time": future_deadline.isoformat(),
    }, headers=organizer_headers)
    closed_event_id = ev_closed.json()["id"]

    team_closed = client.post("/api/v1/teams", json={
        "event_id": closed_event_id,
        "name": "Closed Phase Team",
    }, headers=participant_headers)
    team_closed_id = team_closed.json()["id"]

    draft_closed = client.post("/api/v1/projects", json={
        "event_id": closed_event_id,
        "team_id": team_closed_id,
        "title": "Closed Phase Project",
    }, headers=participant_headers)
    draft_closed_id = draft_closed.json()["id"]

    # Submission MUST fail because event phase is 'closed'
    submit_closed_res = client.post(f"/api/v1/projects/{draft_closed_id}/submit", headers=participant_headers)
    assert submit_closed_res.status_code == 400
    assert "closed" in submit_closed_res.json()["detail"].lower() and "submissions" in submit_closed_res.json()["detail"].lower()

    # --------------------------------------------------------------------------
    # Scenario C: Active Event With Future Deadline (Submission Succeeds)
    # --------------------------------------------------------------------------
    ev_open = client.post("/api/v1/events", json={
        "title": "Open Hackathon",
        "slug": "open-hack",
        "phase": "active",
        "end_time": future_deadline.isoformat(),
    }, headers=organizer_headers)
    open_event_id = ev_open.json()["id"]

    team_open = client.post("/api/v1/teams", json={
        "event_id": open_event_id,
        "name": "On Time Team",
    }, headers=participant_headers)
    team_open_id = team_open.json()["id"]

    draft_open = client.post("/api/v1/projects", json={
        "event_id": open_event_id,
        "team_id": team_open_id,
        "title": "On Time Project",
    }, headers=participant_headers)
    draft_open_id = draft_open.json()["id"]

    # Submission MUST succeed
    submit_success_res = client.post(f"/api/v1/projects/{draft_open_id}/submit", headers=participant_headers)
    assert submit_success_res.status_code == 200
    submitted_project = submit_success_res.json()
    assert submitted_project["is_submitted"] is True
    assert submitted_project["submitted_at"] is not None


# ==============================================================================
# 6. PUBLIC GALLERY WITHOUT AUTHENTICATION
# ==============================================================================

def test_public_gallery_unauthenticated(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify that visitor can access public gallery without credentials."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # Create event and submit a project
    future_deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev_res = client.post("/api/v1/events", json={
        "title": "Public Showcase Hack",
        "slug": "public-showcase",
        "phase": "active",
        "end_time": future_deadline.isoformat(),
    }, headers=organizer_headers)
    event_id = ev_res.json()["id"]

    team_res = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Showcase Team"}, headers=participant_headers)
    team_id = team_res.json()["id"]

    draft_res = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_id,
        "title": "Showcase Artifact",
        "tagline": "Open to everyone",
    }, headers=participant_headers)
    proj_id = draft_res.json()["id"]

    # Before submitting, public gallery MUST NOT show draft
    visitor_res = client.get("/api/v1/projects")
    assert visitor_res.status_code == 200
    project_ids = [p["id"] for p in visitor_res.json()]
    assert proj_id not in project_ids

    # Submit project
    client.post(f"/api/v1/projects/{proj_id}/submit", headers=participant_headers)

    # Now visitor accesses JSON API endpoint WITHOUT Authorization header
    visitor_api_res = client.get("/api/v1/projects")
    assert visitor_api_res.status_code == 200
    submitted_ids = [p["id"] for p in visitor_api_res.json()]
    assert proj_id in submitted_ids

    # Visitor accesses HTML Gallery page WITHOUT cookies or headers
    visitor_html_res = client.get("/gallery")
    assert visitor_html_res.status_code == 200
    assert "Showcase Artifact" in visitor_html_res.text


# ==============================================================================
# 7. SEARCH & FILTERING
# ==============================================================================

def test_gallery_search_and_filter(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify keyword search (title, tagline, team) and track filtering."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Create Event with two tracks
    future_deadline = datetime.now(timezone.utc) + timedelta(days=3)
    ev_res = client.post("/api/v1/events", json={
        "title": "Search & Filter Hackathon",
        "slug": "search-filter-hack",
        "phase": "active",
        "end_time": future_deadline.isoformat(),
    }, headers=organizer_headers)
    event_id = ev_res.json()["id"]

    ai_track = client.post(f"/api/v1/events/{event_id}/tracks", json={"title": "AI/ML Track"}, headers=organizer_headers).json()
    web3_track = client.post(f"/api/v1/events/{event_id}/tracks", json={"title": "Web3 Track"}, headers=organizer_headers).json()

    # 2. Project A (AI Track)
    team_a = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Cortex Core"}, headers=participant_headers).json()
    proj_a = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_a["id"],
        "track_id": ai_track["id"],
        "title": "NeuroGraph Neural Search",
        "tagline": "Semantic neural graph engine",
    }, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj_a['id']}/submit", headers=participant_headers)

    # 3. Project B (Web3 Track)
    team_b = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Cipher Collective"}, headers=participant_headers).json()
    proj_b = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_b["id"],
        "track_id": web3_track["id"],
        "title": "ZeroVault Privacy",
        "tagline": "Zero knowledge cryptographic escrow",
    }, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj_b['id']}/submit", headers=participant_headers)

    # 4. Search by title keyword
    res_search_title = client.get("/api/v1/projects?search=NeuroGraph")
    assert res_search_title.status_code == 200
    results = res_search_title.json()
    assert len(results) == 1
    assert results[0]["id"] == proj_a["id"]

    # 5. Search by tagline keyword
    res_search_tagline = client.get("/api/v1/projects?search=cryptographic")
    assert res_search_tagline.status_code == 200
    results = res_search_tagline.json()
    assert len(results) == 1
    assert results[0]["id"] == proj_b["id"]

    # 6. Search by team name
    res_search_team = client.get("/api/v1/projects?search=Cipher")
    assert res_search_team.status_code == 200
    results = res_search_team.json()
    assert len(results) == 1
    assert results[0]["id"] == proj_b["id"]

    # 7. Filter by Track ID
    res_filter_track = client.get(f"/api/v1/projects?track_id={ai_track['id']}")
    assert res_filter_track.status_code == 200
    results = res_filter_track.json()
    assert len(results) == 1
    assert results[0]["id"] == proj_a["id"]

    # 8. Filter by Track ID returning other project
    res_filter_track_b = client.get(f"/api/v1/projects?track_id={web3_track['id']}")
    assert res_filter_track_b.status_code == 200
    results = res_filter_track_b.json()
    assert len(results) == 1
    assert results[0]["id"] == proj_b["id"]

    # 9. Non-matching search returns empty list
    res_empty = client.get("/api/v1/projects?search=NonExistentProject12345")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0


# ==============================================================================
# 8. HTML VIEWS & SESSION COOKIES
# ==============================================================================

def test_html_views_and_session(client: TestClient):
    """Verify HTML login form setting session cookie and redirecting to root."""
    # 1. Login via HTML form
    login_res = client.post("/login", data={
        "username_or_email": "participant",
        "password": "participant_pass_2026",
    }, follow_redirects=False)
    assert login_res.status_code == 302
    assert SESSION_COOKIE_NAME in client.cookies

    # 2. Access root page with persisted session cookie
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "participant" in root_res.text

    # 3. Logout clears cookie
    logout_res = client.get("/logout", follow_redirects=False)
    assert logout_res.status_code == 302
