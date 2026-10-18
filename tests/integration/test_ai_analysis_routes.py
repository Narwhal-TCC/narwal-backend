from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image

from app.api.deps import (
    get_analyze_service,
    get_gateway_pool,
    get_history_service,
    get_object_store,
    get_user_repository,
)
from app.core.errors import ModelUnavailableError
from app.core.security import hash_password
from app.main import app
from app.repositories.analyses import AnalysisRepository
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository
from app.schemas.analysis import AiAnalysis, AiDetectionNote
from app.services.ai_analyst import AnalystContext
from app.services.analyze import AnalyzeService
from app.services.gateway_pool import GatewayPool
from app.services.history import HistoryService

BUCKET = "narwal-ai-routes-test"


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


class ConfigurableModelGateway:
    def __init__(self) -> None:
        self.raw_output: list = []
        self.unavailable = False
        self.predict_calls = 0

    def ensure_model_loaded(self):
        if self.unavailable:
            raise ModelUnavailableError("Model object could not be downloaded")
        return self

    def predict(self, image_array):
        self.predict_calls += 1
        return [dict(row) for row in self.raw_output]


class FakeAiAnalyst:
    def __init__(self, response: AiAnalysis | None = None) -> None:
        self.calls = 0
        self.contexts: list[AnalystContext] = []
        self.response = response or AiAnalysis(
            status="ready",
            reason=None,
            summary="Resumo de teste.",
            detections=[AiDetectionNote(index=0, note="Nota.")],
            recommendation="Verificar.",
            caveats=[],
            model="openai/gpt-oss-120b",
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
        )

    def analyze(self, context: AnalystContext) -> AiAnalysis:
        self.calls += 1
        self.contexts.append(context)
        return self.response


def _pool_for(gateway: ConfigurableModelGateway) -> GatewayPool:
    return GatewayPool(
        gateway_factories={
            "yolo-convnext-balanced": lambda g=gateway: g,
            "yolo-convnext-recall": lambda g=gateway: g,
            "two-stage-pt": lambda g=gateway: g,
        }
    )


def _stage() -> dict:
    return {
        "x1": 240.0,
        "y1": 120.0,
        "x2": 400.0,
        "y2": 360.0,
        "detector_score": 0.9,
        "label": "MILCO",
        "confidence": 0.9,
    }


@pytest.fixture
def ai_routes_client(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "ai-routes.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    get_settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()
    get_object_store.cache_clear()

    gateway = ConfigurableModelGateway()
    gateway.raw_output = [_stage()]
    pool = _pool_for(gateway)
    fake_analyst = FakeAiAnalyst()

    with mock_aws():
        users = UserRepository(str(db_path))
        users.put_org("org-1", "Sonar Team")
        users.put_user("user-1", "org-1", "operator", hash_password("pw"), "member")
        s3 = __import__("boto3").client("s3", region_name="us-east-1")
        object_store = S3ObjectStore(client=s3, bucket=BUCKET)
        object_store.ensure_bucket()
        analyses = AnalysisRepository(str(db_path))

        def analyze_service_factory() -> AnalyzeService:
            return AnalyzeService(
                gateway_pool=pool,
                object_store=object_store,
                repository=analyses,
                timeout_seconds=5,
                ai_analyst=fake_analyst,
            )

        app.dependency_overrides[get_user_repository] = lambda: users
        app.dependency_overrides[get_gateway_pool] = lambda: pool
        app.dependency_overrides[get_analyze_service] = analyze_service_factory
        app.dependency_overrides[get_history_service] = lambda: HistoryService(
            repository=analyses,
            object_store=object_store,
        )
        with TestClient(app) as client:
            yield client, fake_analyst, gateway
        app.dependency_overrides.clear()
    get_settings.cache_clear()


def _login_headers(client: TestClient) -> dict[str, str]:
    token = client.post("/auth/login", json={"username": "operator", "password": "pw"}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_post_and_get_return_same_ready_ai_analysis(ai_routes_client):
    client, analyst, _ = ai_routes_client
    headers = _login_headers(client)

    response = client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_analysis"]["status"] == "ready"
    assert body["ai_analysis"]["summary"] == "Resumo de teste."
    assert analyst.calls == 1

    detail = client.get(f"/analyses/{body['id']}", headers=headers).json()
    assert detail["ai_analysis"] == body["ai_analysis"]


def test_post_returns_unavailable_ai_analysis_with_201(ai_routes_client):
    client, analyst, _ = ai_routes_client
    analyst.response = AiAnalysis(status="unavailable", reason="timeout")  # type: ignore[arg-type]
    headers = _login_headers(client)

    response = client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_analysis"]["status"] == "unavailable"
    assert body["ai_analysis"]["reason"] == "timeout"


def test_zero_detections_still_calls_analyst(ai_routes_client):
    client, analyst, gateway = ai_routes_client
    gateway.raw_output = []
    headers = _login_headers(client)

    client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
    )

    assert analyst.calls == 1
    assert analyst.contexts[0].milco_detection_count == 0
    assert analyst.contexts[0].detections == []


def test_invalid_image_does_not_call_analyst(ai_routes_client):
    client, analyst, _ = ai_routes_client
    headers = _login_headers(client)

    response = client.post(
        "/analyses",
        headers=headers,
        files={"file": ("bad.png", b"not-an-image", "image/png")},
    )

    assert response.status_code == 400
    assert analyst.calls == 0


def test_unknown_model_does_not_call_analyst(ai_routes_client):
    client, analyst, _ = ai_routes_client
    headers = _login_headers(client)

    response = client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
        data={"model_id": "not-a-model"},
    )

    assert response.status_code == 400
    assert analyst.calls == 0


def test_inference_failure_does_not_call_analyst(ai_routes_client):
    client, analyst, gateway = ai_routes_client
    gateway.unavailable = True
    headers = _login_headers(client)

    response = client.post(
        "/analyses",
        headers=headers,
        files={"file": ("sonar.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert analyst.calls == 0
