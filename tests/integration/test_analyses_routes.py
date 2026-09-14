from io import BytesIO

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image

from app.api.deps import (
    get_analyze_service,
    get_history_service,
    get_user_repository,
)
from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.core.security import hash_password
from app.main import app
from app.repositories.analyses import AnalysisRepository
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository, ensure_table
from app.services.analyze import AnalyzeService
from app.services.history import HistoryService

BUCKET = "narwal-routes-test"


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(5, 10, 15)).save(buffer, format="PNG")
    return buffer.getvalue()


class ConfigurableModelGateway:
    def __init__(self) -> None:
        self.raw_output: list = [(0.5, 0.5, 0.25, 0.5, 0.9)]
        self.unavailable = False

    def ensure_model_loaded(self):
        if self.unavailable:
            raise ModelUnavailableError("Model object could not be downloaded")
        return self

    def predict(self, image_array):
        self.ensure_model_loaded()
        return [list(row) for row in self.raw_output]


@pytest.fixture
def analyses_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ensure_table(dynamodb, "analyses-routes-test")
        users = UserRepository(table)
        users.put_org("org-1", "Sonar Team")
        users.put_user("user-1", "org-1", "operator", hash_password("pw"), "member")
        users.put_org("org-2", "Rival Team")
        users.put_user("user-2", "org-2", "rival", hash_password("pw"), "member")
        users.put_org("platform", "Platform")
        users.put_user(
            "admin-1",
            "platform",
            "platform-admin",
            hash_password("pw"),
            "platform_admin",
        )

        object_store = S3ObjectStore(bucket=BUCKET)
        object_store.ensure_bucket()
        analyses = AnalysisRepository(table)
        gateway = ConfigurableModelGateway()

        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_analyze_service] = lambda: AnalyzeService(
            model_gateway=gateway,
            object_store=object_store,
            repository=analyses,
            timeout_seconds=5,
        )
        app.dependency_overrides[get_history_service] = lambda: HistoryService(
            repository=analyses,
            object_store=object_store,
        )
        with TestClient(app) as client:
            yield client, gateway
        app.dependency_overrides.clear()
    get_settings.cache_clear()


def token_for(client: TestClient, username: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": "pw"})
    return response.json()["access_token"]


def auth_headers(client: TestClient, username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(client, username)}"}


def post_image(client: TestClient, headers: dict, data: bytes, content_type: str = "image/png"):
    return client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", data, content_type)},
    )


def jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(20, 30, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_analyze_returns_detections_for_authenticated_member(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes())

    assert response.status_code == 200
    body = response.json()
    assert body["org_id"] == "org-1"
    assert body["user_id"] == "user-1"
    assert body["status"] == "succeeded"
    assert body["image_s3_key"] == f"analyses/org-1/{body['id']}/original.png"
    assert body["detections"] == [
        {
            "x1": 240.0,
            "y1": 120.0,
            "x2": 400.0,
            "y2": 360.0,
            "confidence": 0.9,
            "label": "mine",
        }
    ]


def test_analyze_accepts_jpeg_and_returns_canonical_detections(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, jpeg_bytes(), content_type="image/jpeg")

    assert response.status_code == 200
    body = response.json()
    assert body["image_content_type"] == "image/jpeg"
    assert body["image_s3_key"].endswith(".jpg")
    assert body["detections"][0]["confidence"] == 0.9


def test_analyze_with_no_detections_returns_empty_list(analyses_client):
    client, gateway = analyses_client
    gateway.raw_output = []
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes())

    assert response.status_code == 200
    assert response.json()["detections"] == []


def test_analyze_with_invalid_image_returns_400_and_creates_no_row(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, b"not-an-image")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"
    assert client.get("/analyses", headers=headers).json()["items"] == []


def test_analyze_with_unavailable_model_returns_503_and_creates_no_row(analyses_client):
    client, gateway = analyses_client
    gateway.unavailable = True
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes())

    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_UNAVAILABLE"
    gateway.unavailable = False
    assert client.get("/analyses", headers=headers).json()["items"] == []


def test_analyze_without_token_returns_401(analyses_client):
    client, _ = analyses_client

    response = post_image(client, {}, png_bytes())

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_list_returns_only_caller_org_analyses(analyses_client):
    client, _ = analyses_client
    owner_headers = auth_headers(client, "operator")
    created = post_image(client, owner_headers, png_bytes()).json()

    owner_list = client.get("/analyses", headers=owner_headers).json()
    rival_list = client.get("/analyses", headers=auth_headers(client, "rival")).json()

    assert [item["id"] for item in owner_list["items"]] == [created["id"]]
    assert owner_list["items"][0]["detection_count"] == 1
    assert rival_list["items"] == []


def test_get_returns_detections_and_image_url_for_owning_org(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    created = post_image(client, headers, png_bytes()).json()

    response = client.get(f"/analyses/{created['id']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["detections"] == created["detections"]
    assert body["image_s3_key"] == created["image_s3_key"]
    assert body["image_url"] is not None
    assert body["image_s3_key"] in body["image_url"]


def test_get_analysis_of_another_org_returns_404(analyses_client):
    client, _ = analyses_client
    created = post_image(client, auth_headers(client, "operator"), png_bytes()).json()

    response = client.get(
        f"/analyses/{created['id']}",
        headers=auth_headers(client, "rival"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"


def test_platform_admin_cannot_list_or_get_another_org_analyses(analyses_client):
    client, _ = analyses_client
    created = post_image(client, auth_headers(client, "operator"), png_bytes()).json()
    admin_headers = auth_headers(client, "platform-admin")

    listed = client.get("/analyses", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    detail = client.get(f"/analyses/{created['id']}", headers=admin_headers)
    assert detail.status_code == 404
    assert detail.json()["code"] == "ANALYSIS_NOT_FOUND"

    admin_created = post_image(client, admin_headers, png_bytes()).json()
    assert admin_created["org_id"] == "platform"
    admin_list = client.get("/analyses", headers=admin_headers).json()
    assert [item["id"] for item in admin_list["items"]] == [admin_created["id"]]
