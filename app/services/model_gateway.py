import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore

DEFAULT_FAKE_RAW_OUTPUT: tuple[Sequence, ...] = ((0.5, 0.5, 0.25, 0.5, 0.9),)


class ModelGateway(Protocol):
    def ensure_model_loaded(self) -> Any: ...

    def predict(self, image_array: Any) -> Any: ...


def _import_keras():
    try:
        import keras
    except ImportError:
        try:
            from tensorflow import keras
        except ImportError as exc:
            raise ModelUnavailableError("Keras runtime is not installed") from exc
    return keras


class KerasModelGateway:
    """Loads the `.keras` artifact from object storage once and keeps it in process memory."""

    def __init__(self, store: S3ObjectStore | None = None) -> None:
        self.store = store or S3ObjectStore()
        self._model: Any | None = None

    def ensure_model_loaded(self) -> Any:
        if self._model is None:
            self._model = self._load_model(self.store.download_model())
        return self._model

    def predict(self, image_array: Any) -> Any:
        return self.ensure_model_loaded().predict(image_array, verbose=0)

    @staticmethod
    def _load_model(payload: bytes) -> Any:
        keras = _import_keras()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.keras"
            path.write_bytes(payload)
            try:
                return keras.models.load_model(path)
            except Exception as exc:
                raise ModelUnavailableError("Model artifact could not be loaded") from exc


class FakeModelGateway:
    """Deterministic gateway so tests and smoke runs need no TensorFlow."""

    def __init__(self, raw_output: Sequence[Sequence] = DEFAULT_FAKE_RAW_OUTPUT) -> None:
        self.raw_output = raw_output
        self.loaded = False

    def ensure_model_loaded(self) -> Any:
        self.loaded = True
        return self

    def predict(self, image_array: Any) -> list[Sequence]:
        self.ensure_model_loaded()
        return [list(row) for row in self.raw_output]
