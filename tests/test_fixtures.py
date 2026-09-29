"""Tests for fixture loading, idempotency, ID preservation, timestamp parsing, and edge cases."""

from datetime import timezone
from pathlib import Path
from sqlalchemy.orm import Session

from src.fixtures import load_fixtures, parse_iso_datetime
from src.auth.models import User
from src.events.models import Event, Track, Prize
from src.submissions.models import Team, TeamMember, TeamInvite, Project
from src.judging.models import Rubric, RubricCriterion, JudgeAssignment, JudgeScore
from src.audit.models import AuditEvent


FIXTURES_PATH = Path(__file__).resolve().parent.parent / "fixtures.json"


def test_fixture_loading_all_entities(test_db: Session):
    """Verify that fixtures.json loads records across all 13 domain models."""
    counts = load_fixtures(FIXTURES_PATH, test_db)

    assert counts["users"] >= 4
    assert counts["events"] >= 1
    assert counts["tracks"] >= 2
    assert counts["prizes"] >= 2
    assert counts["teams"] >= 2
    assert counts["team_members"] >= 2
    assert counts["team_invites"] >= 1
    assert counts["projects"] >= 2
    assert counts["rubrics"] >= 1
    assert counts["rubric_criteria"] >= 4
    assert counts["judge_assignments"] >= 3
    assert counts["judge_scores"] >= 5
    assert counts["audit_events"] >= 2


def test_fixture_loading_idempotency(test_db: Session):
    """Verify that loading fixtures multiple times is idempotent and produces no duplicates."""
    counts_first = load_fixtures(FIXTURES_PATH, test_db)
    counts_second = load_fixtures(FIXTURES_PATH, test_db)

    assert counts_first == counts_second

    # Verify database counts do not double
    assert test_db.query(User).count() == counts_first["users"]
    assert test_db.query(Event).count() == counts_first["events"]
    assert test_db.query(Project).count() == counts_first["projects"]
    assert test_db.query(JudgeScore).count() == counts_first["judge_scores"]


def test_preserve_fixture_ids(test_db: Session):
    """Verify that explicit fixture IDs are preserved exactly in the database."""
    load_fixtures(FIXTURES_PATH, test_db)

    # Check known explicit IDs from fixtures.json
    organizer = test_db.query(User).filter(User.id == "usr_organizer").first()
    assert organizer is not None
    assert organizer.username == "organizer"

    event = test_db.query(Event).filter(Event.id == "evt_dogfood_2026").first()
    assert event is not None
    assert event.slug == "dogfood-2026"

    project = test_db.query(Project).filter(Project.id == "prj_aether_flow").first()
    assert project is not None
    assert project.title == "AetherFlow Agent Swarm"

    rubric = test_db.query(Rubric).filter(Rubric.id == "rbc_standard_2026").first()
    assert rubric is not None

    criterion = test_db.query(RubricCriterion).filter(RubricCriterion.id == "crt_technical_depth").first()
    assert criterion is not None


def test_parse_iso_utc_timestamps(test_db: Session):
    """Verify that ISO timestamps are correctly parsed and normalized to UTC."""
    load_fixtures(FIXTURES_PATH, test_db)

    event = test_db.query(Event).filter(Event.id == "evt_dogfood_2026").first()
    assert event is not None
    assert event.start_time is not None
    assert event.start_time.tzinfo is not None
    # UTC offset is zero
    assert event.start_time.utcoffset().total_seconds() == 0

    project = test_db.query(Project).filter(Project.id == "prj_aether_flow").first()
    assert project is not None
    assert project.submitted_at is not None
    assert project.submitted_at.tzinfo is not None
    assert project.submitted_at.utcoffset().total_seconds() == 0


def test_tolerate_missing_score_entries(test_db: Session):
    """Verify that fixture entries with null or missing scores are tolerated cleanly."""
    load_fixtures(FIXTURES_PATH, test_db)

    missing_score = test_db.query(JudgeScore).filter(JudgeScore.id == "scr_judge_a_crt3_missing").first()
    assert missing_score is not None
    assert missing_score.score is None
    assert "omitted deliberately" in (missing_score.feedback or "")


def test_tolerate_duplicate_submission_data(test_db: Session):
    """Verify that duplicate submission/project data in fixtures is tolerated and updated without error."""
    # Custom fixture data with duplicate project entries
    data_with_duplicates = {
        "users": [
            {"id": "u1", "username": "dup_user", "email": "dup@test.local", "role": "participant"}
        ],
        "events": [
            {"id": "e1", "title": "Dup Event", "slug": "dup-event"}
        ],
        "teams": [
            {"id": "t1", "event_id": "e1", "name": "Dup Team"}
        ],
        "projects": [
            {
                "id": "p1",
                "event_id": "e1",
                "team_id": "t1",
                "title": "Initial Submission",
                "is_submitted": False
            },
            {
                # Duplicate entry with same ID but updated title and submission status
                "id": "p1",
                "event_id": "e1",
                "team_id": "t1",
                "title": "Updated Final Submission",
                "is_submitted": True,
                "submitted_at": "2026-09-29T10:00:00Z"
            }
        ]
    }

    counts = load_fixtures(data_with_duplicates, test_db)
    assert counts["projects"] == 2

    # Should only result in 1 record with the updated title
    projects = test_db.query(Project).filter(Project.event_id == "e1").all()
    assert len(projects) == 1
    assert projects[0].title == "Updated Final Submission"
    assert projects[0].is_submitted is True


def test_handle_judges_with_identical_scores(test_db: Session):
    """Verify that multiple judges awarding identical scores on the same project/criterion is supported."""
    load_fixtures(FIXTURES_PATH, test_db)

    # Both judge_a and judge_b gave 9.5 for technical depth on prj_aether_flow
    scores = test_db.query(JudgeScore).filter(
        JudgeScore.project_id == "prj_aether_flow",
        JudgeScore.criterion_id == "crt_technical_depth",
    ).all()

    assert len(scores) == 2
    assert scores[0].score == 9.5
    assert scores[1].score == 9.5
    judge_ids = {s.judge_id for s in scores}
    assert judge_ids == {"usr_judge_a", "usr_judge_b"}
