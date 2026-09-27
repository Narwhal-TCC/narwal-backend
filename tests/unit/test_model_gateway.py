import numpy as np
import pytest

from app.core.errors import ModelUnavailableError
from app.services.model_gateway import FakeModelGateway, TwoStageTorchGateway


class _MissingObjectStore:
    def download_model(self, s3_uri: str | None = None) -> bytes:
        raise ModelUnavailableError(f"Model object {s3_uri} could not be downloaded")


class _CorruptObjectStore:
    def download_model(self, s3_uri: str | None = None) -> bytes:
        return b"not-a-torch-artifact"


def test_missing_model_object_raises_model_unavailable():
    gateway = TwoStageTorchGateway(store=_MissingObjectStore())

    with pytest.raises(ModelUnavailableError) as excinfo:
        gateway.ensure_model_loaded()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"
    assert excinfo.value.status_code == 503


def test_unloadable_model_artifact_raises_model_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_gateway._import_torch",
        lambda: pytest.importorskip("torch"),
    )
    gateway = TwoStageTorchGateway(store=_CorruptObjectStore())

    with pytest.raises(ModelUnavailableError) as excinfo:
        gateway.ensure_model_loaded()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"


def test_either_model_download_failure_is_model_unavailable():
    class PartialStore:
        def __init__(self) -> None:
            self.calls = 0

        def download_model(self, s3_uri: str | None = None) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"detector-ok"
            raise ModelUnavailableError("classifier missing")

    gateway = TwoStageTorchGateway(store=PartialStore())
    with pytest.raises(ModelUnavailableError) as excinfo:
        gateway.ensure_model_loaded()
    assert excinfo.value.code == "MODEL_UNAVAILABLE"


def test_fake_gateway_predicts_deterministic_raw_output():
    gateway = FakeModelGateway()

    first = gateway.predict(image_array=None)
    second = gateway.predict(image_array=None)

    assert first == second == [
        {
            "x1": 240.0,
            "y1": 120.0,
            "x2": 400.0,
            "y2": 360.0,
            "detector_score": 0.9,
            "label": "NOMBO",
            "confidence": 0.9,
        }
    ]
    assert gateway.loaded is True


def test_fake_gateway_can_return_no_detections():
    gateway = FakeModelGateway(raw_output=[])

    assert gateway.predict(image_array=None) == []


def test_predict_with_stubbed_models_returns_stage_rows(monkeypatch):
    torch = pytest.importorskip("torch")

    class StubDetector:
        def eval(self):
            return self

        def __call__(self, images):
            boxes = torch.tensor([[10.0, 20.0, 30.0, 40.0]])
            scores = torch.tensor([0.87])
            return [{"boxes": boxes, "scores": scores}]

    class StubClassifier:
        def eval(self):
            return self

        def __call__(self, batch):
            # Softmax → prefer MILCO (index 0)
            return torch.tensor([[2.0, 0.1]])

    gateway = TwoStageTorchGateway(store=_MissingObjectStore())
    gateway._detector = StubDetector()
    gateway._classifier = StubClassifier()
    gateway._device = torch.device("cpu")

    image = np.zeros((80, 100, 3), dtype=np.uint8)
    rows = gateway.predict(image)

    assert len(rows) == 1
    assert rows[0]["label"] == "MILCO"
    assert rows[0]["detector_score"] == pytest.approx(0.87)
    assert rows[0]["confidence"] == pytest.approx(float(torch.softmax(torch.tensor([2.0, 0.1]), dim=0)[0]))
    assert (rows[0]["x1"], rows[0]["y1"], rows[0]["x2"], rows[0]["y2"]) == (
        10.0,
        20.0,
        30.0,
        40.0,
    )


def test_predict_empty_boxes_returns_empty_list(monkeypatch):
    torch = pytest.importorskip("torch")

    class EmptyDetector:
        def eval(self):
            return self

        def __call__(self, images):
            return [
                {
                    "boxes": torch.zeros((0, 4)),
                    "scores": torch.zeros((0,)),
                }
            ]

    class UnusedClassifier:
        def eval(self):
            return self

        def __call__(self, batch):  # pragma: no cover
            raise AssertionError("classifier must not run when detector is empty")

    gateway = TwoStageTorchGateway(store=_MissingObjectStore())
    gateway._detector = EmptyDetector()
    gateway._classifier = UnusedClassifier()
    gateway._device = torch.device("cpu")

    assert gateway.predict(np.zeros((40, 40, 3), dtype=np.uint8)) == []
