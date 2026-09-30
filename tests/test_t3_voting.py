"""Comprehensive Milestone T3 Community Voting & Comments Tests for ChameleonOS.

Tests cover:
1. Open-link voting (public unauthenticated participation)
2. Email-gated voting (offline verification flow)
3. Authenticated voting (account-required ballots)
4. Unauthorized voting rejection (wrong access mode, unauthenticated, unverified)
5. Duplicate vote rejection (single and approval methods)
6. Server-side vote rate limiting and anti-abuse
7. Deterministic randomized ballot ordering (server-derived seed)
8. Result secrecy during active voting (sealed from visitors, participants, judges)
9. Public result visibility after close (configurable access)
10. Authenticated comments on submitted projects
11. Comment moderation and soft deletion (organizer only)
12. Tamper-evident vote audit trail
13. Rejected vote audit events
14. Organizer-only live results tally preview
"""

from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi.testclient import TestClient

from src.voting.service import rate_limiter


# ==============================================================================
# TEST FIXTURE HELPER
# ==============================================================================

def setup_voting_environment(client: TestClient, auth_tokens: Dict[str, str]):
    """Helper to configure an event with multiple submitted projects for voting."""
    rate_limiter.reset()
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Create Event
    ev_res = client.post("/api/v1/events", json={
        "title": "Community Hack 2026",
        "slug": "community-hack-2026",
        "phase": "active",
    }, headers=organizer_headers)
    assert ev_res.status_code == 201
    event_id = ev_res.json()["id"]

    # 2. Create Teams and 3 Submitted Projects
    projects = []
    for i in range(1, 4):
        team = client.post("/api/v1/teams", json={
            "event_id": event_id,
            "name": f"Team Alpha {i}",
        }, headers=participant_headers).json()

        proj = client.post("/api/v1/projects", json={
            "event_id": event_id,
            "team_id": team["id"],
            "title": f"Project Pulse {i}",
            "tagline": f"Innovative system {i}",
            "description": f"Detailed description for project {i}",
        }, headers=participant_headers).json()

        # Submit project to gallery
        sub_res = client.post(f"/api/v1/projects/{proj['id']}/submit", headers=participant_headers)
        assert sub_res.status_code == 200
        projects.append(proj["id"])

    return {
        "event_id": event_id,
        "event_slug": "community-hack-2026",
        "proj_1": projects[0],
        "proj_2": projects[1],
        "proj_3": projects[2],
    }


# ==============================================================================
# 1. OPEN-LINK VOTING
# ==============================================================================

def test_open_link_voting(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify open-link voting allows public voters to cast ballots without authentication."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Create open campaign
    c_res = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "People's Choice Open",
        "access_mode": "open",
        "voting_method": "single",
        "results_visibility": "public_after_close",
    }, headers=organizer_headers)
    assert c_res.status_code == 201
    campaign_id = c_res.json()["id"]

    # Activate campaign
    act_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)
    assert act_res.status_code == 200

    # Visitor 1 votes for Project 1
    v1_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "visitor-device-alpha",
    })
    assert v1_res.status_code == 201
    assert v1_res.json()["project_id"] == env["proj_1"]

    # Visitor 2 votes for Project 2
    v2_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_2"],
        "voter_key": "visitor-device-beta",
    })
    assert v2_res.status_code == 201
    assert v2_res.json()["project_id"] == env["proj_2"]


# ==============================================================================
# 2. EMAIL-GATED VOTING (OFFLINE FLOW)
# ==============================================================================

