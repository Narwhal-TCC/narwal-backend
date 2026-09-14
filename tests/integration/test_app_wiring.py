from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image

from app.api.deps import (
    get_analysis_repository,
    get_model_gateway,
    get_object_store,
)
from app.core.config import get_settings
from app.main import app
from app.repositories.users import UserRepository
from app.services.model_gateway import FakeModelGateway


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (640, 480), color=(1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def _clear_dependency_caches() -> None:
    get_object_store.cache_clear()
    get_analysis_repository.cache_clear()
    get_model_gateway.cache_clear()


@pytest.fixture
def wired_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "wiring-test-secret-at-least-32-bytes")
    monkeypatch.setenv("DDB_TABLE", "wiring-test")
    monkeypatch.setenv("S3_BUCKET", "wiring-test")
    monkeypatch.setenv("PLATFORM_ADMIN_USERNAME", "wiring-admin")
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "wiring-admin-password")
    monkeypatch.setenv("PLATFORM_ADMIN_ORG_ID", "wiring-org")
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    _clear_dependency_caches()
    with mock_aws():
        app.dependency_overrides[get_model_gateway] = lambda: FakeModelGateway()
        with TestClient(app) as client:
            yield client
        app.dependency_overrides.clear()
    _clear_dependency_caches()
    get_settings.cache_clear()


def test_lifespan_seeds_platform_admin_and_creates_bucket(wired_client):
    seeded = UserRepository().get_by_username("wiring-admin")

    assert seeded is not None
    assert seeded["org_id"] == "wiring-org"
    assert seeded["role"] == "platform_admin"
    buckets = [bucket["Name"] for bucket in get_object_store().client.list_buckets()["Buckets"]]
    assert "wiring-test" in buckets


def test_health_auth_and_analyses_routes_share_one_app(wired_client):
    paths = set(app.openapi()["paths"])

    assert {"/health", "/auth/login", "/auth/me", "/analyses", "/analyses/{analysis_id}"} <= paths
    assert wired_client.get("/health").status_code == 200


def test_smoke_login_then_analyze_then_list(wired_client):
    login = wired_client.post(
        "/auth/login",
        json={"username": "wiring-admin", "password": "wiring-admin-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    analyze = wired_client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
    )
    assert analyze.status_code == 200
    created = analyze.json()
    assert created["org_id"] == "wiring-org"
    assert len(created["detections"]) == 1

    listed = wired_client.get("/analyses", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
