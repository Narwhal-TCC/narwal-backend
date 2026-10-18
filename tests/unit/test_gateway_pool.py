import pytest

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.services.gateway_pool import GatewayPool
from app.services.model_gateway import FakeModelGateway
from app.services.yolo_convnext import YoloConvnextWeights


class CountingStore:
    def __init__(self) -> None:
        self.downloads: list[str] = []

    def download_model(self, s3_uri: str | None = None) -> bytes:
        assert s3_uri is not None
        self.downloads.append(s3_uri)
        return b"weights"


class UnavailableGateway:
    def ensure_model_loaded(self):
        raise ModelUnavailableError("unavailable")

    def predict(self, _image_array):
        raise AssertionError("predict must not run")


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
