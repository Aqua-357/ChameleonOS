"""Official DOGFOOD 2026 Acceptance Test Suite.

Loads and executes checks defined in .dogfood.toml:
1. public gallery (unauthenticated access)
2. fixture visibility (fixture projects in public gallery)
3. closed submission (deadline enforcement)
4. judge own scores (judge can read own score records)
5. judge peer-score denial (judge forbidden from reading peer scores)
6. participant judge-score denial (participant forbidden from judging endpoints)
7. organizer CSV export (organizer can export CSV results, non-organizers denied)
"""

import csv
import io
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
import pytest
import tomllib

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from src.main import app
from src.database import SessionLocal
from src.auth.service import seed_users


BASE_DIR = Path(__file__).resolve().parent.parent
TOML_PATH = BASE_DIR / ".dogfood.toml"


def load_dogfood_config() -> Dict[str, Any]:
    """Parse .dogfood.toml configuration."""
    assert TOML_PATH.exists(), f"Configuration file {TOML_PATH} must exist."
    with open(TOML_PATH, "rb") as f:
        return tomllib.load(f)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_tokens(client):
    with SessionLocal() as db:
        seed_data = seed_users(db)
        return {
            username: data["token"]
            for username, data in seed_data.items()
        }


# ==============================================================================
# Configuration Integrity Check
# ==============================================================================

def test_dogfood_toml_structure():
    """Verify .dogfood.toml exists and defines all seven required checks."""
    config = load_dogfood_config()
    assert "suite" in config
    assert "checks" in config
    checks = {c["id"]: c for c in config["checks"]}

    required_check_ids = [
        "public_gallery",
        "fixture_visibility",
        "closed_submission",
        "judge_own_scores",
        "judge_peer_score_denial",
        "participant_judge_score_denial",
        "organizer_csv_export",
    ]
    for req_id in required_check_ids:
        assert req_id in checks, f"Check '{req_id}' must be configured in .dogfood.toml"


# ==============================================================================
# CHECK 1: Public Gallery
# ==============================================================================

def test_check_1_public_gallery(client):
    """
    Check 1: public gallery
    Verify public gallery is accessible without any authentication cookies or bearer tokens.
    """
    # 1. HTML page unauthenticated
    resp_html = client.get("/gallery")
    assert resp_html.status_code == 200
    assert "Project Gallery" in resp_html.text

    # 2. Public API endpoint unauthenticated
    resp_api = client.get("/api/v1/projects")
    assert resp_api.status_code == 200
    projects = resp_api.json()
    assert isinstance(projects, list)


# ==============================================================================
# CHECK 2: Fixture Visibility
# ==============================================================================

def test_check_2_fixture_visibility(client):
    """
    Check 2: fixture visibility
    Verify fixture projects loaded from fixtures.json are visible in the public gallery.
    """
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 1, "At least one fixture project must be visible in public projects."

    fixture_ids = [p["id"] for p in projects]
    assert "prj_dogfood_agent" in fixture_ids or any("agent" in p["title"].lower() for p in projects), (
        "Fixture project must be present and visible in public gallery."
    )


# ==============================================================================
# CHECK 3: Closed Submission
# ==============================================================================

