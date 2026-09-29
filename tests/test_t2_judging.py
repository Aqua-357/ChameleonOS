"""Comprehensive Milestone T2 Judging & Security Tests for ChameleonOS.

Tests cover:
1. Judge invitation & assignment
2. Weighted rubric configuration
3. Judge dashboard & project queue
4. Score submission & feedback comments
5. Judging progress tracking
6. Organizer results calculation & ranking
7. CSV export format
8. CRITICAL SECURITY BOUNDARIES:
   - Judge can only access projects assigned to that judge
   - Judge may read only their own score records
   - Judge must never retrieve another judge's scores, even when other judge ID is manually supplied
   - Participant must not access judge endpoints
   - Organizer can access aggregate results, CSV export, and audit records
   - Judges and participants cannot access aggregate results or audit records
"""

from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.auth.models import User
from src.judging.models import JudgeAssignment, JudgeScore


# ==============================================================================
# TEST FIXTURE HELPER
# ==============================================================================

def setup_judging_environment(client: TestClient, auth_tokens: Dict[str, str]):
    """Helper to set up an event with 2 submitted projects and custom rubric."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Create Event
    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev_res = client.post("/api/v1/events", json={
        "title": "Judging Arena 2026",
        "slug": "judging-arena-2026",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers)
    assert ev_res.status_code == 201
    event_id = ev_res.json()["id"]

    # 2. Configure Weighted Rubric
    # Criterion 1: Weight 3.0
    # Criterion 2: Weight 1.0
    rubric_res = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Weighted Excellence Rubric",
        "criteria": [
            {"name": "Innovation & Architecture", "weight": 3.0, "min_score": 1.0, "max_score": 10.0, "order_index": 1},
            {"name": "Visual Execution", "weight": 1.0, "min_score": 1.0, "max_score": 10.0, "order_index": 2},
        ],
    }, headers=organizer_headers)
    assert rubric_res.status_code == 200
    rubric_data = rubric_res.json()
    crit_1_id = rubric_data["criteria"][0]["id"]
    crit_2_id = rubric_data["criteria"][1]["id"]

    # 3. Create Teams and Submit 2 Projects
    team_1 = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Nova"}, headers=participant_headers).json()
    proj_1 = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_1["id"],
        "title": "Nova Engine",
        "tagline": "Next-gen distributed runtime",
    }, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj_1['id']}/submit", headers=participant_headers)

    team_2 = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Solar"}, headers=participant_headers).json()
    proj_2 = client.post("/api/v1/projects", json={
        "event_id": event_id,
        "team_id": team_2["id"],
        "title": "Solar Grid",
        "tagline": "Decentralized energy micro-grid",
    }, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj_2['id']}/submit", headers=participant_headers)

    # 4. Resolve judge user IDs
    judge_a_user = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {auth_tokens['judge_a']}"}).json()
    judge_b_user = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {auth_tokens['judge_b']}"}).json()

    return {
        "event_id": event_id,
        "event_slug": "judging-arena-2026",
        "crit_1_id": crit_1_id,
        "crit_2_id": crit_2_id,
        "proj_1_id": proj_1["id"],
        "proj_2_id": proj_2["id"],
        "judge_a_id": judge_a_user["id"],
        "judge_b_id": judge_b_user["id"],
    }


# ==============================================================================
# 1. JUDGE INVITATION & ASSIGNMENT
# ==============================================================================

def test_judge_invitation_and_assignment(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify organizer can invite judges and assign them to submitted projects."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    env = setup_judging_environment(client, auth_tokens)

    # Invite a new judge
    inv_res = client.post("/api/v1/judging/invites", json={
        "event_id": env["event_id"],
        "email": "specialist_judge@chameleon.local",
        "username": "specialist_judge",
    }, headers=organizer_headers)
    assert inv_res.status_code == 200
    assert inv_res.json()["role"] == "judge"

    # Assign Judge A to Project 1
    assign_res = client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)
    assert assign_res.status_code == 201
    assert assign_res.json()["status"] == "assigned"


# ==============================================================================
# 2. CRITICAL SECURITY: A JUDGE CAN ONLY ACCESS PROJECTS ASSIGNED TO THAT JUDGE
# ==============================================================================

def test_judge_can_only_access_assigned_projects(client: TestClient, auth_tokens: Dict[str, str]):
    """
    CRITICAL SECURITY TEST:
    Judge A is assigned ONLY to Project 1.
    Judge B is assigned ONLY to Project 2.
    - Judge A accessing Project 1 -> 200 OK.
    - Judge A accessing Project 2 -> 403 Forbidden.
    - Judge B accessing Project 2 -> 200 OK.
    - Judge B accessing Project 1 -> 403 Forbidden.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    judge_b_headers = {"Authorization": f"Bearer {auth_tokens['judge_b']}"}
    env = setup_judging_environment(client, auth_tokens)

    # Assign Judge A -> Project 1 ONLY
    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)

    # Assign Judge B -> Project 2 ONLY
    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_b_id"],
        "project_id": env["proj_2_id"],
    }, headers=organizer_headers)

    # 1. Judge A accesses assigned Project 1 -> 200 OK
    res_a_proj1 = client.get(f"/api/v1/judging/projects/{env['proj_1_id']}", headers=judge_a_headers)
    assert res_a_proj1.status_code == 200
    assert res_a_proj1.json()["project"]["id"] == env["proj_1_id"]

    # 2. Judge A attempts to access UNASSIGNED Project 2 -> 403 FORBIDDEN
    res_a_proj2 = client.get(f"/api/v1/judging/projects/{env['proj_2_id']}", headers=judge_a_headers)
    assert res_a_proj2.status_code == 403
    assert "not assigned" in res_a_proj2.json()["detail"].lower()

    # 3. Judge A attempts to access UNASSIGNED Project 2 via HTML -> 403 FORBIDDEN
    res_a_proj2_html = client.get(f"/judging/projects/{env['proj_2_id']}", headers=judge_a_headers)
    assert res_a_proj2_html.status_code == 403

    # 4. Judge B accesses assigned Project 2 -> 200 OK
    res_b_proj2 = client.get(f"/api/v1/judging/projects/{env['proj_2_id']}", headers=judge_b_headers)
    assert res_b_proj2.status_code == 200

    # 5. Judge B attempts to access UNASSIGNED Project 1 -> 403 FORBIDDEN
    res_b_proj1 = client.get(f"/api/v1/judging/projects/{env['proj_1_id']}", headers=judge_b_headers)
    assert res_b_proj1.status_code == 403
    assert "not assigned" in res_b_proj1.json()["detail"].lower()

    # 6. Judge A attempts to submit score to UNASSIGNED Project 2 -> 403 FORBIDDEN
    unauth_score = client.post(f"/api/v1/judging/projects/{env['proj_2_id']}/scores", json={
        "scores": [{"criterion_id": env["crit_1_id"], "score": 9.0}],
    }, headers=judge_a_headers)
    assert unauth_score.status_code == 403
    assert "not assigned" in unauth_score.json()["detail"].lower()


