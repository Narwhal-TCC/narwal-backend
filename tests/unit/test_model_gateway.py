import pytest

from app.core.errors import ModelUnavailableError
from app.services.model_gateway import FakeModelGateway, KerasModelGateway


class _MissingObjectStore:
    def download_model(self) -> bytes:
        raise ModelUnavailableError("Model object s3://narwal/model.keras could not be downloaded")


class _CorruptObjectStore:
    def download_model(self) -> bytes:
        return b"not-a-keras-artifact"


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


def test_fake_gateway_predicts_deterministic_raw_output():
    gateway = FakeModelGateway()

    first = gateway.predict(image_array=None)
    second = gateway.predict(image_array=None)

    assert first == second == [[0.5, 0.5, 0.25, 0.5, 0.9]]
    assert gateway.loaded is True


def test_fake_gateway_can_return_no_detections():
    gateway = FakeModelGateway(raw_output=[])

    assert gateway.predict(image_array=None) == []
