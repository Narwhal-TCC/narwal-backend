import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ok_when_sqlite_path_is_corrupt(monkeypatch, tmp_path: Path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not-a-sqlite-file")
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_bootstrap_logs_metadata_store_unavailable_for_corrupt_file(
    monkeypatch, tmp_path: Path, caplog
):
    from app.main import bootstrap

    corrupt = tmp_path / "corrupt.db"
    garbage = b"not-a-sqlite-file"
    corrupt.write_bytes(garbage)
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    get_settings.cache_clear()

    caplog.set_level(logging.WARNING)
    bootstrap()

    assert any("metadata store unavailable" in record.message for record in caplog.records)
    assert corrupt.read_bytes() == garbage


def test_auth_me_returns_200_with_valid_token_when_store_is_corrupt(
    monkeypatch, tmp_path: Path
):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not-a-sqlite-file")
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    token = create_access_token("user-1", "org-1", "member")

    with TestClient(app) as client:
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "org_id": "org-1",
        "role": "member",
    }


def test_auth_me_without_token_returns_unauthorized_when_store_is_corrupt(
    monkeypatch, tmp_path: Path
):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not-a-sqlite-file")
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
