import numpy as np
import pytest

from app.core.errors import ModelUnavailableError
from app.services.model_gateway import (
    MODEL_INPUT_SIZE,
    FakeModelGateway,
    KerasModelGateway,
    preprocess_mobilenet_input,
)


class _MissingObjectStore:
    def download_model(self) -> bytes:
        raise ModelUnavailableError("Model object s3://narwal/model.keras could not be downloaded")


class _CorruptObjectStore:
    def download_model(self) -> bytes:
        return b"not-a-keras-artifact"


class _ArtifactObjectStore:
    def download_model(self) -> bytes:
        return b"fake-keras-bytes"


def test_missing_model_object_raises_model_unavailable():
    gateway = KerasModelGateway(store=_MissingObjectStore())

    with pytest.raises(ModelUnavailableError) as excinfo:
        gateway.ensure_model_loaded()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"
    assert excinfo.value.status_code == 503


def test_unloadable_model_artifact_raises_model_unavailable():
    gateway = KerasModelGateway(store=_CorruptObjectStore())

    with pytest.raises(ModelUnavailableError) as excinfo:
        gateway.ensure_model_loaded()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"


def test_preprocess_mobilenet_input_resizes_to_batched_float32():
    image = np.zeros((32, 416, 3), dtype=np.uint8)

    batch = preprocess_mobilenet_input(image)

    assert batch.shape == (1, MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, 3)
    assert batch.dtype == np.float32
    assert float(batch.min()) >= 0.0
    assert float(batch.max()) <= 255.0


def test_keras_gateway_loads_artifact_and_predicts_with_mocked_runtime(monkeypatch):
    class FakeModel:
        def predict(self, image_array, verbose=0):
            self.last_input = image_array
            return np.array([[0.73]], dtype=np.float32)

    class FakeKeras:
        class models:
            @staticmethod
            def load_model(_path):
                return FakeModel()

    monkeypatch.setattr("app.services.model_gateway._import_keras", lambda: FakeKeras)
    gateway = KerasModelGateway(store=_ArtifactObjectStore())
    model = gateway.ensure_model_loaded()

    raw = gateway.predict(np.zeros((32, 416, 3), dtype=np.uint8))

    assert np.allclose(raw, [[0.73]])
    assert model.last_input.shape == (1, MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, 3)
    assert model.last_input.dtype == np.float32


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