def test_check_3_closed_submission(client, auth_tokens):
    """
    Check 3: closed submission
    Verify a participant cannot submit after configured deadline or when event is closed.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    uid = uuid.uuid4().hex[:8]
    # Create an event whose deadline expired yesterday
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    ev_resp = client.post("/api/v1/events", json={
        "title": f"Expired Hackathon {uid}",
        "slug": f"expired-hack-{uid}",
        "phase": "active",
        "end_time": yesterday.isoformat(),
    }, headers=organizer_headers)
    assert ev_resp.status_code == 201
    event_id = ev_resp.json()["id"]

    # Create team for participant
    team_resp = client.post("/api/v1/teams", json={
        "event_id": event_id,
        "name": f"Late Team {uid}",
    }, headers=participant_headers)
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    # Create draft
    draft_resp = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_id,
        "title": f"Late Project Attempt {uid}",
    }, headers=participant_headers)
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Attempt to submit draft to closed event -> Must fail with HTTP 400
    sub_resp = client.post(f"/api/v1/projects/{draft_id}/submit", headers=participant_headers)
    assert sub_resp.status_code == 400, "Submitting to an event past deadline must return HTTP 400."
    detail = sub_resp.json()["detail"].lower()
    assert "deadline" in detail or "closed" in detail


# ==============================================================================
# CHECK 4: Judge Own Scores
# ==============================================================================

def test_check_4_judge_own_scores(client, auth_tokens):
    """
    Check 4: judge own scores
    Verify a judge can access and submit their own score records for assigned projects.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    uid = uuid.uuid4().hex[:8]
    # Setup active event, team, project, rubric
    ev_resp = client.post("/api/v1/events", json={
        "title": f"Judge Own Score Event {uid}",
        "slug": f"judge-own-evt-{uid}",
        "phase": "active",
    }, headers=organizer_headers)
    assert ev_resp.status_code == 201
    event_id = ev_resp.json()["id"]

    team_resp = client.post("/api/v1/teams", json={
        "event_id": event_id,
        "name": f"Scoring Team {uid}",
    }, headers=participant_headers)
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    proj_resp = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_id,
        "title": f"Scorable Innovation {uid}",
    }, headers=participant_headers)
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # Submit project draft
    client.post(f"/api/v1/projects/{project_id}/submit", headers=participant_headers)

    # Assign judge_a
    assign_res = client.post("/api/v1/judging/assignments", json={
        "event_id": event_id,
        "judge_id": "usr_judge_a",
        "project_id": project_id,
    }, headers=organizer_headers)
    assert assign_res.status_code == 201

    rubric_resp = client.get(f"/api/v1/judging/events/{event_id}/rubric", headers=organizer_headers)
    criterion_id = rubric_resp.json()["criteria"][0]["id"]

    # Judge submits own scores
    score_resp = client.post(f"/api/v1/judging/projects/{project_id}/scores", json={
        "scores": [{"criterion_id": criterion_id, "score": 9.0}],
        "general_feedback": "Outstanding prototype",
    }, headers=judge_a_headers)
    assert score_resp.status_code == 200

    # Judge reads own scores
    get_scores = client.get(f"/api/v1/judging/projects/{project_id}/scores", headers=judge_a_headers)
    assert get_scores.status_code == 200
    scores_data = get_scores.json()
    assert len(scores_data) >= 1
    assert scores_data[0]["judge_id"] == "usr_judge_a"
    assert scores_data[0]["score"] == 9.0


# ==============================================================================
# CHECK 5: Judge Peer-Score Denial
# ==============================================================================

