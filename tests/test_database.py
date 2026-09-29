"""Tests for database initialization, schema integrity, and seed credentials."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.service import seed_users, verify_password, decode_access_token, print_auth_headers
from src.database import Base


def test_database_initialization_tables(test_db: Session):
    """Verify that all 13 required SQLAlchemy models and tables are initialized."""
    engine = test_db.get_bind()
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    expected_tables = {
        "users",
        "events",
        "tracks",
        "prizes",
        "teams",
        "team_members",
        "team_invites",
        "projects",
        "rubrics",
        "rubric_criteria",
        "judge_assignments",
        "judge_scores",
        "audit_events",
    }

    assert expected_tables.issubset(table_names), (
        f"Missing tables: {expected_tables - table_names}"
    )


def test_seed_credentials_creation(test_db: Session):
    """Verify that organizer, judge_a, judge_b, and participant are seeded with valid tokens."""
    seed_data = seed_users(test_db)

    assert "organizer" in seed_data
    assert "judge_a" in seed_data
    assert "judge_b" in seed_data
    assert "participant" in seed_data

    # Check roles
    assert seed_data["organizer"]["role"] == "organizer"
    assert seed_data["judge_a"]["role"] == "judge"
    assert seed_data["judge_b"]["role"] == "judge"
    assert seed_data["participant"]["role"] == "participant"

    # Verify password verification works
    organizer_user = test_db.query(User).filter(User.username == "organizer").first()
    assert organizer_user is not None
    assert verify_password(seed_data["organizer"]["password"], organizer_user.hashed_password)

    # Verify token decoding works
    for username, data in seed_data.items():
        token = data["token"]
        assert token is not None
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["username"] == username
        assert payload["role"] == data["role"]
        assert data["auth_header"].startswith("Bearer ")


def test_print_auth_headers(test_db: Session, capsys):
    """Verify that print_auth_headers outputs readable formatted headers."""
    seed_data = seed_users(test_db)
    print_auth_headers(seed_data)
    captured = capsys.readouterr()

    assert "[ChameleonOS] Seed Authentication Headers" in captured.out
    assert "ORGANIZER" in captured.out
    assert "Authorization: Bearer" in captured.out
