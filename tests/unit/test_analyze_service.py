import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.core.errors import (
    InferenceTimeoutError,
    InvalidImageError,
    ModelUnavailableError,
    StorageError,
    UnknownModelError,
    ValidationError,
)
from app.services.analyze import MAX_IMAGE_BYTES, AnalyzeService
from app.services.model_gateway import FakeModelGateway


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(40, 50, 60)).save(buffer, format="JPEG")
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

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        return f"https://example.test/{key}?expires={expires_seconds}"


class FailingObjectStore:
    def put_analysis_image(self, org_id, analysis_id, ext, data, content_type) -> str:
        raise StorageError("Could not store analysis image")

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:  # pragma: no cover
        raise AssertionError("presign must not run when put failed")


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


class SpyModelGateway(FakeModelGateway):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.ensure_calls = 0
        self.predict_calls = 0

    def ensure_model_loaded(self):
        self.ensure_calls += 1
        return super().ensure_model_loaded()

    def predict(self, image_array):
        self.predict_calls += 1
        return super().predict(image_array)


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
    gateway = FakeModelGateway()
    service = build_service(gateway=gateway, store=store, repository=repository)

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
    assert result.image_url == (
        f"https://example.test/{result.image_s3_key}?expires=900"
    )
    assert isinstance(gateway.last_image_array, np.ndarray)
    assert gateway.last_image_array.shape == (480, 640, 3)
    assert gateway.last_image_array.dtype == np.uint8

    assert store.puts[0]["content_type"] == "image/png"
    assert len(repository.puts) == 1
    persisted = repository.puts[0]
    assert persisted["analysis_id"] == result.id
    assert persisted["org_id"] == "org-1"
    assert persisted["user_id"] == "user-1"
    assert persisted["status"] == "succeeded"
    assert persisted["image_s3_key"] == result.image_s3_key
    assert persisted["detections"] == [detection.model_dump()]


def test_valid_jpeg_returns_detections_and_persists_analysis():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    gateway = FakeModelGateway()
    service = build_service(gateway=gateway, store=store, repository=repository)

    result = service.analyze_image("org-1", "user-1", "image/jpeg", jpeg_bytes())

    assert result.status == "succeeded"
    assert result.image_content_type == "image/jpeg"
    assert result.image_s3_key.endswith(".jpg")
    assert store.puts[0]["ext"] == "jpg"
    assert isinstance(gateway.last_image_array, np.ndarray)
    assert gateway.last_image_array.shape == (480, 640, 3)
    assert len(repository.puts) == 1


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


def test_storage_error_after_inference_leaves_no_analysis_row():
    repository = FakeAnalysisRepository()
    service = build_service(store=FailingObjectStore(), repository=repository)

    with pytest.raises(StorageError) as excinfo:
        service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert excinfo.value.code == "STORAGE_ERROR"
    assert excinfo.value.status_code == 503
    assert repository.puts == []


def test_same_org_concurrent_analyses_keep_payloads_isolated():
    repository = FakeAnalysisRepository()
    store = FakeObjectStore()

    def run(user_id: str, confidence: float):
        return build_service(
            gateway=FakeModelGateway(
                raw_output=[
                    {
                        "x1": 240.0,
                        "y1": 120.0,
                        "x2": 400.0,
                        "y2": 360.0,
                        "detector_score": confidence,
                        "label": "NOMBO",
                        "confidence": confidence,
                    }
                ]
            ),
            store=store,
            repository=repository,
        ).analyze_image("org-1", user_id, "image/png", png_bytes())

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, "user-a", 0.91)
        second = pool.submit(run, "user-b", 0.42)
        results = [first.result(), second.result()]

    assert len({result.id for result in results}) == 2
    assert {result.user_id for result in results} == {"user-a", "user-b"}
    by_user = {result.user_id: result for result in results}
    assert by_user["user-a"].detections[0].confidence == 0.91
    assert by_user["user-b"].detections[0].confidence == 0.42
    assert by_user["user-a"].image_s3_key != by_user["user-b"].image_s3_key
    assert len(repository.puts) == 2
    assert {row["user_id"] for row in repository.puts} == {"user-a", "user-b"}


def test_analyze_with_metadata_persists_parity_fields():
    repository = FakeAnalysisRepository()
    service = build_service(repository=repository)

    result = service.analyze_image(
        org_id="org-1",
        user_id="user-1",
        content_type="image/png",
        data=png_bytes(),
        campaign_name="Alpha Campaign",
        coordinates="-23.5,-46.6",
        collected_at="2026-09-12T08:30:00+00:00",
    )

    assert result.review_status == "pending"
    assert result.campaign_name == "Alpha Campaign"
    assert result.coordinates == "-23.5,-46.6"
    assert result.collected_at == datetime(2026, 9, 12, 8, 30, tzinfo=UTC)
    assert result.primary_class == "NOMBO"
    assert result.milco_detection_count == 0

    persisted = repository.puts[0]
    assert persisted["review_status"] == "pending"
    assert persisted["campaign_name"] == "Alpha Campaign"
    assert persisted["coordinates"] == "-23.5,-46.6"
    assert persisted["collected_at"] == "2026-09-12T08:30:00+00:00"
    assert persisted["primary_class"] == "NOMBO"
    assert persisted["milco_detection_count"] == 0