# ==============================================================================
# 3. CRITICAL SECURITY: SCORE RETRIEVAL ISOLATION & PROHIBITING OTHER JUDGE SCORES
# ==============================================================================

def test_judge_score_isolation_and_no_leakage(client: TestClient, auth_tokens: Dict[str, str]):
    """
    CRITICAL SECURITY TEST:
    Both Judge A and Judge B are assigned to Project 1 and each submit scores.
    - Judge A can only retrieve Judge A's own scores.
    - Judge A must NEVER retrieve Judge B's scores.
    - When Judge A manually passes judge_id=judge_b_id to the query, 403 Forbidden is returned.
    - When Judge A requests Judge B's score by ID, 403 Forbidden is returned.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    judge_b_headers = {"Authorization": f"Bearer {auth_tokens['judge_b']}"}
    env = setup_judging_environment(client, auth_tokens)

    # Assign both judges to Project 1
    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)

    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_b_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)

    # Judge A submits scores: 9.0 on crit_1, 8.0 on crit_2
    score_a_res = client.post(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", json={
        "scores": [
            {"criterion_id": env["crit_1_id"], "score": 9.0, "feedback": "Judge A feedback on innovation"},
            {"criterion_id": env["crit_2_id"], "score": 8.0, "feedback": "Judge A feedback on design"},
        ],
        "general_feedback": "Judge A overall feedback",
    }, headers=judge_a_headers)
    assert score_a_res.status_code == 200
    judge_a_score_id = score_a_res.json()[0]["id"]

    # Judge B submits scores: 6.0 on crit_1, 5.0 on crit_2
    score_b_res = client.post(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", json={
        "scores": [
            {"criterion_id": env["crit_1_id"], "score": 6.0, "feedback": "Judge B feedback on innovation"},
            {"criterion_id": env["crit_2_id"], "score": 5.0, "feedback": "Judge B feedback on design"},
        ],
        "general_feedback": "Judge B overall feedback",
    }, headers=judge_b_headers)
    assert score_b_res.status_code == 200
    judge_b_score_id = score_b_res.json()[0]["id"]

    # 1. Judge A requests scores for Project 1 -> Must contain ONLY Judge A's scores
    res_a_scores = client.get(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", headers=judge_a_headers)
    assert res_a_scores.status_code == 200
    scores_list_a = res_a_scores.json()
    assert len(scores_list_a) == 2
    for s in scores_list_a:
        assert s["judge_id"] == env["judge_a_id"]
        assert s["judge_id"] != env["judge_b_id"]

    # 2. Judge B requests scores for Project 1 -> Must contain ONLY Judge B's scores
    res_b_scores = client.get(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", headers=judge_b_headers)
    assert res_b_scores.status_code == 200
    scores_list_b = res_b_scores.json()
    assert len(scores_list_b) == 2
    for s in scores_list_b:
        assert s["judge_id"] == env["judge_b_id"]
        assert s["judge_id"] != env["judge_a_id"]

    # 3. Judge A manually supplies judge_id=judge_b_id in query parameter -> MUST BE REJECTED WITH 403
    leak_attempt = client.get(
        f"/api/v1/judging/projects/{env['proj_1_id']}/scores?judge_id={env['judge_b_id']}",
        headers=judge_a_headers,
    )
    assert leak_attempt.status_code == 403
    assert "strictly prohibited" in leak_attempt.json()["detail"].lower()

    # 4. Judge A attempts to read Judge B's individual score by ID -> MUST BE REJECTED WITH 403
    score_id_leak = client.get(f"/api/v1/judging/scores/{judge_b_score_id}", headers=judge_a_headers)
    assert score_id_leak.status_code == 403
    assert "only read your own" in score_id_leak.json()["detail"].lower()

    # 5. Judge A reading their own score by ID succeeds -> 200 OK
    score_a_own = client.get(f"/api/v1/judging/scores/{judge_a_score_id}", headers=judge_a_headers)
    assert score_a_own.status_code == 200
    assert score_a_own.json()["id"] == judge_a_score_id


# ==============================================================================
# 4. CRITICAL SECURITY: PARTICIPANT CANNOT ACCESS ANY JUDGE ENDPOINTS
# ==============================================================================

def test_participant_forbidden_from_all_judging_endpoints(client: TestClient, auth_tokens: Dict[str, str]):
    """
    CRITICAL SECURITY TEST:
    A participant must NOT access any judge endpoints.
    Every single judging route must return 403 Forbidden for participants.
    """
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}
    env = setup_judging_environment(client, auth_tokens)

    # 1. Queue endpoint
    assert client.get("/api/v1/judging/queue", headers=participant_headers).status_code == 403

    # 2. Project judging detail endpoint
    assert client.get(f"/api/v1/judging/projects/{env['proj_1_id']}", headers=participant_headers).status_code == 403

    # 3. Score submission endpoint
    assert client.post(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", json={
        "scores": [{"criterion_id": env["crit_1_id"], "score": 10.0}]
    }, headers=participant_headers).status_code == 403

    # 4. Scores read endpoint
    assert client.get(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", headers=participant_headers).status_code == 403

    # 5. Results endpoint
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/results", headers=participant_headers).status_code == 403

    # 6. Progress endpoint
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/progress", headers=participant_headers).status_code == 403

    # 7. CSV Export endpoint
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/export.csv", headers=participant_headers).status_code == 403

    # 8. Audit logs endpoint
    assert client.get("/api/v1/audit", headers=participant_headers).status_code == 403

    # 9. HTML Judge Dashboard
    assert client.get("/judging", headers=participant_headers).status_code == 403

    # 10. HTML Project Evaluation View
    assert client.get(f"/judging/projects/{env['proj_1_id']}", headers=participant_headers).status_code == 403

    # 11. HTML Results View
    assert client.get(f"/events/{env['event_slug']}/results", headers=participant_headers).status_code == 403


# ==============================================================================
# 5. CRITICAL SECURITY: ORGANIZER OVERVIEW VS JUDGE RESTRICTIONS ON AGGREGATE DATA
# ==============================================================================

def test_organizer_vs_judge_aggregate_results_and_audit(client: TestClient, auth_tokens: Dict[str, str]):
    """
    CRITICAL SECURITY TEST:
    - An organizer can access aggregate results, CSV export, and audit records.
    - A judge CANNOT access aggregate results, CSV export, or audit records.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    env = setup_judging_environment(client, auth_tokens)

    # 1. Aggregate results: Judge -> 403, Organizer -> 200
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/results", headers=judge_headers).status_code == 403
    res_org_results = client.get(f"/api/v1/judging/events/{env['event_id']}/results", headers=organizer_headers)
    assert res_org_results.status_code == 200

    # 2. CSV Export: Judge -> 403, Organizer -> 200
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/export.csv", headers=judge_headers).status_code == 403
    res_org_csv = client.get(f"/api/v1/judging/events/{env['event_id']}/export.csv", headers=organizer_headers)
    assert res_org_csv.status_code == 200
    assert "text/csv" in res_org_csv.headers["content-type"]

    # 3. Event Progress: Judge -> 403, Organizer -> 200
    assert client.get(f"/api/v1/judging/events/{env['event_id']}/progress", headers=judge_headers).status_code == 403
    res_org_progress = client.get(f"/api/v1/judging/events/{env['event_id']}/progress", headers=organizer_headers)
    assert res_org_progress.status_code == 200

    # 4. Audit Logs: Judge -> 403, Organizer -> 200
    assert client.get("/api/v1/audit", headers=judge_headers).status_code == 403
    res_org_audit = client.get("/api/v1/audit", headers=organizer_headers)
    assert res_org_audit.status_code == 200
    assert len(res_org_audit.json()) > 0  # Contains logged events from setup


