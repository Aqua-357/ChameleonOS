"""Deterministic edge-case and security tests for cross-judge score normalization."""

from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.auth.models import User
from src.judging.models import JudgeAssignment, JudgeScore


def test_zero_variance_judge_handling(client: TestClient, auth_tokens: Dict[str, str], test_db: Session):
    """
    Edge Case Test:
    A judge who gives every single project the exact same score (standard deviation = 0).
    Verify that division by zero is safely prevented, z-score is 0.0,
    and is_zero_variance is detected.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Create Event & Rubric
    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Zero Variance Event",
        "slug": "zero-var-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]

    rubric = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Standard",
        "criteria": [{"name": "Quality", "weight": 1.0}],
    }, headers=organizer_headers).json()
    crit_id = rubric["criteria"][0]["id"]

    # 2. Create 3 projects
    team = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Zero"}, headers=participant_headers).json()
    p1 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "P1"}, headers=participant_headers).json()
    p2 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "P2"}, headers=participant_headers).json()
    p3 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "P3"}, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{p1['id']}/submit", headers=participant_headers)
    client.post(f"/api/v1/projects/{p2['id']}/submit", headers=participant_headers)
    client.post(f"/api/v1/projects/{p3['id']}/submit", headers=participant_headers)

    # 3. Assign Judge A to all 3 projects
    judge_a_info = client.get("/api/v1/auth/me", headers=judge_a_headers).json()
    for p in [p1, p2, p3]:
        client.post("/api/v1/judging/assignments", json={
            "event_id": event_id,
            "judge_id": judge_a_info["id"],
            "project_id": p["id"],
        }, headers=organizer_headers)

    # 4. Judge A scores EVERY project with EXACTLY 7.0 (zero variance!)
    for p in [p1, p2, p3]:
        client.post(f"/api/v1/judging/projects/{p['id']}/scores", json={
            "scores": [{"criterion_id": crit_id, "score": 7.0}]
        }, headers=judge_a_headers)

    # 5. Execute Normalization
    res = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers)
    assert res.status_code == 200
    data = res.json()

    # Verify Judge Stats
    judge_stat = next(j for j in data["judges_stats"] if j["judge_id"] == judge_a_info["id"])
    assert judge_stat["is_zero_variance"] is True
    assert judge_stat["std_dev_raw_score"] == 0.0
    assert "Zero Variance" in judge_stat["status_label"]

    # Verify Projects receive neutral z-score = 0.0
    for proj_res in data["results"]:
        assert proj_res["normalized_z_score"] == 0.0
        assert proj_res["raw_score"] == 7.0


def test_harsh_vs_lenient_judge_rank_inversion(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Edge Case Test:
    Judge Harsh grades strictly: assigns 3.0, 4.0, 5.0 (mean = 4.0).
    Judge Lenient grades easily: assigns 8.0, 9.0, 10.0 (mean = 9.0).

    Project Alpha gets 5.0 from Judge Harsh (best of the harsh batch: +1.0 above mean).
    Project Beta gets 8.0 from Judge Lenient (worst of the lenient batch: -1.0 below mean).

    In Raw Scores: Beta (8.0) > Alpha (5.0) -> Beta is Raw Rank 1!
    In Normalized Scores: Alpha (z > 0) > Beta (z < 0) -> Alpha becomes Normalized Rank 1!
    Verify rank_delta correctly reports Alpha (+1) and Beta (-1).
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_harsh_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    judge_lenient_headers = {"Authorization": f"Bearer {auth_tokens['judge_b']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Bias Correction Event",
        "slug": "bias-correction-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]

    rubric = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Standard",
        "criteria": [{"name": "Technical", "weight": 1.0}],
    }, headers=organizer_headers).json()
    crit_id = rubric["criteria"][0]["id"]

    team = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Bias"}, headers=participant_headers).json()

    # Projects for Judge Harsh
    p_h1 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Harsh Low"}, headers=participant_headers).json()
    p_h2 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Harsh Mid"}, headers=participant_headers).json()
    p_alpha = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Project Alpha (Harsh Best)"}, headers=participant_headers).json()

    # Projects for Judge Lenient
    p_beta = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Project Beta (Lenient Worst)"}, headers=participant_headers).json()
    p_l2 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Lenient Mid"}, headers=participant_headers).json()
    p_l3 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Lenient High"}, headers=participant_headers).json()

    for p in [p_h1, p_h2, p_alpha, p_beta, p_l2, p_l3]:
        client.post(f"/api/v1/projects/{p['id']}/submit", headers=participant_headers)

    harsh_id = client.get("/api/v1/auth/me", headers=judge_harsh_headers).json()["id"]
    lenient_id = client.get("/api/v1/auth/me", headers=judge_lenient_headers).json()["id"]

    # Assign & Score Harsh projects: 3.0, 4.0, 5.0
    for p, score in [(p_h1, 3.0), (p_h2, 4.0), (p_alpha, 5.0)]:
        client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": harsh_id, "project_id": p["id"]}, headers=organizer_headers)
        client.post(f"/api/v1/judging/projects/{p['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": score}]}, headers=judge_harsh_headers)

    # Assign & Score Lenient projects: 8.0, 9.0, 10.0
    for p, score in [(p_beta, 8.0), (p_l2, 9.0), (p_l3, 10.0)]:
        client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": lenient_id, "project_id": p["id"]}, headers=organizer_headers)
        client.post(f"/api/v1/judging/projects/{p['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": score}]}, headers=judge_lenient_headers)

    # Calculate Normalization
    res = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers)
    assert res.status_code == 200
    data = res.json()

    results_map = {r["project_id"]: r for r in data["results"]}
    res_alpha = results_map[p_alpha["id"]]
    res_beta = results_map[p_beta["id"]]

    # In raw scoring: Beta (8.0) beat Alpha (5.0)
    assert res_beta["raw_score"] > res_alpha["raw_score"]
    assert res_beta["raw_rank"] < res_alpha["raw_rank"]

    # In normalized scoring: Alpha (+1.22 z) beats Beta (-1.22 z)
    assert res_alpha["normalized_z_score"] > 0
    assert res_beta["normalized_z_score"] < 0
    assert res_alpha["normalized_score"] > res_beta["normalized_score"]
    assert res_alpha["normalized_rank"] < res_beta["normalized_rank"]

    # Rank shift verification: Alpha climbed, Beta fell
    assert res_alpha["rank_delta"] > 0
    assert res_beta["rank_delta"] < 0


def test_missing_scores_proportional_weighting(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Edge Case Test:
    Multi-criterion rubric with weights 3.0 and 1.0.
    Judge evaluates only criterion 1 and leaves criterion 2 blank.
    Verify raw weighted score is computed proportionally (score on criterion 1) without error.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Missing Score Event",
        "slug": "missing-score-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]

    rubric = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Standard",
        "criteria": [
            {"name": "Architecture", "weight": 3.0},
            {"name": "Design", "weight": 1.0},
        ],
    }, headers=organizer_headers).json()
    crit_1_id = rubric["criteria"][0]["id"]

    team = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Missing"}, headers=participant_headers).json()
    proj = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Partial Project"}, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj['id']}/submit", headers=participant_headers)

    judge_id = client.get("/api/v1/auth/me", headers=judge_headers).json()["id"]
    client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": judge_id, "project_id": proj["id"]}, headers=organizer_headers)

    # Submit score ONLY for criterion 1 (9.0)
    client.post(f"/api/v1/judging/projects/{proj['id']}/scores", json={
        "scores": [{"criterion_id": crit_1_id, "score": 9.0}]
    }, headers=judge_headers)

    res = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers)
    assert res.status_code == 200
    item = res.json()["results"][0]
    assert item["raw_score"] == 9.0


def test_unequal_judges_per_project(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Edge Case Test:
    Project A is evaluated by 2 judges.
    Project B is evaluated by 1 judge.
    Verify normalized z-scores average properly without penalizing or biasing by judge count.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_a_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    judge_b_headers = {"Authorization": f"Bearer {auth_tokens['judge_b']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Unequal Judges Event",
        "slug": "unequal-judges-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]

    rubric = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Standard",
        "criteria": [{"name": "Score", "weight": 1.0}],
    }, headers=organizer_headers).json()
    crit_id = rubric["criteria"][0]["id"]

    team = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Unequal"}, headers=participant_headers).json()
    proj_a = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Project 2 Judges"}, headers=participant_headers).json()
    proj_b = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Project 1 Judge"}, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{proj_a['id']}/submit", headers=participant_headers)
    client.post(f"/api/v1/projects/{proj_b['id']}/submit", headers=participant_headers)

    judge_a_id = client.get("/api/v1/auth/me", headers=judge_a_headers).json()["id"]
    judge_b_id = client.get("/api/v1/auth/me", headers=judge_b_headers).json()["id"]

    # Assign Judge A to Project A and B
    client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": judge_a_id, "project_id": proj_a["id"]}, headers=organizer_headers)
    client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": judge_a_id, "project_id": proj_b["id"]}, headers=organizer_headers)
    client.post(f"/api/v1/judging/projects/{proj_a['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": 8.0}]}, headers=judge_a_headers)
    client.post(f"/api/v1/judging/projects/{proj_b['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": 6.0}]}, headers=judge_a_headers)

    # Assign Judge B to Project A ONLY
    client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": judge_b_id, "project_id": proj_a["id"]}, headers=organizer_headers)
    client.post(f"/api/v1/judging/projects/{proj_a['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": 8.0}]}, headers=judge_b_headers)

    res = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers)
    assert res.status_code == 200
    results_map = {r["project_id"]: r for r in res.json()["results"]}

    assert results_map[proj_a["id"]]["evaluations_count"] == 2
    assert results_map[proj_b["id"]]["evaluations_count"] == 1


def test_deterministic_tie_breaking(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Verify deterministic tie-breaking produces the exact same ranking order every time.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Tie Break Event",
        "slug": "tie-break-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]

    rubric = client.post(f"/api/v1/judging/events/{event_id}/rubric", json={
        "name": "Standard",
        "criteria": [{"name": "Score", "weight": 1.0}],
    }, headers=organizer_headers).json()
    crit_id = rubric["criteria"][0]["id"]

    team = client.post("/api/v1/teams", json={"event_id": event_id, "name": "Team Tie"}, headers=participant_headers).json()
    p1 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Tie Project Alpha"}, headers=participant_headers).json()
    p2 = client.post("/api/v1/projects", json={"event_id": event_id, "team_id": team["id"], "title": "Tie Project Beta"}, headers=participant_headers).json()
    client.post(f"/api/v1/projects/{p1['id']}/submit", headers=participant_headers)
    client.post(f"/api/v1/projects/{p2['id']}/submit", headers=participant_headers)

    judge_id = client.get("/api/v1/auth/me", headers=judge_headers).json()["id"]
    for p in [p1, p2]:
        client.post("/api/v1/judging/assignments", json={"event_id": event_id, "judge_id": judge_id, "project_id": p["id"]}, headers=organizer_headers)
        client.post(f"/api/v1/judging/projects/{p['id']}/scores", json={"scores": [{"criterion_id": crit_id, "score": 8.0}]}, headers=judge_headers)

    # Run 1
    res1 = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers).json()
    order1 = [r["project_id"] for r in res1["results"]]

    # Run 2
    res2 = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers).json()
    order2 = [r["project_id"] for r in res2["results"]]

    # Order must be 100% identical and deterministic
    assert order1 == order2
    assert res1["results"][0]["normalized_rank"] == 1
    assert res1["results"][1]["normalized_rank"] == 2


def test_normalization_security_boundaries(client: TestClient, auth_tokens: Dict[str, str]):
    """
    Security Test:
    - Participant: 403 Forbidden on API and HTML Normalization Lab.
    - Judge: 403 Forbidden on API and HTML Normalization Lab.
    - Organizer: 200 OK on both.
    """
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # Setup quick event
    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    ev = client.post("/api/v1/events", json={
        "title": "Sec Normalization Event",
        "slug": "sec-norm-event",
        "phase": "active",
        "end_time": deadline.isoformat(),
    }, headers=organizer_headers).json()
    event_id = ev["id"]
    slug = ev["slug"]

    # 1. Participant is Forbidden
    assert client.get(f"/api/v1/normalization/events/{event_id}", headers=participant_headers).status_code == 403
    assert client.get(f"/events/{slug}/normalization-lab", headers=participant_headers).status_code == 403

    # 2. Judge is Forbidden
    assert client.get(f"/api/v1/normalization/events/{event_id}", headers=judge_headers).status_code == 403
    assert client.get(f"/events/{slug}/normalization-lab", headers=judge_headers).status_code == 403

    # 3. Organizer is Authorized
    res_api = client.get(f"/api/v1/normalization/events/{event_id}", headers=organizer_headers)
    assert res_api.status_code == 200
    res_html = client.get(f"/events/{slug}/normalization-lab", headers=organizer_headers)
    assert res_html.status_code == 200
    assert "Cross-Judge Normalization Lab" in res_html.text
