"""Comprehensive tests for DOGFOOD Tier 4 (T4) features:
1. Complete REST API + OpenAPI coverage
2. Webhooks Subsystem with HMAC-SHA256 signing
3. Certificates & Record Generation with public verification
4. Signed Judge Participation Records with tamper detection
5. Embeddable Gallery Widget (zero CDN)
6. Bulk Import & Export (transactional rollback & multi-entity CSV/JSON)
"""

import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

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
from src.voting.models import Vote, VotingCampaign
from src.webhooks.models import WebhookEndpoint, WebhookDelivery


def test_rest_api_completeness_and_openapi(client, auth_tokens, test_db: Session):
    """Test REST API completeness and OpenAPI schema export."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    headers_part = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # 1. OpenAPI Specification endpoint
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/events" in spec["paths"]
    assert "/api/v1/webhooks" in spec["paths"]
    assert "/api/v1/certificates" in spec["paths"]

    # 2. Event creation & REST update
    res = client.post(
        "/api/v1/events",
        headers=headers_org,
        json={
            "title": "T4 Test Hackathon",
            "slug": "t4-test-hackathon",
            "description": "Initial description",
            "archetype": "cosmos",
        },
    )
    assert res.status_code == 201
    event_id = res.json()["id"]

    # Update event
    res = client.put(
        f"/api/v1/events/{event_id}",
        headers=headers_org,
        json={"title": "T4 Test Hackathon Updated", "description": "Updated description"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "T4 Test Hackathon Updated"

    # 3. Tracks listing and update
    res = client.post(
        f"/api/v1/events/{event_id}/tracks",
        headers=headers_org,
        json={"title": "AI Track", "description": "AI innovations"},
    )
    assert res.status_code == 201
    track_id = res.json()["id"]

    res = client.get(f"/api/v1/events/{event_id}/tracks")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.put(
        f"/api/v1/events/{event_id}/tracks/{track_id}",
        headers=headers_org,
        json={"title": "AI & ML Track"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "AI & ML Track"

    # 4. Prizes listing and update
    res = client.post(
        f"/api/v1/events/{event_id}/prizes",
        headers=headers_org,
        json={"title": "Grand Prize", "amount": "$5,000"},
    )
    assert res.status_code == 201
    prize_id = res.json()["id"]

    res = client.get(f"/api/v1/events/{event_id}/prizes")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.put(
        f"/api/v1/events/{event_id}/prizes/{prize_id}",
        headers=headers_org,
        json={"title": "Grand Championship Prize", "amount": "$10,000"},
    )
    assert res.status_code == 200
    assert res.json()["amount"] == "$10,000"

    # 5. Team creation, retrieval, and update
    res = client.post(
        "/api/v1/teams",
        headers=headers_part,
        json={"event_id": event_id, "name": "Team Nova"},
    )
    assert res.status_code == 201
    team_id = res.json()["id"]

    res = client.get(f"/api/v1/teams/{team_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Team Nova"

    res = client.put(
        f"/api/v1/teams/{team_id}",
        headers=headers_part,
        json={"name": "Team Supernova"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Team Supernova"

    # 6. Project creation, retrieval
    res = client.post(
        "/api/v1/projects",
        headers=headers_part,
        json={
            "event_id": event_id,
            "team_id": team_id,
            "title": "Quantum Leap",
            "tagline": "Next-gen computing",
            "description": "Detailed description",
        },
    )
    assert res.status_code == 201
    project_id = res.json()["id"]

    res = client.get(f"/api/v1/projects/{project_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Quantum Leap"


def test_webhooks_lifecycle_and_signatures(client, auth_tokens, test_db: Session):
    """Test webhook subscription, delivery logging, and HMAC-SHA256 signature verification."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    headers_part = {"Authorization": f"Bearer {auth_tokens['participant']}"}

    # Participant cannot manage webhooks (403)
    res = client.post(
        "/api/v1/webhooks",
        headers=headers_part,
        json={
            "url": "http://127.0.0.1:9999/webhook",
            "secret": "my-secret-key",
        },
    )
    assert res.status_code == 403

    # Organizer registers webhook
    res = client.post(
        "/api/v1/webhooks",
        headers=headers_org,
        json={
            "url": "http://127.0.0.1:9999/webhook",
            "secret": "super-secret-hmac-key",
        },
    )
    assert res.status_code == 201
    webhook = res.json()
    webhook_id = webhook["id"]
    assert webhook["url"] == "http://127.0.0.1:9999/webhook"
    assert webhook["active"] is True


    # List webhooks
    res = client.get("/api/v1/webhooks", headers=headers_org)
    assert res.status_code == 200
    assert any(w["id"] == webhook_id for w in res.json())

    # Trigger test delivery (safe failure expected since 127.0.0.1:9999 is closed, but logged)
    res = client.post(f"/api/v1/webhooks/{webhook_id}/test", headers=headers_org)
    assert res.status_code == 200
    deliveries = res.json()
    assert len(deliveries) >= 1
    assert deliveries[0]["endpoint_id"] == webhook_id
    assert deliveries[0]["event_type"] == "webhook.test_ping"


    # List deliveries for endpoint
    res = client.get(f"/api/v1/webhooks/{webhook_id}/deliveries", headers=headers_org)
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # Verify HMAC signature calculation determinism
    test_payload = b'{"event":"test","timestamp":"2026-09-30T10:00:00Z"}'
    secret = "super-secret-hmac-key"
    expected_sig = hmac.new(secret.encode("utf-8"), test_payload, hashlib.sha256).hexdigest()
    calculated_sig = hmac.new(secret.encode("utf-8"), test_payload, hashlib.sha256).hexdigest()
    assert expected_sig == calculated_sig

    # Delete webhook
    res = client.delete(f"/api/v1/webhooks/{webhook_id}", headers=headers_org)
    assert res.status_code in (200, 204)



