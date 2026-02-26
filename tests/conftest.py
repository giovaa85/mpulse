"""
Pytest fixtures for MarketPulse Terminal tests.
Uses a shared in-memory SQLite connection via StaticPool for test isolation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.auth import hash_password
from app.models import User, UserSettings


# ── Single shared in-memory engine ───────────────────────────────────────────
# StaticPool ensures ALL code in the test process reuses the same connection,
# so tables created in one place are visible everywhere.
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(TEST_ENGINE, "connect")
def _set_pragmas(conn, _):
    conn.execute("PRAGMA foreign_keys=ON")


TestSessionLocal = sessionmaker(bind=TEST_ENGINE, autocommit=False, autoflush=False)


def _create_tables_and_seed():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    with TestSessionLocal() as session:
        if session.query(User).count() == 0:
            for username, password, role in [
                ("admin", "admin", "admin"),
                ("demo",  "demo",  "user"),
            ]:
                u = User(username=username, password_hash=hash_password(password), role=role)
                session.add(u)
                session.flush()
                session.add(UserSettings(user_id=u.id))
            session.commit()


# Create tables and seed once for the entire test session
_create_tables_and_seed()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """TestClient with DB overridden to the test in-memory DB."""
    # Reset rate limiter so each test starts fresh
    from app import auth as auth_module
    auth_module._login_attempts.clear()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    """TestClient pre-authenticated as demo user."""
    resp = client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client


@pytest.fixture()
def admin_client(client):
    """TestClient pre-authenticated as admin."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return client