# ==============================================================================
# 6. WEIGHTED RUBRIC CALCULATIONS, RESULTS & RANKINGS
# ==============================================================================

def test_weighted_rubric_calculations_and_rankings(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Verify weighted average calculations:
    Rubric:
      Criterion 1 weight = 3.0
      Criterion 2 weight = 1.0
      Total weight = 4.0

    Project 1 evaluated by Judge A:
      Crit 1 = 10.0, Crit 2 = 6.0
      Weighted score = (10*3 + 6*1) / 4 = 36 / 4 = 9.0

    Project 2 evaluated by Judge A:
      Crit 1 = 6.0, Crit 2 = 10.0
      Weighted score = (6*3 + 10*1) / 4 = 28 / 4 = 7.0

    Rank 1: Project 1 (score 9.0)
    Rank 2: Project 2 (score 7.0)
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    env = setup_judging_environment(client, auth_tokens)

    # Assign Judge A to both projects
    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)

    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_2_id"],
    }, headers=organizer_headers)

    # Judge A scores Project 1 -> (10*3 + 6*1)/4 = 9.0
    client.post(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", json={
        "scores": [
            {"criterion_id": env["crit_1_id"], "score": 10.0},
            {"criterion_id": env["crit_2_id"], "score": 6.0},
        ],
    }, headers=judge_a_headers)

    # Judge A scores Project 2 -> (6*3 + 10*1)/4 = 7.0
    client.post(f"/api/v1/judging/projects/{env['proj_2_id']}/scores", json={
        "scores": [
            {"criterion_id": env["crit_1_id"], "score": 6.0},
            {"criterion_id": env["crit_2_id"], "score": 10.0},
        ],
    }, headers=judge_a_headers)

    # Retrieve organizer results
    res = client.get(f"/api/v1/judging/events/{env['event_id']}/results", headers=organizer_headers)
    assert res.status_code == 200
    results_data = res.json()["results"]

    assert len(results_data) == 2
    # Project 1 must be Rank 1 with score 9.0
    assert results_data[0]["project_id"] == env["proj_1_id"]
    assert results_data[0]["rank"] == 1
    assert results_data[0]["weighted_score"] == 9.0
    assert results_data[0]["evaluations_count"] == 1

    # Project 2 must be Rank 2 with score 7.0
    assert results_data[1]["project_id"] == env["proj_2_id"]
    assert results_data[1]["rank"] == 2
    assert results_data[1]["weighted_score"] == 7.0
    assert results_data[1]["evaluations_count"] == 1


# ==============================================================================
# 7. CSV EXPORT INTEGRITY
# ==============================================================================

def test_csv_export_format(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify CSV export contains headers, rankings, project titles, and scores."""
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    env = setup_judging_environment(client, auth_tokens)

    # Assign and score Project 1
    client.post("/api/v1/judging/assignments", json={
        "event_id": env["event_id"],
        "judge_id": env["judge_a_id"],
        "project_id": env["proj_1_id"],
    }, headers=organizer_headers)

    client.post(f"/api/v1/judging/projects/{env['proj_1_id']}/scores", json={
        "scores": [
            {"criterion_id": env["crit_1_id"], "score": 8.0},
            {"criterion_id": env["crit_2_id"], "score": 8.0},
        ],
    }, headers=judge_a_headers)

    # Download CSV
    res = client.get(f"/api/v1/judging/events/{env['event_id']}/export.csv", headers=organizer_headers)
    assert res.status_code == 200
    csv_text = res.text

    assert "Rank" in csv_text
    assert "Project Title" in csv_text
    assert "Final Weighted Score" in csv_text
    assert "Nova Engine" in csv_text
    assert "8.00" in csv_text
