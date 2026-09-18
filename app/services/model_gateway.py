import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore

DEFAULT_FAKE_RAW_OUTPUT: tuple[Sequence, ...] = ((0.5, 0.5, 0.25, 0.5, 0.9),)
# MobileNetV2_fase_congelada.keras expects RGB floats in 0..255 at this spatial size.
MODEL_INPUT_SIZE = 96


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


def preprocess_mobilenet_input(image_array: Any) -> np.ndarray:
    """Resize HWC RGB to a batched ``(1, 96, 96, 3)`` float32 tensor in 0..255."""
    array = np.asarray(image_array)
    if array.ndim != 3 or array.shape[-1] != 3:
        raise ModelUnavailableError("Model expects an HWC RGB image array")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    image = Image.fromarray(array, mode="RGB").resize(
        (MODEL_INPUT_SIZE, MODEL_INPUT_SIZE),
        Image.Resampling.BILINEAR,
    )
    return np.expand_dims(np.asarray(image, dtype=np.float32), axis=0)


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
        batch = preprocess_mobilenet_input(image_array)
        return self.ensure_model_loaded().predict(batch, verbose=0)

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
        self.last_image_array: Any | None = None

    def ensure_model_loaded(self) -> Any:
        self.loaded = True
        return self

    def predict(self, image_array: Any) -> list[Sequence]:
        self.ensure_model_loaded()
        self.last_image_array = image_array
        return [list(row) for row in self.raw_output]
