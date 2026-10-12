from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_user_repository
from app.core.config import get_settings
from app.core.security import hash_password
from app.main import app
from app.repositories.users import UserRepository


@pytest.fixture
def auth_client(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth-routes.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    get_settings.cache_clear()
    repository = UserRepository(str(db_path))
    repository.put_org("org-1", "Sonar Team")
    repository.put_user(
        user_id="user-1",
        org_id="org-1",
        username="operator",
        password_hash=hash_password("correct-password"),
        role="member",
    )
    app.dependency_overrides[get_user_repository] = lambda: repository
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_login_returns_access_token(auth_client):
    response = auth_client.post(
        "/auth/login",
        json={"username": "operator", "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_demo_style_login_on_fresh_seeded_file(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "fresh-auth.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("SEED_DEMO_USERNAME", "demo")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "demo")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "demo")
    get_settings.cache_clear()
    repository = UserRepository(str(db_path))
    from app.bootstrap.seed import run_seed

    run_seed(repository)
    app.dependency_overrides[get_user_repository] = lambda: repository
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"username": "demo", "password": "demo"},
        )
    app.dependency_overrides.clear()
    get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_invalid_credentials_returns_stable_401(auth_client):
    response = auth_client.post(
        "/auth/login",
        json={"username": "operator", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert "access_token" not in response.json()


def test_login_with_corrupt_database_returns_store_unavailable(
    monkeypatch, tmp_path: Path
):
    corrupt = tmp_path / "corrupt-auth.db"
    garbage = b"NOT SQLITE"
    corrupt.write_bytes(garbage)
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    get_settings.cache_clear()
    app.dependency_overrides[get_user_repository] = lambda: UserRepository(str(corrupt))
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"username": "operator", "password": "any"},
        )
    app.dependency_overrides.clear()
    get_settings.cache_clear()

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "STORE_UNAVAILABLE"
    assert body["message"] == "Metadata store is unavailable"
    assert corrupt.read_bytes() == garbage


def test_me_without_token_returns_unauthorized(auth_client):
    response = auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_me_with_invalid_token_returns_unauthorized(auth_client):
    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_me_with_login_token_returns_org_identity(auth_client):
    login = auth_client.post(
        "/auth/login",
        json={"username": "operator", "password": "correct-password"},
    )
    token = login.json()["access_token"]

    response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "org_id": "org-1",
        "role": "member",
    }
