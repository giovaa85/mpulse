"""
Tests: authentication flows.
"""
import pytest


def test_login_success(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "demo"
    assert data["role"] == "user"
    assert "mp_session" in r.cookies


def test_login_admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "wrongpassword"})
    assert r.status_code == 401


def test_login_wrong_username(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "demo"})
    assert r.status_code == 401


def test_me_authenticated(auth_client):
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "demo"


def test_me_unauthenticated(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout(auth_client):
    r = auth_client.post("/api/auth/logout")
    assert r.status_code == 200
    # After logout, me should be 401
    r2 = auth_client.get("/api/auth/me")
    assert r2.status_code == 401


def test_change_password_success(auth_client):
    # Re-login fresh
    auth_client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    r = auth_client.post("/api/auth/change-password", json={
        "current_password": "demo",
        "new_password": "newpass123",
    })
    assert r.status_code == 200
    # Restore original password
    auth_client.post("/api/auth/change-password", json={
        "current_password": "newpass123",
        "new_password": "demo",
    })


def test_change_password_wrong_current(auth_client):
    auth_client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    r = auth_client.post("/api/auth/change-password", json={
        "current_password": "totallyWrong",
        "new_password": "newpass123",
    })
    assert r.status_code == 400


def test_admin_can_access_cache_stats(admin_client):
    r = admin_client.get("/api/debug/cache-stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_fetches" in data
    assert "hit_ratio" in data


def test_demo_cannot_access_cache_stats(auth_client):
    r = auth_client.get("/api/debug/cache-stats")
    assert r.status_code == 403


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["db"] is True