def test_check_5_judge_peer_score_denial(client, auth_tokens):
    """
    Check 5: judge peer-score denial
    A judge must never retrieve another judge's scores,
    even when the other judge ID is manually supplied to the API.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    judge_b_headers = {"Authorization": f"Bearer {auth_tokens['judge_b']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    uid = uuid.uuid4().hex[:8]
    # Setup event & project
    ev_resp = client.post("/api/v1/events", json={
        "title": f"Peer Isolation Event {uid}",
        "slug": f"peer-iso-{uid}",
        "phase": "active",
    }, headers=organizer_headers)
    assert ev_resp.status_code == 201
    event_id = ev_resp.json()["id"]

    team_resp = client.post("/api/v1/teams", json={
        "event_id": event_id,
        "name": f"Peer Team {uid}",
    }, headers=participant_headers)
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    proj_resp = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_id,
        "title": f"Peer Isolation Target {uid}",
    }, headers=participant_headers)
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # Submit project
    client.post(f"/api/v1/projects/{project_id}/submit", headers=participant_headers)

    # Assign only judge_b
    assign_b = client.post("/api/v1/judging/assignments", json={
        "event_id": event_id,
        "judge_id": "usr_judge_b",
        "project_id": project_id,
    }, headers=organizer_headers)
    assert assign_b.status_code == 201

    rubric_resp = client.get(f"/api/v1/judging/events/{event_id}/rubric", headers=organizer_headers)
    criterion_id = rubric_resp.json()["criteria"][0]["id"]

    # judge_b scores project
    score_b_res = client.post(f"/api/v1/judging/projects/{project_id}/scores", json={
        "scores": [{"criterion_id": criterion_id, "score": 8.0}],
        "general_feedback": "Secret Judge B notes",
    }, headers=judge_b_headers)
    assert score_b_res.status_code == 200
    judge_b_score_id = score_b_res.json()[0]["id"]

    # 1. judge_a attempts to submit scores on project assigned only to judge_b -> 403 Forbidden
    unassigned_post = client.post(f"/api/v1/judging/projects/{project_id}/scores", json={
        "scores": [{"criterion_id": criterion_id, "score": 7.0}]
    }, headers=judge_a_headers)
    assert unassigned_post.status_code == 403

    # 2. judge_a attempts to retrieve judge_b's single score record by score_id -> 403 Forbidden
    score_id_res = client.get(f"/api/v1/judging/scores/{judge_b_score_id}", headers=judge_a_headers)
    assert score_id_res.status_code == 403, "Judge requesting peer score record by ID must return HTTP 403."

    # 3. judge_a queries project scores manually specifying judge_id=usr_judge_b -> 403 Forbidden
    snoop_res = client.get(
        f"/api/v1/judging/projects/{project_id}/scores?judge_id=usr_judge_b",
        headers=judge_a_headers,
    )
    assert snoop_res.status_code == 403, "Judge requesting peer scores via query parameter must return HTTP 403."


# ==============================================================================
# CHECK 6: Participant Judge-Score Denial
# ==============================================================================

def test_check_6_participant_judge_score_denial(client, auth_tokens):
    """
    Check 6: participant judge-score denial
    A participant must not access judge endpoints under any circumstances.
    """
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Judge queue
    q_res = client.get("/api/v1/judging/queue", headers=participant_headers)
    assert q_res.status_code == 403

    # 2. Judge scores
    s_res = client.get("/api/v1/judging/projects/prj_dogfood_agent/scores", headers=participant_headers)
    assert s_res.status_code == 403

    # 3. Judge score post
    p_res = client.post("/api/v1/judging/projects/prj_dogfood_agent/scores", json={"scores": []}, headers=participant_headers)
    assert p_res.status_code == 403

    # 4. Results calculation
    r_res = client.get("/api/v1/judging/events/evt_dogfood_2026/results", headers=participant_headers)
    assert r_res.status_code == 403

    # 5. Normalization lab API
    n_res = client.get("/api/v1/normalization/events/evt_dogfood_2026", headers=participant_headers)
    assert n_res.status_code == 403


# ==============================================================================
# CHECK 7: Organizer CSV Export
# ==============================================================================

def test_check_7_organizer_csv_export(client, auth_tokens):
    """
    Check 7: organizer CSV export
    An organizer can access aggregate results and CSV export.
    Non-organizers are denied. CSV output format is strictly valid.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}

    event_id = "evt_dogfood_2026"

    # 1. Participant is denied CSV export -> 403
    p_res = client.get(f"/api/v1/judging/events/{event_id}/export.csv", headers=participant_headers)
    assert p_res.status_code == 403

    # 2. Judge is denied CSV export -> 403
    j_res = client.get(f"/api/v1/judging/events/{event_id}/export.csv", headers=judge_headers)
    assert j_res.status_code == 403

    # 3. Organizer successfully exports CSV -> 200
    org_res = client.get(f"/api/v1/judging/events/{event_id}/export.csv", headers=organizer_headers)
    assert org_res.status_code == 200
    assert "text/csv" in org_res.headers.get("content-type", "")

    # Parse and validate CSV data structure
    csv_text = org_res.text
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) >= 2, "CSV export must contain header row and at least one project row."

    header = rows[0]
    required_cols = ["Rank", "Project Title", "Team Name", "Track", "Final Weighted Score"]
    for col in required_cols:
        assert col in header, f"CSV header must contain '{col}'"

    # Verify first row rank is 1
    first_data_row = rows[1]
    rank_idx = header.index("Rank")
    assert first_data_row[rank_idx] in ["1", "1.0", "1st"]


# ==============================================================================
# Standalone Runner
# ==============================================================================

def run_all_checks_standalone():
    """Execute all seven acceptance checks programmatically and report results."""
    print("=" * 80)
    print("RUNNING OFFICIAL DOGFOOD ACCEPTANCE SUITE (.dogfood.toml)")
    print("=" * 80)

    cfg = load_dogfood_config()
    print(f"Suite: {cfg['suite']['name']} (Version: {cfg['suite']['version']})")
    print(f"Target: {cfg['suite']['target_url']} | Offline Mode: {cfg['suite']['offline_mode']}")
    print("-" * 80)

    test_client = TestClient(app)
    with SessionLocal() as db:
        seed_data = seed_users(db)
        tokens = {u: d["token"] for u, d in seed_data.items()}

    checks = [
        ("Check 1: public gallery", lambda: test_check_1_public_gallery(test_client)),
        ("Check 2: fixture visibility", lambda: test_check_2_fixture_visibility(test_client)),
        ("Check 3: closed submission", lambda: test_check_3_closed_submission(test_client, tokens)),
        ("Check 4: judge own scores", lambda: test_check_4_judge_own_scores(test_client, tokens)),
        ("Check 5: judge peer-score denial", lambda: test_check_5_judge_peer_score_denial(test_client, tokens)),
        ("Check 6: participant judge-score denial", lambda: test_check_6_participant_judge_score_denial(test_client, tokens)),
        ("Check 7: organizer CSV export", lambda: test_check_7_organizer_csv_export(test_client, tokens)),
    ]

    passed = 0
    for name, check_fn in checks:
        try:
            check_fn()
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            raise

    print("=" * 80)
    print(f"DOGFOOD ACCEPTANCE SUITE RESULT: {passed}/{len(checks)} CHECKS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    run_all_checks_standalone()
