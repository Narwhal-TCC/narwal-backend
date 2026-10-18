import sqlite3
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image

from app.api.deps import (
    get_analyze_service,
    get_history_service,
    get_model_gateway,
    get_object_store,
    get_user_repository,
)
from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.core.security import create_access_token, hash_password
from app.main import app
from app.repositories.analyses import AnalysisRepository
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository
from app.services.analyze import AnalyzeService
from app.services.history import HistoryService

BUCKET = "narwal-routes-test"


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(5, 10, 15)).save(buffer, format="PNG")
    return buffer.getvalue()


def _stage(
    *,
    label: str = "NOMBO",
    confidence: float = 0.9,
    detector_score: float | None = None,
) -> dict:
    return {
        "x1": 240.0,
        "y1": 120.0,
        "x2": 400.0,
        "y2": 360.0,
        "detector_score": confidence if detector_score is None else detector_score,
        "label": label,
        "confidence": confidence,
    }


class ConfigurableModelGateway:
    def __init__(self) -> None:
        self.raw_output: list = [_stage()]
        self.unavailable = False

    def ensure_model_loaded(self):
        if self.unavailable:
            raise ModelUnavailableError("Model object could not be downloaded")
        return self

    def predict(self, image_array):
        self.ensure_model_loaded()
        return [dict(row) for row in self.raw_output]


@pytest.fixture
def analyses_client(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "analyses-routes.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    get_object_store.cache_clear()
    with mock_aws():
        users = UserRepository(str(db_path))
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

        s3 = boto3.client("s3", region_name="us-east-1")
        object_store = S3ObjectStore(client=s3, bucket=BUCKET)
        object_store.ensure_bucket()
        analyses = AnalysisRepository(str(db_path))
        gateway = ConfigurableModelGateway()

        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_model_gateway] = lambda: gateway
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


def post_image(
    client: TestClient,
    headers: dict,
    data: bytes,
    content_type: str = "image/png",
    *,
    query_params: dict | None = None,
    **form_fields: str,
):
    return client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", data, content_type)},
        data=form_fields,
        params=query_params or {},
    )


def assert_model_id_on_detail_list_and_stats(
    client: TestClient,
    headers: dict,
    analysis_id: str,
    expected: str,
) -> None:
    detail = client.get(f"/analyses/{analysis_id}", headers=headers).json()
    assert detail["model_id"] == expected
    listed = client.get("/analyses", headers=headers).json()["items"]
    match = next(item for item in listed if item["id"] == analysis_id)
    assert match["model_id"] == expected
    stats = client.get("/analyses/stats", headers=headers).json()
    assert stats["last_analysis"]["id"] == analysis_id
    assert stats["last_analysis"]["model_id"] == expected


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
            "label": "NOMBO",
            "detector_score": 0.9,
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


