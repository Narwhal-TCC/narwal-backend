import pytest

from app.core.errors import ModelUnavailableError
from app.services.model_gateway import FakeModelGateway, KerasModelGateway


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


def test_keras_gateway_loads_artifact_and_predicts_with_mocked_runtime(monkeypatch):
    class FakeModel:
        def predict(self, image_array, verbose=0):
            self.last_input = image_array
            return [[0.5, 0.5, 0.25, 0.5, 0.88]]

    class FakeKeras:
        class models:
            @staticmethod
            def load_model(_path):
                return FakeModel()

    monkeypatch.setattr("app.services.model_gateway._import_keras", lambda: FakeKeras)
    gateway = KerasModelGateway(store=_ArtifactObjectStore())
    model = gateway.ensure_model_loaded()

    raw = gateway.predict([[1, 2, 3]])

    assert raw == [[0.5, 0.5, 0.25, 0.5, 0.88]]
    assert model.last_input == [[1, 2, 3]]


def test_fake_gateway_predicts_deterministic_raw_output():
    gateway = FakeModelGateway()

    first = gateway.predict(image_array=None)
    second = gateway.predict(image_array=None)

    assert first == second == [[0.5, 0.5, 0.25, 0.5, 0.9]]
    assert gateway.loaded is True


def test_fake_gateway_can_return_no_detections():
    gateway = FakeModelGateway(raw_output=[])

    assert gateway.predict(image_array=None) == []
