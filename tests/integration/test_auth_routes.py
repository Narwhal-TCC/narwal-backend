import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.api.deps import get_user_repository
from app.core.config import get_settings
from app.core.security import hash_password
from app.main import app
from app.repositories.users import UserRepository, ensure_table


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    get_settings.cache_clear()
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ensure_table(dynamodb, "auth-routes-test")
        repository = UserRepository(table)
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
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_with_invalid_credentials_returns_stable_401(auth_client):
    response = auth_client.post(
        "/auth/login",
        json={"username": "operator", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert "access_token" not in response.json()


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
