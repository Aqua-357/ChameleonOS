"""Shared test fixtures for ChameleonOS."""

from typing import Dict, Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

import src.models  # Ensure all 13 models are imported
from src.database import Base, get_db
from src.main import app
from src.auth.service import seed_users


@pytest.fixture
def test_engine():
    """Create a static-pool in-memory SQLite engine shared across sessions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_db(test_engine) -> Generator[Session, None, None]:
    """Provide a fresh in-memory SQLite database session for each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_tokens(test_db: Session) -> Dict[str, str]:
    """Seed default credentials and return a dictionary of access tokens by username."""
    seed_data = seed_users(test_db)
    return {username: data["token"] for username, data in seed_data.items()}


@pytest.fixture
def client(test_engine, test_db: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to the in-memory test database."""
    seed_users(test_db)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
