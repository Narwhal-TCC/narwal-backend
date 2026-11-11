import numpy as np
import pytest

from app.core.config import g5v2_ensemble_s3_uri_list, get_settings
from app.core.errors import ModelUnavailableError
from app.services.yolo_convnext import (
    CLASSIFIER_SIZE,
    CROP_MODE,
    DETECTOR_PREDICT_CONF,
    G5_DETECTOR,
    MILCO_THRESHOLD,
    POST_WBF_NMS_IOU,
    WBF_IOU,
    YOLO_A_DETECTOR,
    YoloConvnextGateway,
    YoloConvnextWeights,
)


class CountingStore:
    def __init__(self) -> None:
        self.downloads: list[str] = []
        self.failures: set[str] = set()

    def download_model(self, s3_uri: str | None = None) -> bytes:
        assert s3_uri is not None
        if s3_uri in self.failures:
            raise ModelUnavailableError(f"download failed for {s3_uri}")
        self.downloads.append(s3_uri)
        return f"bytes-for-{s3_uri}".encode()


def _stub_builders():
    yolo_calls: list[int] = []

    def yolo_builder(payload: bytes):
        yolo_calls.append(len(payload))
        return object()

    classifier_calls: list[tuple[int, str | None]] = []

    def classifier_builder(payload: bytes, s3_uri: str | None = None):
        classifier_calls.append((len(payload), s3_uri))
        return object(), {}

    return yolo_calls, classifier_calls, yolo_builder, classifier_builder


def test_g5v2_weights_download_eight_artifacts_never_old_g5(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    _, _, yolo_builder, classifier_builder = _stub_builders()
    settings = get_settings()
    weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
        g5_s3_uri=lambda: settings.yolo_g5v2_s3_uri,
        classifier_s3_uris=lambda: g5v2_ensemble_s3_uri_list(settings),
    )

    weights.ensure_loaded()
    weights.ensure_loaded()

    assert len(store.downloads) == 8
    assert len(set(store.downloads)) == 8
    assert settings.yolo_g5_s3_uri not in store.downloads
    assert settings.yolo_g5v2_s3_uri in store.downloads
    assert store.downloads.count(settings.yolo_g5v2_s3_uri) == 1
    get_settings.cache_clear()


def test_g5v2_classifier_download_failure_clears_and_retry_succeeds(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    settings = get_settings()
    failing_uri = g5v2_ensemble_s3_uri_list(settings)[0]
    store.failures.add(failing_uri)
    _, _, yolo_builder, classifier_builder = _stub_builders()
    weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
        g5_s3_uri=lambda: settings.yolo_g5v2_s3_uri,
        classifier_s3_uris=lambda: g5v2_ensemble_s3_uri_list(settings),
    )

    with pytest.raises(ModelUnavailableError):
        weights.ensure_loaded()
    assert not weights.is_loaded

    store.failures.clear()
    weights.ensure_loaded()
    assert weights.is_loaded
    get_settings.cache_clear()


def test_g5v2_gateway_pipeline_constants_match_balanced():
    gateway = YoloConvnextGateway(_PreloadedWeights(3), fusion_conf=0.4)
    assert gateway.fusion_conf == 0.4
    assert G5_DETECTOR == {"imgsz": 1024, "iou_nms": 0.5, "augment": True}
    assert YOLO_A_DETECTOR == {"imgsz": 640, "iou_nms": 0.5, "augment": True}
    assert WBF_IOU == 0.55
    assert POST_WBF_NMS_IOU == 0.5
    assert DETECTOR_PREDICT_CONF == 0.001
    assert CROP_MODE == "m0.15"
    assert CLASSIFIER_SIZE == 224
    assert MILCO_THRESHOLD == 0.6


class _PreloadedWeights:
    def __init__(self, classifier_count: int) -> None:
        self.classifiers = [object()] * classifier_count
        self.yolo_g5 = object()
        self.yolo_a = object()

    def ensure_loaded(self) -> None:
        return None


def test_g5v2_gateway_labels_milco_from_six_model_mean():
    gateway = YoloConvnextGateway(_PreloadedWeights(6), fusion_conf=0.4)

    box = np.array([[10.0, 10.0, 60.0, 60.0, 0.9]], dtype=np.float64)
    gateway._detector_lists_fn = lambda _image: [box.copy(), box.copy()]
    gateway._classifier_probs_fn = lambda _batch: np.array([[0.7, 0.3]])

    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert len(rows) == 1
    assert rows[0]["label"] == "MILCO"

    gateway._classifier_probs_fn = lambda _batch: np.array([[0.5, 0.5]])
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert rows[0]["label"] == "NOMBO"