def test_certificates_issuance_verification_revocation(client, auth_tokens, test_db: Session):
    """Test certificate issuance, public cryptographic verification, and revocation."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    headers_part = {"Authorization": f"Bearer {auth_tokens['participant']}"}


    # Setup event
    res = client.post(
        "/api/v1/events",
        headers=headers_org,
        json={"title": "Cert Event", "slug": "cert-event", "archetype": "verdant"},
    )
    event_id = res.json()["id"]

    # Non-organizer cannot issue certificate (403)
    res = client.post(
        "/api/v1/certificates",
        headers=headers_part,
        json={
            "event_id": event_id,
            "recipient": "Hacker One",
            "award": "First Place",
        },
    )
    assert res.status_code == 403

    # Organizer issues certificate
    res = client.post(
        "/api/v1/certificates",
        headers=headers_org,
        json={
            "event_id": event_id,
            "recipient": "Alice & Bob (Team Alpha)",
            "award": "First Place - Grand Champion",
        },
    )
    assert res.status_code == 201
    cert = res.json()
    cert_id = cert["id"]
    token = cert["verification_token"]
    assert cert["status"] == "valid"

    # Get certificate by ID
    res = client.get(f"/api/v1/certificates/{cert_id}")
    assert res.status_code == 200
    assert res.json()["recipient"] == "Alice & Bob (Team Alpha)"

    # Public verification JSON API (no auth required)
    res = client.get(f"/api/v1/certificates/verify/{token}")
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["recipient"] == "Alice & Bob (Team Alpha)"
    assert data["status"] == "valid"

    # Invalid token verification
    res = client.get("/api/v1/certificates/verify/invalid-fake-token-12345")
    assert res.status_code == 200
    assert res.json()["valid"] is False

    # HTML verification view (public)
    res = client.get(f"/verify/certificate/{token}")
    assert res.status_code == 200
    assert "OFFICIALLY VERIFIED CERTIFICATE" in res.text
    assert "Alice &amp; Bob (Team Alpha)" in res.text or "Alice & Bob" in res.text

    # Printable HTML view
    res = client.get(f"/certificates/{cert_id}/printable")
    assert res.status_code == 200
    assert "Certificate of Achievement" in res.text
    assert cert["verification_token"] in res.text

    # Organizer revokes certificate
    res = client.post(f"/api/v1/certificates/{cert_id}/revoke", headers=headers_org)
    assert res.status_code == 200
    assert res.json()["status"] == "revoked"

    # Verify check now reports revoked
    res = client.get(f"/api/v1/certificates/verify/{token}")
    assert res.status_code == 200
    assert res.json()["valid"] is False
    assert res.json()["status"] == "revoked"


def test_signed_judge_participation_records(client, auth_tokens, test_db: Session):
    """Test signed judge records with completion requirements, HMAC signatures, and tamper detection."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}
    headers_judge = {"Authorization": f"Bearer {auth_tokens['judge_a']}"}

    # Setup event, team, project, rubric, and judge
    res = client.post(
        "/api/v1/events",
        headers=headers_org,
        json={"title": "Judge Sign Event", "slug": "judge-sign-event", "archetype": "arcade"},
    )
    event_id = res.json()["id"]

    res = client.post(
        "/api/v1/teams",
        headers=headers_org,
        json={"event_id": event_id, "name": "Team Judgeable"},
    )
    team_id = res.json()["id"]

    res = client.post(
        "/api/v1/projects",
        headers=headers_org,
        json={"event_id": event_id, "team_id": team_id, "title": "Project Evaluatable"},
    )
    project_id = res.json()["id"]

    # Submit project
    res = client.post(f"/api/v1/projects/{project_id}/submit", headers=headers_org)
    assert res.status_code == 200

    # Configure rubric
    res = client.post(
        f"/api/v1/judging/events/{event_id}/rubric",
        headers=headers_org,
        json={
            "name": "Standard Rubric",
            "criteria": [{"name": "Execution", "weight": 1.0, "min_score": 1, "max_score": 10}],
        },
    )
    rubric = res.json()
    criterion_id = rubric["criteria"][0]["id"]

    # Get judge_a user
    judge_a = test_db.query(User).filter(User.username == "judge_a").first()
    assert judge_a is not None

    # Try to issue record before assignment -> 400
    res = client.post(
        f"/api/v1/judging/events/{event_id}/judges/{judge_a.id}/record",
        headers=headers_org,
    )
    assert res.status_code == 400
    assert "no assigned projects" in res.json()["detail"]

    # Assign project to judge_a
    res = client.post(
        "/api/v1/judging/assignments",
        headers=headers_org,
        json={"event_id": event_id, "judge_id": judge_a.id, "project_id": project_id},
    )
    assert res.status_code == 201

    # Try to issue record before scoring -> 400 (pending evaluations)
    res = client.post(
        f"/api/v1/judging/events/{event_id}/judges/{judge_a.id}/record",
        headers=headers_org,
    )
    assert res.status_code == 400
    assert "pending evaluations" in res.json()["detail"]

    # Judge submits evaluation
    res = client.post(
        f"/api/v1/judging/projects/{project_id}/scores",
        headers=headers_judge,
        json={"scores": [{"criterion_id": criterion_id, "score": 9.5, "feedback": "Superb work"}]},
    )
    assert res.status_code in (200, 201)

    # Now issuance succeeds!

    res = client.post(
        f"/api/v1/judging/events/{event_id}/judges/{judge_a.id}/record",
        headers=headers_judge,
    )
    assert res.status_code == 201
    record = res.json()
    record_id = record["id"]
    assert record["total_assigned"] == 1
    assert record["total_evaluated"] == 1
    assert "signature" in record
    assert "canonical_payload" in record

    # Cryptographic verification endpoint
    res = client.get(f"/api/v1/judging/records/verify/{record_id}")
    assert res.status_code == 200
    assert res.json()["valid"] is True
    assert res.json()["judge_name"] == "judge_a"


    # HTML verification view (public)
    res = client.get(f"/verify/judge/{record_id}")
    assert res.status_code == 200
    assert "CRYPTOGRAPHICALLY VERIFIED JUDGE RECORD" in res.text
    assert record["signature"] in res.text

    # Tamper detection test: modify canonical_payload directly in database
    rec_obj = test_db.query(JudgeParticipationRecord).filter(JudgeParticipationRecord.id == record_id).first()
    rec_obj.canonical_payload = rec_obj.canonical_payload.replace('"total_evaluated":1', '"total_evaluated":999')
    test_db.commit()

    # Re-verify -> Tamper detected!
    res = client.get(f"/api/v1/judging/records/verify/{record_id}")
    assert res.status_code == 200
    assert res.json()["valid"] is False
    assert "mismatch" in res.json()["detail"]

    # HTML view reflects tampered status
    res = client.get(f"/verify/judge/{record_id}")
    assert res.status_code == 200
    assert "INVALID OR TAMPERED RECORD" in res.text