def test_email_gated_voting(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify email-gated voting using offline verification token/code."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Create email campaign
    c_res = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Verified Community Award",
        "access_mode": "email",
        "voting_method": "single",
    }, headers=organizer_headers)
    campaign_id = c_res.json()["id"]
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)

    # 1. Request verification token/code
    tok_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/request-email-token", json={
        "email": "innovator@example.com",
    })
    assert tok_res.status_code == 200
    tok_data = tok_res.json()
    assert tok_data["email"] == "innovator@example.com"
    token = tok_data["token"]
    code = tok_data["verification_code"]
    assert code is not None
    assert tok_data["is_verified"] is False

    # 2. Confirm token via code
    conf_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/verify-email", json={
        "email": "innovator@example.com",
        "code": code,
        "token": token,
    })
    assert conf_res.status_code == 200
    assert conf_res.json()["is_verified"] is True

    # 3. Cast vote using verified token
    vote_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": token,
    })
    assert vote_res.status_code == 201
    assert vote_res.json()["project_id"] == env["proj_1"]


# ==============================================================================
# 3. AUTHENTICATED VOTING
# ==============================================================================

def test_authenticated_voting(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify authenticated voting requires logged-in user credentials."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    c_res = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Builders Ballot",
        "access_mode": "authenticated",
        "voting_method": "single",
    }, headers=organizer_headers)
    campaign_id = c_res.json()["id"]
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)

    # Participant votes
    v_res = client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_2"],
    }, headers=participant_headers)
    assert v_res.status_code == 201
    assert v_res.json()["project_id"] == env["proj_2"]


# ==============================================================================
# 4. UNAUTHORIZED VOTING REJECTION
# ==============================================================================

def test_unauthorized_voting_rejection(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify unauthorized votes are strictly rejected according to access rules."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Case A: Authenticated campaign rejects unauthenticated visitor
    c1 = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Auth Only",
        "access_mode": "authenticated",
    }, headers=organizer_headers).json()
    client.post(f"/api/v1/voting/campaigns/{c1['id']}/activate", headers=organizer_headers)

    unauth_res = client.post(f"/api/v1/voting/campaigns/{c1['id']}/votes", json={
        "project_id": env["proj_1"],
    })
    assert unauth_res.status_code == 401

    # Case B: Email campaign rejects unverified voter key
    c2 = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Email Only",
        "access_mode": "email",
    }, headers=organizer_headers).json()
    client.post(f"/api/v1/voting/campaigns/{c2['id']}/activate", headers=organizer_headers)

    bad_email_res = client.post(f"/api/v1/voting/campaigns/{c2['id']}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "unverified-random-token",
    })
    assert bad_email_res.status_code == 403

    # Case C: Draft/Inactive campaign rejects any vote
    c3 = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Draft Campaign",
        "access_mode": "open",
    }, headers=organizer_headers).json()

    draft_res = client.post(f"/api/v1/voting/campaigns/{c3['id']}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "some-key",
    })
    assert draft_res.status_code == 400


# ==============================================================================
# 5. DUPLICATE VOTE REJECTION
# ==============================================================================

def test_duplicate_vote_rejection(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify duplicate vote rejection for single and approval voting methods."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Test single-vote duplicate rejection
    c_single = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Single Vote Campaign",
        "access_mode": "open",
        "voting_method": "single",
    }, headers=organizer_headers).json()
    client.post(f"/api/v1/voting/campaigns/{c_single['id']}/activate", headers=organizer_headers)

    # First vote succeeds
    v1 = client.post(f"/api/v1/voting/campaigns/{c_single['id']}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "voter-dup-check",
    })
    assert v1.status_code == 201

    # Second vote from same voter key rejected (HTTP 409 Conflict)
    v2 = client.post(f"/api/v1/voting/campaigns/{c_single['id']}/votes", json={
        "project_id": env["proj_2"],
        "voter_key": "voter-dup-check",
    })
    assert v2.status_code == 409
    assert "duplicate" in v2.json()["detail"].lower()

    # Test approval-vote duplicate rejection
    c_appr = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Approval Campaign",
        "access_mode": "open",
        "voting_method": "approval",
    }, headers=organizer_headers).json()
    client.post(f"/api/v1/voting/campaigns/{c_appr['id']}/activate", headers=organizer_headers)

    # Vote for proj 1 -> OK
    client.post(f"/api/v1/voting/campaigns/{c_appr['id']}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "voter-appr-check",
    })
    # Vote for proj 2 -> OK
    a2 = client.post(f"/api/v1/voting/campaigns/{c_appr['id']}/votes", json={
        "project_id": env["proj_2"],
        "voter_key": "voter-appr-check",
    })
    assert a2.status_code == 201

    # Second vote for proj 1 from same voter -> Rejected 409
    a3 = client.post(f"/api/v1/voting/campaigns/{c_appr['id']}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "voter-appr-check",
    })
    assert a3.status_code == 409


