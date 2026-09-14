import time
from io import BytesIO

import pytest
from PIL import Image

from app.core.errors import (
    InferenceTimeoutError,
    InvalidImageError,
    ModelUnavailableError,
)
from app.services.analyze import MAX_IMAGE_BYTES, AnalyzeService
from app.services.model_gateway import FakeModelGateway


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeObjectStore:
    def __init__(self) -> None:
        self.puts: list[dict] = []

    def put_analysis_image(self, org_id, analysis_id, ext, data, content_type) -> str:
        self.puts.append(
            {
                "org_id": org_id,
                "analysis_id": analysis_id,
                "ext": ext,
                "data": data,
                "content_type": content_type,
            }
        )
        return f"analyses/{org_id}/{analysis_id}/original.{ext}"


class FakeAnalysisRepository:
    def __init__(self) -> None:
        self.puts: list[dict] = []

    def put_analysis(self, **fields) -> dict:
        self.puts.append(fields)
        return fields


class UnavailableModelGateway:
    def ensure_model_loaded(self):
        raise ModelUnavailableError("Model object could not be downloaded")

    def predict(self, image_array):  # pragma: no cover - never reached
        raise AssertionError("predict must not run when the model is unavailable")


class HangingModelGateway:
    def ensure_model_loaded(self):
        return self

    def predict(self, image_array):
        time.sleep(5)
        return []


def build_service(gateway=None, store=None, repository=None, timeout_seconds=60):
    return AnalyzeService(
        model_gateway=gateway or FakeModelGateway(),
        object_store=store or FakeObjectStore(),
        repository=repository or FakeAnalysisRepository(),
        timeout_seconds=timeout_seconds,
    )


def test_valid_png_returns_detections_and_persists_analysis():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    result = service.analyze_image(
        org_id="org-1",
        user_id="user-1",
        content_type="image/png",
        data=png_bytes(),
    )

    assert result.status == "succeeded"
    assert result.org_id == "org-1"
    assert result.user_id == "user-1"
    assert len(result.detections) == 1
    detection = result.detections[0]
    assert (detection.x1, detection.y1, detection.x2, detection.y2) == (
        240.0,
        120.0,
        400.0,
        360.0,
    )
    assert detection.confidence == 0.9
    assert result.image_s3_key == f"analyses/org-1/{result.id}/original.png"
    assert result.image_content_type == "image/png"

    assert store.puts[0]["content_type"] == "image/png"
    assert len(repository.puts) == 1
    persisted = repository.puts[0]
    assert persisted["analysis_id"] == result.id
    assert persisted["org_id"] == "org-1"
    assert persisted["user_id"] == "user-1"
    assert persisted["status"] == "succeeded"
    assert persisted["image_s3_key"] == result.image_s3_key
    assert persisted["detections"] == [detection.model_dump()]


def test_no_detections_returns_empty_list_and_still_persists():
    repository = FakeAnalysisRepository()
    service = build_service(gateway=FakeModelGateway(raw_output=[]), repository=repository)

    result = service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert result.detections == []
    assert repository.puts[0]["detections"] == []


def test_oversize_image_is_rejected_without_any_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    with pytest.raises(InvalidImageError) as excinfo:
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            b"x" * (MAX_IMAGE_BYTES + 1),
        )

    assert excinfo.value.code == "INVALID_IMAGE"
    assert excinfo.value.status_code == 400
    assert store.puts == []
    assert repository.puts == []


def test_corrupt_bytes_with_valid_content_type_are_rejected_without_any_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    with pytest.raises(InvalidImageError) as excinfo:
        service.analyze_image("org-1", "user-1", "image/png", b"not-an-image")

    assert excinfo.value.code == "INVALID_IMAGE"
    assert store.puts == []
    assert repository.puts == []


def test_unsupported_content_type_is_rejected_without_any_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    with pytest.raises(InvalidImageError):
        service.analyze_image("org-1", "user-1", "image/tiff", png_bytes())

    assert store.puts == []
    assert repository.puts == []


def test_model_unavailable_leaves_no_image_or_analysis():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(gateway=UnavailableModelGateway(), store=store, repository=repository)

    with pytest.raises(ModelUnavailableError) as excinfo:
        service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert excinfo.value.code == "MODEL_UNAVAILABLE"
    assert excinfo.value.status_code == 503
    assert store.puts == []
    assert repository.puts == []


def test_inference_timeout_returns_timeout_error_without_success_row():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(
        gateway=HangingModelGateway(),
        store=store,
        repository=repository,
        timeout_seconds=1,
    )

    started = time.perf_counter()
    with pytest.raises(InferenceTimeoutError) as excinfo:
        service.analyze_image("org-1", "user-1", "image/png", png_bytes())
    elapsed = time.perf_counter() - started

    assert excinfo.value.code == "INFERENCE_TIMEOUT"
    assert excinfo.value.status_code == 504
    assert elapsed < 4
    assert store.puts == []
    assert repository.puts == []