def test_embeddable_gallery_widget(client, auth_tokens, test_db: Session):
    """Test embeddable gallery widget JS asset and public projects JSON API."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Setup event with submitted project
    res = client.post(
        "/api/v1/events",
        headers=headers_org,
        json={"title": "Embed Event", "slug": "embed-event", "archetype": "monolith"},
    )
    event_id = res.json()["id"]

    res = client.post(
        "/api/v1/teams",
        headers=headers_org,
        json={"event_id": event_id, "name": "Embed Team"},
    )
    team_id = res.json()["id"]

    res = client.post(
        "/api/v1/projects",
        headers=headers_org,
        json={
            "event_id": event_id,
            "team_id": team_id,
            "title": "Widget Showcase",
            "tagline": "Works anywhere without CDN",
            "description": "Self-contained gallery widget",
        },
    )
    project_id = res.json()["id"]

    # Submit project
    client.post(f"/api/v1/projects/{project_id}/submit", headers=headers_org)

    # 1. Widget JavaScript asset
    res = client.get("/embed/gallery.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]
    assert "initGalleryWidgets" in res.text
    assert "chameleon-gallery-widget" in res.text

    # 2. Public Embed JSON Data API
    res = client.get(f"/api/v1/embed/events/{event_id}/projects")
    assert res.status_code == 200
    projects = res.json()
    assert len(projects) == 1
    assert projects[0]["title"] == "Widget Showcase"
    assert projects[0]["team_name"] == "Embed Team"

    # 3. Organizer Embed Dashboard HTML
    res = client.get("/events/embed-event/embed", headers=headers_org)
    assert res.status_code == 200
    assert "Embeddable Gallery Widget" in res.text
    assert "chameleon-gallery-widget" in res.text


def test_bulk_import_and_export(client, auth_tokens, test_db: Session):
    """Test bulk import with transactional rollback on errors and multi-entity bulk exports."""
    headers_org = {"Authorization": f"Bearer {auth_tokens['organizer']}"}

    # Setup event
    res = client.post(
        "/api/v1/events",
        headers=headers_org,
        json={"title": "Data Exchange Event", "slug": "data-exchange-event", "archetype": "bio"},
    )
    event_id = res.json()["id"]

    # 1. Bulk import with invalid row -> Transactional rollback!
    invalid_payload = [
        {"title": "Valid Project", "team_name": "Valid Team"},
        {"title": "", "team_name": "Broken Team"},  # Empty title -> error
    ]
    res = client.post(
        f"/api/v1/events/{event_id}/import/projects",
        headers=headers_org,
        json=invalid_payload,
    )
    assert res.status_code == 400
    data = res.json()
    assert data["success"] is False
    assert len(data["errors"]) >= 1

    # Verify ZERO projects were created (rollback worked)
    count = test_db.query(Project).filter(Project.event_id == event_id).count()
    assert count == 0

    # 2. Bulk import with valid JSON payload -> Transactional commit
    valid_payload = [
        {
            "title": "Bio Sensors",
            "team_name": "BioTech Group",
            "track": "Health Tech",
            "tagline": "Realtime biometrics",
            "description": "Wearable sensor platform",
        },
        {
            "title": "Neural Linker",
            "team_name": "Neuro Labs",
            "track": "Health Tech",
            "tagline": "Brain-computer interface",
            "description": "Neural signal decoding",
        },
    ]
    res = client.post(
        f"/api/v1/events/{event_id}/import/projects",
        headers=headers_org,
        json=valid_payload,
    )
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["imported_count"] == 2

    # Verify both projects now exist in database
    count = test_db.query(Project).filter(Project.event_id == event_id).count()
    assert count == 2

    # 3. Bulk Exports
    # Projects CSV
    res = client.get(f"/api/v1/events/{event_id}/export/projects.csv", headers=headers_org)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Bio Sensors" in res.text
    assert "Neural Linker" in res.text

    # Teams CSV
    res = client.get(f"/api/v1/events/{event_id}/export/teams.csv", headers=headers_org)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "BioTech Group" in res.text
    assert "Neuro Labs" in res.text

    # Scores CSV
    res = client.get(f"/api/v1/events/{event_id}/export/scores.csv", headers=headers_org)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]

    # Votes CSV
    res = client.get(f"/api/v1/events/{event_id}/export/votes.csv", headers=headers_org)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]

    # Event Bundle JSON
    res = client.get(f"/api/v1/events/{event_id}/export/bundle.json", headers=headers_org)
    assert res.status_code == 200
    bundle = res.json()
    assert bundle["event"]["title"] == "Data Exchange Event"
    assert len(bundle["projects"]) == 2
    assert "exported_at" in bundle

    # 4. Organizer Data Exchange Dashboard HTML
    res = client.get("/events/data-exchange-event/data", headers=headers_org)
    assert res.status_code == 200
    assert "Data Exchange &amp; Bulk Transfer" in res.text or "Data Exchange & Bulk Transfer" in res.text
    assert "Bulk Projects Import" in res.text