def test_analyze_without_metadata_uses_defaults():
    repository = FakeAnalysisRepository()
    service = build_service(repository=repository)

    result = service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert result.review_status == "pending"
    assert result.campaign_name is None
    assert result.coordinates is None
    assert result.collected_at is None
    assert result.primary_class == "NOMBO"
    assert result.milco_detection_count == 0
    assert repository.puts[0]["campaign_name"] is None


def test_oversized_campaign_name_is_rejected_without_any_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    with pytest.raises(ValidationError) as excinfo:
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            png_bytes(),
            campaign_name="x" * 257,
        )

    assert excinfo.value.status_code == 400
    assert store.puts == []
    assert repository.puts == []


def test_invalid_collected_at_is_rejected_without_any_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(store=store, repository=repository)

    with pytest.raises(ValidationError) as excinfo:
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            png_bytes(),
            collected_at="not-a-datetime",
        )

    assert excinfo.value.status_code == 400
    assert store.puts == []
    assert repository.puts == []


def test_milco_detection_sets_primary_class_and_count():
    repository = FakeAnalysisRepository()
    gateway = FakeModelGateway(
        raw_output=[
            {
                "x1": 240.0,
                "y1": 120.0,
                "x2": 400.0,
                "y2": 360.0,
                "detector_score": 0.9,
                "label": "MILCO",
                "confidence": 0.9,
            }
        ]
    )
    service = build_service(gateway=gateway, repository=repository)

    result = service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert result.primary_class == "MILCO"
    assert result.milco_detection_count == 1
    assert repository.puts[0]["primary_class"] == "MILCO"
    assert repository.puts[0]["milco_detection_count"] == 1


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


@pytest.mark.parametrize("model_id", [None, ""])
def test_analyze_omitted_or_empty_model_id_stores_balanced_pipeline(model_id):
    repository = FakeAnalysisRepository()
    service = build_service(repository=repository)

    result = service.analyze_image(
        "org-1",
        "user-1",
        "image/png",
        png_bytes(),
        model_id=model_id,
    )

    assert result.model_id == "yolo-convnext-balanced"
    assert repository.puts[0]["model_id"] == "yolo-convnext-balanced"


def test_analyze_explicit_two_stage_pt_stores_two_stage_pt():
    repository = FakeAnalysisRepository()
    service = build_service(repository=repository)

    result = service.analyze_image(
        "org-1",
        "user-1",
        "image/png",
        png_bytes(),
        model_id="two-stage-pt",
    )

    assert result.model_id == "two-stage-pt"
    assert repository.puts[0]["model_id"] == "two-stage-pt"


def test_analyze_unknown_model_id_raises_without_gateway_or_repository_write():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    gateway = SpyModelGateway()
    service = build_service(gateway=gateway, store=store, repository=repository)

    with pytest.raises(UnknownModelError) as excinfo:
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            png_bytes(),
            model_id="not-a-model",
        )

    assert excinfo.value.code == "UNKNOWN_MODEL"
    assert excinfo.value.status_code == 400
    assert excinfo.value.message == "Unknown model id"
    assert gateway.ensure_calls == 0
    assert gateway.predict_calls == 0
    assert store.puts == []
    assert repository.puts == []


def test_analyze_bad_image_with_unknown_model_id_raises_invalid_image_first():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    gateway = SpyModelGateway()
    service = build_service(gateway=gateway, store=store, repository=repository)

    with pytest.raises(InvalidImageError) as excinfo:
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            b"not-an-image",
            model_id="not-a-model",
        )

    assert excinfo.value.code == "INVALID_IMAGE"
    assert gateway.ensure_calls == 0
    assert gateway.predict_calls == 0
    assert store.puts == []
    assert repository.puts == []


def test_analyze_model_unavailable_with_model_id_leaves_no_insert():
    store = FakeObjectStore()
    repository = FakeAnalysisRepository()
    service = build_service(
        gateway=UnavailableModelGateway(),
        store=store,
        repository=repository,
    )

    with pytest.raises(ModelUnavailableError):
        service.analyze_image(
            "org-1",
            "user-1",
            "image/png",
            png_bytes(),
            model_id="two-stage-pt",
        )

    assert store.puts == []
    assert repository.puts == []


def test_analyze_canonical_row_is_stored_with_exact_field_values():
    repository = FakeAnalysisRepository()
    gateway = FakeModelGateway(
        raw_output=[
            {
                "x1": 10.0,
                "y1": 20.0,
                "x2": 30.0,
                "y2": 40.0,
                "detector_score": 0.91,
                "label": "MILCO",
                "confidence": 0.88,
            }
        ]
    )
    service = build_service(gateway=gateway, repository=repository)

    result = service.analyze_image("org-1", "user-1", "image/png", png_bytes())

    assert len(result.detections) == 1
    detection = result.detections[0]
    assert (detection.x1, detection.y1, detection.x2, detection.y2) == (
        10.0,
        20.0,
        30.0,
        40.0,
    )
    assert detection.detector_score == 0.91
    assert detection.label == "MILCO"
    assert detection.confidence == 0.88
    persisted = repository.puts[0]["detections"][0]
    assert persisted["confidence"] == 0.88
    assert persisted["label"] == "MILCO"
