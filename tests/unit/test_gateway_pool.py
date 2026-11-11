import numpy as np
import pytest

from app.core.config import g5v2_ensemble_s3_uri_list, get_settings
from app.core.errors import ModelUnavailableError
from app.services.gateway_pool import (
    FUSION_CONF_BY_ID,
    YOLO_G5V2_MOBILEVIT_ID,
    GatewayPool,
)
from app.services.model_gateway import FakeModelGateway
from app.services.yolo_convnext import YoloConvnextGateway, YoloConvnextWeights
from app.services.yolo_fusion_v3 import YoloFusionV3Gateway


class CountingStore:
    def __init__(self) -> None:
        self.downloads: list[str] = []
        self.failures: set[str] = set()

    def download_model(self, s3_uri: str | None = None) -> bytes:
        assert s3_uri is not None
        if s3_uri in self.failures:
            raise ModelUnavailableError(f"download failed for {s3_uri}")
        self.downloads.append(s3_uri)
        return b"weights"


class UnavailableGateway:
    def ensure_model_loaded(self):
        raise ModelUnavailableError("unavailable")

    def predict(self, _image_array):
        raise AssertionError("predict must not run")


class NoLoadWeights:
    def ensure_loaded(self) -> None:
        return None


def _fused_box_score_0_3() -> list[np.ndarray]:
    box = np.array([[10.0, 10.0, 60.0, 60.0, 0.3]], dtype=np.float64)
    return [box.copy(), box.copy()]


def _wire_stub_detectors(gateway: YoloConvnextGateway) -> None:
    gateway._detector_lists_fn = lambda _image: _fused_box_score_0_3()
    gateway._classifier_probs_fn = lambda _batch: np.array([[0.1, 0.9]])


def test_recall_after_balanced_reuses_yolo_weights_without_extra_downloads(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()

    def yolo_builder(_payload: bytes):
        return object()

    def classifier_builder(_payload: bytes):
        return object(), {}

    shared = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )
    pool = GatewayPool(store, yolo_weights=shared)

    pool.get("yolo-convnext-balanced").ensure_model_loaded()
    assert len(store.downloads) == 5

    pool.get("yolo-convnext-recall").ensure_model_loaded()
    assert len(store.downloads) == 5
    assert pool.get("yolo-convnext-balanced") is not pool.get("yolo-convnext-recall")
    get_settings.cache_clear()


def test_one_unavailable_gateway_does_not_break_another():
    good = FakeModelGateway()
    pool = GatewayPool(
        gateway_factories={
            "two-stage-pt": lambda: UnavailableGateway(),
            "yolo-convnext-balanced": lambda: good,
        }
    )

    with pytest.raises(ModelUnavailableError):
        pool.get("two-stage-pt").ensure_model_loaded()

    assert pool.get("yolo-convnext-balanced").predict(None)[0]["label"] == "NOMBO"


def test_pooled_gateways_apply_fusion_conf_from_fusion_conf_by_id():
    pool = GatewayPool(yolo_weights=NoLoadWeights())  # type: ignore[arg-type]
    recall = pool.get("yolo-convnext-recall")
    balanced = pool.get("yolo-convnext-balanced")

    assert isinstance(recall, YoloConvnextGateway)
    assert isinstance(balanced, YoloConvnextGateway)
    assert recall.fusion_conf == FUSION_CONF_BY_ID["yolo-convnext-recall"] == 0.2
    assert balanced.fusion_conf == FUSION_CONF_BY_ID["yolo-convnext-balanced"] == 0.4

    _wire_stub_detectors(recall)
    _wire_stub_detectors(balanced)
    image = np.zeros((80, 100, 3), dtype=np.uint8)

    recall_rows = recall.predict(image)
    balanced_rows = balanced.predict(image)

    assert len(recall_rows) == 1
    assert balanced_rows == []


def test_pool_builds_fusion_v3_gateway():
    pool = GatewayPool(fusion_v3_weights=NoLoadWeights())  # type: ignore[arg-type]
    gateway = pool.get("yolo-fusion-v3")
    assert isinstance(gateway, YoloFusionV3Gateway)


def test_pool_builds_g5v2_gateway_with_separate_weights_and_fusion_conf():
    pool = GatewayPool(yolo_weights=NoLoadWeights())  # type: ignore[arg-type]
    gateway = pool.get(YOLO_G5V2_MOBILEVIT_ID)
    balanced = pool.get("yolo-convnext-balanced")

    assert isinstance(gateway, YoloConvnextGateway)
    assert gateway.fusion_conf == 0.4
    assert gateway.weights is not balanced.weights
    assert gateway.weights is pool._shared_g5v2_weights()


def test_balanced_before_g5v2_downloads_no_g5v2_artifacts(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()

    def yolo_builder(_payload: bytes):
        return object()

    def classifier_builder(_payload: bytes, s3_uri: str | None = None):
        return object(), {}

    shared = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )
    pool = GatewayPool(store, yolo_weights=shared)

    pool.get("yolo-convnext-balanced").ensure_model_loaded()
    settings = get_settings()
    g5v2_uris = {settings.yolo_g5v2_s3_uri, *g5v2_ensemble_s3_uri_list(settings)}
    assert not any(uri in store.downloads for uri in g5v2_uris)
    get_settings.cache_clear()


def test_g5v2_load_failure_leaves_balanced_usable(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    settings = get_settings()
    store.failures.add(settings.yolo_g5v2_s3_uri)

    def yolo_builder(_payload: bytes):
        return object()

    def classifier_builder(_payload: bytes, s3_uri: str | None = None):
        return object(), {}

    balanced_weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )
    pool = GatewayPool(store, yolo_weights=balanced_weights)

    with pytest.raises(ModelUnavailableError):
        pool.get(YOLO_G5V2_MOBILEVIT_ID).ensure_model_loaded()

    pool.get("yolo-convnext-balanced").ensure_model_loaded()
    assert balanced_weights.is_loaded
    get_settings.cache_clear()


def test_pool_builds_mobilevit_fusion_gateway_with_own_classifier(monkeypatch):
    monkeypatch.setenv(
        "YOLO_FUSION_MOBILEVIT_CLASSIFIER_S3_URI", "s3://narwal/models/v3/mvit.pt"
    )
    get_settings.cache_clear()
    pool = GatewayPool(fusion_v3_weights=NoLoadWeights())  # type: ignore[arg-type]
    gateway = pool.get("yolo-fusion-mobilevit")
    try:
        assert isinstance(gateway, YoloFusionV3Gateway)
        assert gateway.weights is not pool.get("yolo-fusion-v3").weights
        assert gateway.weights._classifier_s3_uri() == "s3://narwal/models/v3/mvit.pt"
    finally:
        get_settings.cache_clear()
