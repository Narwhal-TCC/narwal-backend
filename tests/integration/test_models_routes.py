from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_model_gateway
from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.core.security import create_access_token
from app.main import app
from app.repositories import metadata_db

EXPECTED_CATALOG = {
    "models": [
        {
            "id": "two-stage-pt",
            "label": "RetinaNet + fusão (PyTorch)",
            "is_default": True,
        }
    ]
}


@pytest.fixture
def models_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "models-route-test-secret-at-least-32-bytes")
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def _auth_headers(role: str, user_id: str = "user-1", org_id: str = "org-1") -> dict[str, str]:
    token = create_access_token(user_id, org_id, role)
    return {"Authorization": f"Bearer {token}"}


def test_get_models_member_returns_catalog(models_client):
    response = models_client.get("/models", headers=_auth_headers("member"))

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG


def test_get_models_platform_admin_returns_catalog(models_client):
    response = models_client.get(
        "/models",
        headers=_auth_headers("platform_admin", user_id="admin-1", org_id="platform"),
    )

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG


def test_get_models_without_token_returns_401(models_client):
    response = models_client.get("/models")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_get_models_invalid_token_returns_401(models_client):
    response = models_client.get(
        "/models",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_get_models_disallowed_role_returns_401(models_client):
    response = models_client.get("/models", headers=_auth_headers("viewer"))

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_get_models_succeeds_when_sqlite_path_is_garbage(
    models_client, monkeypatch, tmp_path: Path
):
    garbage_path = tmp_path / "corrupt.db"
    garbage_path.write_bytes(b"NOT A SQLITE DATABASE")
    monkeypatch.setenv("SQLITE_PATH", str(garbage_path))
    get_settings.cache_clear()

    response = models_client.get("/models", headers=_auth_headers("member"))

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG


def test_get_models_succeeds_when_model_gateway_would_fail(models_client):
    class FailingGateway:
        def ensure_model_loaded(self):
            raise ModelUnavailableError("Model object could not be downloaded")

        def predict(self, _image_array):
            raise ModelUnavailableError("Model object could not be downloaded")

    app.dependency_overrides[get_model_gateway] = lambda: FailingGateway()
    try:
        response = models_client.get("/models", headers=_auth_headers("member"))
    finally:
        app.dependency_overrides.pop(get_model_gateway, None)

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG


def test_get_models_does_not_open_sqlite(models_client, monkeypatch):
    def forbidden_connect(*_args, **_kwargs):
        raise AssertionError("GET /models must not open SQLite")

    monkeypatch.setattr(metadata_db, "connect", forbidden_connect)

    response = models_client.get("/models", headers=_auth_headers("member"))

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG


def test_get_models_does_not_call_ensure_model_loaded(models_client):
    gateway = MagicMock()
    gateway.ensure_model_loaded.side_effect = ModelUnavailableError("unavailable")

    app.dependency_overrides[get_model_gateway] = lambda: gateway
    try:
        response = models_client.get("/models", headers=_auth_headers("member"))
    finally:
        app.dependency_overrides.pop(get_model_gateway, None)

    assert response.status_code == 200
    assert response.json() == EXPECTED_CATALOG
    gateway.ensure_model_loaded.assert_not_called()