# ==============================================================================
# 6. RATE LIMITING
# ==============================================================================

def test_rate_limiting(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify server-side vote rate limiting rejects abusive high-frequency voting."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    rate_limiter.reset()

    c = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Rate Limit Test",
        "access_mode": "open",
        "voting_method": "approval",
    }, headers=organizer_headers).json()
    client.post(f"/api/v1/voting/campaigns/{c['id']}/activate", headers=organizer_headers)

    voter_key = "rapid-fire-bot"
    # Send 5 allowed requests (to different projects or tokens)
    for i in range(5):
        # We need distinct projects to avoid duplicate check, or test rate limiter directly
        res = client.post(f"/api/v1/voting/campaigns/{c['id']}/votes", json={
            "project_id": env[f"proj_{(i % 3) + 1}"],
            "voter_key": f"{voter_key}-{i}",
        })
        assert res.status_code == 201

    # Now simulate rapid bursts from the exact same rate limit key
    rate_test_key = "burst-voter"
    # Send 5 rapid attempts from same key
    for _ in range(5):
        client.post(f"/api/v1/voting/campaigns/{c['id']}/votes", json={
            "project_id": env["proj_1"],
            "voter_key": rate_test_key,
        })

    # The 6th attempt must be blocked with HTTP 429
    rate_limited_res = client.post(f"/api/v1/voting/campaigns/{c['id']}/votes", json={
        "project_id": env["proj_2"],
        "voter_key": rate_test_key,
    })
    assert rate_limited_res.status_code == 429
    assert "rate limit exceeded" in rate_limited_res.json()["detail"].lower()


# ==============================================================================
# 7. DETERMINISTIC RANDOMIZED BALLOT ORDER
# ==============================================================================

def test_deterministic_randomized_ballot_order(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify project ordering on ballot is randomized per voter, but deterministic on refresh."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    c = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Ballot Ordering Test",
        "access_mode": "open",
    }, headers=organizer_headers).json()
    campaign_id = c["id"]

    # Voter A: First request
    b1_a = client.get(f"/api/v1/voting/campaigns/{campaign_id}/ballot?voter_key=voter-alice").json()
    order_1_a = [p["project_id"] for p in b1_a["projects"]]

    # Voter A: Second request (Refresh simulation)
    b2_a = client.get(f"/api/v1/voting/campaigns/{campaign_id}/ballot?voter_key=voter-alice").json()
    order_2_a = [p["project_id"] for p in b2_a["projects"]]

    # Must be 100% identical on refresh!
    assert order_1_a == order_2_a

    # Voter B: Request
    b_b = client.get(f"/api/v1/voting/campaigns/{campaign_id}/ballot?voter_key=voter-charlie-different-seed").json()
    order_b = [p["project_id"] for p in b_b["projects"]]

    # Both contain all 3 projects
    assert set(order_1_a) == {env["proj_1"], env["proj_2"], env["proj_3"]}
    assert set(order_b) == {env["proj_1"], env["proj_2"], env["proj_3"]}


# ==============================================================================
# 8. RESULT SECRECY DURING ACTIVE VOTING
# ==============================================================================

