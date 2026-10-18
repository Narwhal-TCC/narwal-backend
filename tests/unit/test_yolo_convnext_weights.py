from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.services.yolo_convnext import YoloConvnextWeights


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

    classifier_calls: list[int] = []

    def classifier_builder(payload: bytes):
        classifier_calls.append(len(payload))
        return object(), {}

    return yolo_calls, classifier_calls, yolo_builder, classifier_builder


def test_ensure_loaded_downloads_five_artifacts_once(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    yolo_calls, cls_calls, yolo_builder, classifier_builder = _stub_builders()
    weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )

    weights.ensure_loaded()
    weights.ensure_loaded()

    assert len(store.downloads) == 5
    assert len(set(store.downloads)) == 5
    assert len(yolo_calls) == 2
    assert len(cls_calls) == 3
    assert weights.is_loaded
    get_settings.cache_clear()


def test_concurrent_first_load_downloads_each_file_once(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    _, _, yolo_builder, classifier_builder = _stub_builders()
    weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(weights.ensure_loaded) for _ in range(2)]
        for fut in futs:
            fut.result()

    assert len(store.downloads) == 5
    assert len(set(store.downloads)) == 5
    get_settings.cache_clear()


def test_load_failure_leaves_unloaded_and_retry_succeeds(monkeypatch):
    get_settings.cache_clear()
    store = CountingStore()
    settings = get_settings()
    store.failures.add(settings.yolo_a_s3_uri)
    _, _, yolo_builder, classifier_builder = _stub_builders()
    weights = YoloConvnextWeights(
        store,
        yolo_builder=yolo_builder,
        classifier_builder=classifier_builder,
    )

    with pytest.raises(ModelUnavailableError):
        weights.ensure_loaded()
    assert not weights.is_loaded

    assert store.downloads == [settings.yolo_g5_s3_uri]

    store.failures.clear()
    weights.ensure_loaded()
    assert weights.is_loaded
    assert len(store.downloads) == 6
    assert store.downloads.count(settings.yolo_g5_s3_uri) == 2
    get_settings.cache_clear()