def test_analyze_with_metadata_round_trips_in_response_and_get(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(
        client,
        headers,
        png_bytes(),
        campaign_name="North Survey",
        coordinates="12.34, -56.78",
        collected_at="2026-09-12T08:30:00+00:00",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["campaign_name"] == "North Survey"
    assert body["coordinates"] == "12.34, -56.78"
    expected_collected_at = datetime(2026, 9, 12, 8, 30, tzinfo=UTC)
    assert datetime.fromisoformat(body["collected_at"]) == expected_collected_at
    assert body["review_status"] == "pending"
    assert body["primary_class"] == "NOMBO"

    detail = client.get(f"/analyses/{body['id']}", headers=headers).json()
    assert detail["campaign_name"] == "North Survey"
    assert detail["coordinates"] == "12.34, -56.78"
    assert datetime.fromisoformat(detail["collected_at"]) == expected_collected_at


def test_analyze_without_metadata_omits_optional_fields(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes())

    assert response.status_code == 200
    body = response.json()
    assert body["campaign_name"] is None
    assert body["coordinates"] is None
    assert body["collected_at"] is None


def test_analyze_with_invalid_collected_at_returns_400_and_creates_no_row(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(
        client,
        headers,
        png_bytes(),
        collected_at="not-a-datetime",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert client.get("/analyses", headers=headers).json()["items"] == []


def test_analyze_without_token_returns_401(analyses_client):
    client, _ = analyses_client

    response = post_image(client, {}, png_bytes())

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_list_q_filters_by_campaign_name(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    post_image(client, headers, png_bytes(), campaign_name="North Survey")
    post_image(client, headers, png_bytes(), campaign_name="South Run")

    response = client.get("/analyses", headers=headers, params={"q": "north"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["campaign_name"] == "North Survey"


def test_list_class_filter_milco_and_nombo(analyses_client):
    client, gateway = analyses_client
    headers = auth_headers(client, "operator")
    gateway.raw_output = [_stage(label="MILCO")]
    milco = post_image(client, headers, png_bytes()).json()
    gateway.raw_output = [_stage(label="NOMBO")]
    nombo = post_image(client, headers, png_bytes()).json()

    milco_list = client.get("/analyses", headers=headers, params={"class": "MILCO"}).json()
    nombo_list = client.get("/analyses", headers=headers, params={"class": "NOMBO"}).json()

    assert [item["id"] for item in milco_list["items"]] == [milco["id"]]
    assert milco_list["items"][0]["primary_class"] == "MILCO"
    assert [item["id"] for item in nombo_list["items"]] == [nombo["id"]]
    assert nombo_list["items"][0]["primary_class"] == "NOMBO"


def test_list_invalid_class_returns_400(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = client.get("/analyses", headers=headers, params={"class": "UNKNOWN"})

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_filters_respect_org_isolation(analyses_client):
    client, gateway = analyses_client
    owner_headers = auth_headers(client, "operator")
    rival_headers = auth_headers(client, "rival")
    gateway.raw_output = [_stage(label="MILCO")]
    post_image(client, owner_headers, png_bytes(), campaign_name="North Survey")

    rival_list = client.get(
        "/analyses",
        headers=rival_headers,
        params={"q": "north", "class": "MILCO"},
    ).json()

    assert rival_list["items"] == []


def test_list_returns_only_caller_org_analyses(analyses_client):
    client, _ = analyses_client
    owner_headers = auth_headers(client, "operator")
    created = post_image(client, owner_headers, png_bytes()).json()

    owner_list = client.get("/analyses", headers=owner_headers).json()
    rival_list = client.get("/analyses", headers=auth_headers(client, "rival")).json()

    assert [item["id"] for item in owner_list["items"]] == [created["id"]]
    assert owner_list["items"][0]["detection_count"] == 1
    assert rival_list["items"] == []


def test_patch_review_status_transitions_pending_confirmed_false_positive(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    created = post_image(client, headers, png_bytes()).json()
    analysis_id = created["id"]

    confirmed = client.patch(
        f"/analyses/{analysis_id}",
        headers=headers,
        json={"review_status": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["review_status"] == "confirmed"

    false_positive = client.patch(
        f"/analyses/{analysis_id}",
        headers=headers,
        json={"review_status": "false_positive"},
    )
    assert false_positive.status_code == 200
    assert false_positive.json()["review_status"] == "false_positive"
    assert false_positive.json()["detections"] == created["detections"]
    assert false_positive.json()["image_url"] is not None

    listed = client.get("/analyses", headers=headers).json()
    assert listed["items"][0]["review_status"] == "false_positive"


def test_patch_invalid_review_status_returns_400(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    created = post_image(client, headers, png_bytes()).json()

    response = client.patch(
        f"/analyses/{created['id']}",
        headers=headers,
        json={"review_status": "invalid"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert (
        client.get(f"/analyses/{created['id']}", headers=headers).json()["review_status"]
        == "pending"
    )


def test_patch_review_status_cross_org_returns_404(analyses_client):
    client, _ = analyses_client
    created = post_image(client, auth_headers(client, "operator"), png_bytes()).json()

    response = client.patch(
        f"/analyses/{created['id']}",
        headers=auth_headers(client, "rival"),
        json={"review_status": "confirmed"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"


def test_patch_review_status_without_token_returns_401(analyses_client):
    client, _ = analyses_client
    created = post_image(client, auth_headers(client, "operator"), png_bytes()).json()

    response = client.patch(
        f"/analyses/{created['id']}",
        json={"review_status": "confirmed"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


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


def test_stats_empty_org_returns_zeros_and_nulls(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = client.get("/analyses/stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["analyses_count"] == 0
    assert body["milco_detections_count"] == 0
    assert body["last_analysis"] is None
    assert body["active_campaign"] is None


def test_stats_populated_org_aggregates_counts_and_campaign(analyses_client):
    client, gateway = analyses_client
    headers = auth_headers(client, "operator")
    gateway.raw_output = [_stage(label="MILCO")]
    post_image(client, headers, png_bytes(), campaign_name="Beta").json()
    gateway.raw_output = [_stage(label="NOMBO")]
    latest = post_image(client, headers, png_bytes(), campaign_name="Alpha").json()

    response = client.get("/analyses/stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["analyses_count"] == 2
    assert body["milco_detections_count"] == 1
    assert body["active_campaign"] == "Alpha"
    assert body["last_analysis"]["id"] == latest["id"]
    assert body["last_analysis"]["primary_class"] == "NOMBO"


def test_stats_is_not_captured_as_analysis_id(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = client.get("/analyses/stats", headers=headers)

    assert response.status_code == 200
    assert "analyses_count" in response.json()
    assert response.json().get("code") != "ANALYSIS_NOT_FOUND"


def test_stats_without_token_returns_401(analyses_client):
    client, _ = analyses_client

    response = client.get("/analyses/stats")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


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


def test_analyze_stored_image_is_readable_from_object_storage(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes())
    body = response.json()
    assert body["image_s3_key"]

    s3 = boto3.client("s3", region_name="us-east-1")
    payload = s3.get_object(Bucket=BUCKET, Key=body["image_s3_key"])["Body"].read()
    assert len(payload) > 0


def _wire_analyses_app(db_path: Path, gateway: ConfigurableModelGateway, s3) -> None:
    users = UserRepository(str(db_path))
    object_store = S3ObjectStore(client=s3, bucket=BUCKET)
    object_store.ensure_bucket()
    analyses = AnalysisRepository(str(db_path))
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_model_gateway] = lambda: gateway
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


def test_stored_analysis_readable_via_http_after_new_client_on_same_file(
    monkeypatch, tmp_path: Path
):
    db_path = tmp_path / "http-persist.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    get_object_store.cache_clear()

    gateway = ConfigurableModelGateway()
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        seed_users = UserRepository(str(db_path))
        seed_users.put_org("org-1", "Sonar Team")
        seed_users.put_user("user-1", "org-1", "operator", hash_password("pw"), "member")

        _wire_analyses_app(db_path, gateway, s3)
        with TestClient(app) as client:
            headers = auth_headers(client, "operator")
            created = post_image(
                client,
                headers,
                png_bytes(),
                campaign_name="Persist Survey",
            ).json()
            analysis_id = created["id"]
        app.dependency_overrides.clear()

        _wire_analyses_app(db_path, gateway, s3)
        with TestClient(app) as reopened_client:
            headers = auth_headers(reopened_client, "operator")
            response = reopened_client.get(f"/analyses/{analysis_id}", headers=headers)

        app.dependency_overrides.clear()
    get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == analysis_id
    assert body["campaign_name"] == "Persist Survey"


def test_get_analysis_returns_confidence_088_as_json_number(analyses_client):
    client, gateway = analyses_client
    gateway.raw_output = [_stage(confidence=0.88)]
    headers = auth_headers(client, "operator")

    created = post_image(client, headers, png_bytes()).json()
    detail = client.get(f"/analyses/{created['id']}", headers=headers).json()

    confidence = detail["detections"][0]["confidence"]
    assert confidence == 0.88
    assert isinstance(confidence, float)


def test_list_analyses_returns_newest_created_first(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    older = post_image(client, headers, png_bytes(), campaign_name="Older Run").json()
    newer = post_image(client, headers, png_bytes(), campaign_name="Newer Run").json()

    response = client.get("/analyses", headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [newer["id"], older["id"]]


def test_patch_confirmed_then_get_returns_confirmed_review_status(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    created = post_image(client, headers, png_bytes()).json()
    analysis_id = created["id"]

    patch_response = client.patch(
        f"/analyses/{analysis_id}",
        headers=headers,
        json={"review_status": "confirmed"},
    )
    assert patch_response.status_code == 200

    detail = client.get(f"/analyses/{analysis_id}", headers=headers).json()
    assert detail["review_status"] == "confirmed"


def _corrupt_analyses_client(monkeypatch, tmp_path: Path):
    corrupt = tmp_path / "corrupt-analyses.db"
    corrupt.write_bytes(b"NOT SQLITE")
    monkeypatch.setenv("SQLITE_PATH", str(corrupt))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    get_object_store.cache_clear()
    users = UserRepository(str(corrupt))
    analyses = AnalysisRepository(str(corrupt))
    gateway = ConfigurableModelGateway()
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        object_store = S3ObjectStore(client=s3, bucket=BUCKET)
        object_store.ensure_bucket()
        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_model_gateway] = lambda: gateway
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
            yield client
        app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def corrupt_analyses_client(monkeypatch, tmp_path):
    yield from _corrupt_analyses_client(monkeypatch, tmp_path)


def test_corrupt_database_returns_store_unavailable_on_analysis_routes(
    corrupt_analyses_client,
):
    client = corrupt_analyses_client
    token = create_access_token("user-1", "org-1", "member")
    headers = {"Authorization": f"Bearer {token}"}
    analysis_id = "01J0000000000000000000000"

    store_message = "Metadata store is unavailable"

    post = post_image(client, headers, png_bytes())
    assert post.status_code == 503
    assert post.json()["code"] == "STORE_UNAVAILABLE"
    assert post.json()["message"] == store_message

    listing = client.get("/analyses", headers=headers)
    assert listing.status_code == 503
    assert listing.json()["code"] == "STORE_UNAVAILABLE"
    assert listing.json()["message"] == store_message

    stats = client.get("/analyses/stats", headers=headers)
    assert stats.status_code == 503
    assert stats.json()["code"] == "STORE_UNAVAILABLE"
    assert stats.json()["message"] == store_message

    detail = client.get(f"/analyses/{analysis_id}", headers=headers)
    assert detail.status_code == 503
    assert detail.json()["code"] == "STORE_UNAVAILABLE"
    assert detail.json()["message"] == store_message

    patch_response = client.patch(
        f"/analyses/{analysis_id}",
        headers=headers,
        json={"review_status": "confirmed"},
    )
    assert patch_response.status_code == 503
    assert patch_response.json()["code"] == "STORE_UNAVAILABLE"
    assert patch_response.json()["message"] == store_message


def test_failed_insert_returns_503_and_leaves_list_unchanged(
    monkeypatch, tmp_path: Path
):
    db_path = tmp_path / "failed-insert.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings.cache_clear()
    get_object_store.cache_clear()
    users = UserRepository(str(db_path))
    users.put_org("org-1", "Sonar Team")
    users.put_user("user-1", "org-1", "operator", hash_password("pw"), "member")
    analyses = AnalysisRepository(str(db_path))
    gateway = ConfigurableModelGateway()

    class _ConnectionProxy:
        def __init__(self, inner: sqlite3.Connection) -> None:
            self._inner = inner

        def execute(self, sql, params=(), /, **kwargs):
            if "INSERT INTO analyses" in str(sql):
                raise sqlite3.OperationalError("forced failure")
            return self._inner.execute(sql, params, **kwargs)

        def commit(self):
            return self._inner.commit()

        def rollback(self):
            return self._inner.rollback()

        def close(self):
            return self._inner.close()

        def __getattr__(self, name):
            return getattr(self._inner, name)

    real_with_connection = analyses._with_connection

    def failing_with_connection():
        return _ConnectionProxy(real_with_connection())

    analyses._with_connection = failing_with_connection  # type: ignore[method-assign]

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        object_store = S3ObjectStore(client=s3, bucket=BUCKET)
        object_store.ensure_bucket()
        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_model_gateway] = lambda: gateway
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
            headers = auth_headers(client, "operator")
            before = client.get("/analyses", headers=headers).json()["items"]
            response = post_image(client, headers, png_bytes())
            after = client.get("/analyses", headers=headers).json()["items"]
        app.dependency_overrides.clear()
    get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["code"] == "STORE_UNAVAILABLE"
    assert after == before


@pytest.mark.parametrize(
    ("form_model_id", "query_model_id"),
    [
        (None, None),
        ("", None),
        (None, "ignored-id"),
    ],
)
def test_post_analyses_default_model_id_on_detail_list_and_stats(
    analyses_client, form_model_id, query_model_id
):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    form = {}
    if form_model_id is not None:
        form["model_id"] = form_model_id
    query = {"model_id": query_model_id} if query_model_id is not None else None

    response = post_image(
        client,
        headers,
        png_bytes(),
        query_params=query,
        **form,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "yolo-convnext-balanced"
    assert_model_id_on_detail_list_and_stats(
        client, headers, body["id"], "yolo-convnext-balanced"
    )


def test_post_analyses_explicit_two_stage_pt_returns_two_stage_pt(analyses_client):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(client, headers, png_bytes(), model_id="two-stage-pt")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "two-stage-pt"
    assert_model_id_on_detail_list_and_stats(
        client, headers, body["id"], "two-stage-pt"
    )


@pytest.mark.parametrize("bad_model_id", ["two-stage-pt ", "Two-Stage-Pt"])
def test_post_analyses_unknown_model_id_returns_400_and_leaves_list_unchanged(
    analyses_client, bad_model_id
):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")
    before = client.get("/analyses", headers=headers).json()["items"]

    response = post_image(client, headers, png_bytes(), model_id=bad_model_id)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "UNKNOWN_MODEL"
    assert body["message"] == "Unknown model id"
    after = client.get("/analyses", headers=headers).json()["items"]
    assert after == before


def test_post_analyses_invalid_image_with_unknown_model_returns_invalid_image(
    analyses_client,
):
    client, _ = analyses_client
    headers = auth_headers(client, "operator")

    response = post_image(
        client,
        headers,
        b"not-an-image",
        model_id="not-a-model",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"


def test_post_analyses_unknown_model_without_token_returns_unauthorized(analyses_client):
    client, _ = analyses_client

    response = post_image(client, {}, png_bytes(), model_id="not-a-model")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_post_analyses_model_unavailable_leaves_list_unchanged(analyses_client):
    client, gateway = analyses_client
    gateway.unavailable = True
    headers = auth_headers(client, "operator")
    before = client.get("/analyses", headers=headers).json()["items"]

    response = post_image(client, headers, png_bytes(), model_id="two-stage-pt")

    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_UNAVAILABLE"
    after = client.get("/analyses", headers=headers).json()["items"]
    assert after == before