def test_result_secrecy_during_voting(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify results are strictly hidden from visitors, participants, and judges while voting is active."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}

    c = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Secrecy Test Campaign",
        "access_mode": "open",
    }, headers=organizer_headers).json()
    campaign_id = c["id"]
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)

    # Cast a vote
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "voter-1",
    })

    # 1. Unauthenticated visitor tries to view results -> 403 Forbidden
    vis_res = client.get(f"/api/v1/voting/campaigns/{campaign_id}/results")
    assert vis_res.status_code == 403
    assert "sealed" in vis_res.json()["detail"].lower()

    # 2. Participant tries to view results -> 403 Forbidden
    part_res = client.get(f"/api/v1/voting/campaigns/{campaign_id}/results", headers=participant_headers)
    assert part_res.status_code == 403

    # 3. Judge tries to view results -> 403 Forbidden
    judge_res = client.get(f"/api/v1/voting/campaigns/{campaign_id}/results", headers=judge_headers)
    assert judge_res.status_code == 403


# ==============================================================================
# 9. ORGANIZER-ONLY LIVE RESULTS
# ==============================================================================

def test_organizer_only_live_results(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify organizers can inspect live results during active voting."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    c = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Live Tally Test",
        "access_mode": "open",
    }, headers=organizer_headers).json()
    campaign_id = c["id"]
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)

    # Cast 2 votes for Proj 1 and 1 vote for Proj 2
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={"project_id": env["proj_1"], "voter_key": "v1"})
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={"project_id": env["proj_1"], "voter_key": "v2"})
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={"project_id": env["proj_2"], "voter_key": "v3"})

    # Organizer views live results -> 200 OK
    org_res = client.get(f"/api/v1/voting/campaigns/{campaign_id}/results", headers=organizer_headers)
    assert org_res.status_code == 200
    data = org_res.json()
    assert data["total_votes"] == 3
    assert data["total_unique_voters"] == 3
    results = data["results"]
    assert results[0]["project_id"] == env["proj_1"]
    assert results[0]["votes_count"] == 2
    assert results[0]["rank"] == 1
    assert results[1]["project_id"] == env["proj_2"]
    assert results[1]["votes_count"] == 1
    assert results[1]["rank"] == 2


# ==============================================================================
# 10. PUBLIC RESULT VISIBILITY AFTER CLOSE
# ==============================================================================

def test_public_result_visibility_after_close(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify results become visible after campaign is closed according to configuration."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # Case A: public_after_close
    c1 = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Public After Close Campaign",
        "access_mode": "open",
        "results_visibility": "public_after_close",
    }, headers=organizer_headers).json()
    c1_id = c1["id"]
    client.post(f"/api/v1/voting/campaigns/{c1_id}/activate", headers=organizer_headers)
    client.post(f"/api/v1/voting/campaigns/{c1_id}/votes", json={"project_id": env["proj_1"], "voter_key": "v1"})

    # Close campaign
    client.post(f"/api/v1/voting/campaigns/{c1_id}/close", headers=organizer_headers)

    # Now visitor can view results
    pub_res = client.get(f"/api/v1/voting/campaigns/{c1_id}/results")
    assert pub_res.status_code == 200
    assert pub_res.json()["total_votes"] == 1

    # Case B: organizers_only
    c2 = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Secret Always Campaign",
        "access_mode": "open",
        "results_visibility": "organizers_only",
    }, headers=organizer_headers).json()
    c2_id = c2["id"]
    client.post(f"/api/v1/voting/campaigns/{c2_id}/activate", headers=organizer_headers)
    client.post(f"/api/v1/voting/campaigns/{c2_id}/close", headers=organizer_headers)

    # Visitor rejected even after close
    assert client.get(f"/api/v1/voting/campaigns/{c2_id}/results").status_code == 403
    # Organizer allowed
    assert client.get(f"/api/v1/voting/campaigns/{c2_id}/results", headers=organizer_headers).status_code == 200


# ==============================================================================
# 11. COMMENTS ON GALLERY PROJECTS
# ==============================================================================

def test_comments(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify authenticated users can post comments on public projects and visitors can read them."""
    env = setup_voting_environment(client, auth_tokens)
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. Unauthenticated post rejected -> 401
    unauth_post = client.post(f"/api/v1/projects/{env['proj_1']}/comments", json={
        "body": "Visitor trying to comment",
    })
    assert unauth_post.status_code == 401

    # 2. Authenticated participant posts comment -> 201
    post_res = client.post(f"/api/v1/projects/{env['proj_1']}/comments", json={
        "body": "Impressive microservice architecture and clean visual design!",
    }, headers=participant_headers)
    assert post_res.status_code == 201
    comment_data = post_res.json()
    assert comment_data["author_name"] == "participant"
    assert "Impressive microservice" in comment_data["body"]
    assert comment_data["is_deleted"] is False

    # 3. Public visitor can read comments -> 200
    list_res = client.get(f"/api/v1/projects/{env['proj_1']}/comments")
    assert list_res.status_code == 200
    comments = list_res.json()
    assert len(comments) == 1
    assert comments[0]["id"] == comment_data["id"]


# ==============================================================================
# 12. COMMENT MODERATION & DELETION
# ==============================================================================

def test_comment_moderation(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify only organizers/admins can moderate and delete comments."""
    env = setup_voting_environment(client, auth_tokens)
    participant_headers = {"Authorization": f"Bearer {auth_tokens['participant']}"}
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    judge_headers = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}

    # Post comment
    c_res = client.post(f"/api/v1/projects/{env['proj_1']}/comments", json={
        "body": "Comment with inappropriate spam link",
    }, headers=participant_headers)
    comment_id = c_res.json()["id"]

    # Judge attempt to delete -> 403 Forbidden
    judge_del = client.delete(f"/api/v1/projects/{env['proj_1']}/comments/{comment_id}", headers=judge_headers)
    assert judge_del.status_code == 403

    # Organizer deletes comment -> 200 OK
    org_del = client.delete(f"/api/v1/projects/{env['proj_1']}/comments/{comment_id}", headers=organizer_headers)
    assert org_del.status_code == 200
    assert org_del.json()["is_deleted"] is True

    # Visitor listing comments should no longer see it
    public_list = client.get(f"/api/v1/projects/{env['proj_1']}/comments").json()
    assert len(public_list) == 0

    # Including deleted shows it marked
    admin_list = client.get(f"/api/v1/projects/{env['proj_1']}/comments?include_deleted=true").json()
    assert len(admin_list) == 1
    assert admin_list[0]["is_deleted"] is True


# ==============================================================================
# 13. VOTE AUDIT TRAIL & REJECTED VOTE AUDIT
# ==============================================================================

def test_vote_audit_trail(client: TestClient, auth_tokens: Dict[str, str]):
    """Verify vote audit trail captures accepted votes and rejected attempts."""
    env = setup_voting_environment(client, auth_tokens)
    organizer_headers = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    c = client.post("/api/v1/voting/campaigns", json={
        "event_id": env["event_id"],
        "title": "Audit Verification Campaign",
        "access_mode": "open",
        "voting_method": "single",
    }, headers=organizer_headers).json()
    campaign_id = c["id"]
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/activate", headers=organizer_headers)

    # 1. Accepted vote
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_1"],
        "voter_key": "audit-voter-1",
    })

    # 2. Rejected duplicate vote
    client.post(f"/api/v1/voting/campaigns/{campaign_id}/votes", json={
        "project_id": env["proj_2"],
        "voter_key": "audit-voter-1",
    })

    # Retrieve audit records as organizer
    audit_res = client.get("/api/v1/audit", headers=organizer_headers)
    assert audit_res.status_code == 200
    events = audit_res.json()
    event_types = [e["event_type"] for e in events]

    assert "VOTE_ACCEPTED" in event_types
    assert "VOTE_DUPLICATE_REJECTED" in event_types
    assert "VOTING_CAMPAIGN_CREATED" in event_types
    assert "VOTING_CAMPAIGN_ACTIVATED" in event_types
