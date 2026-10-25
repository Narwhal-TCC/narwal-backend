from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore
from app.services.yolo_convnext import default_yolo_builder
from app.services.yolo_fusion_v3_models import (
    FUSION_V3_CLASS_NAMES,
    FUSION_V3_IMG_SIZE,
    build_crop_fusion_classifier,
)

YoloBuilder = Callable[[bytes], Any]
ClassifierBuilder = Callable[[bytes], Any]


def default_fusion_v3_classifier_builder(payload: bytes) -> Any:
    torch = _import_torch()
    import io

    try:
        state = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)
    except TypeError:
        state = torch.load(io.BytesIO(payload), map_location="cpu")
    if not isinstance(state, dict):
        raise ModelUnavailableError("Fusion v3 classifier artifact could not be loaded")
    return build_crop_fusion_classifier(state)


def _import_torch():
    try:
        import torch
    except ImportError as exc:
        raise ModelUnavailableError("PyTorch runtime is not installed") from exc
    return torch


class YoloFusionV3Weights:
    """YOLO Model A + fusao_edgenext_small crop classifier (main branch notebooks)."""

    def __init__(
        self,
        store: S3ObjectStore | None = None,
        *,
        yolo_builder: YoloBuilder | None = None,
        classifier_builder: ClassifierBuilder | None = None,
    ) -> None:
        self.store = store or S3ObjectStore()
        self._yolo_builder = yolo_builder or default_yolo_builder
        self._classifier_builder = classifier_builder or default_fusion_v3_classifier_builder
        self._lock = threading.Lock()
        self._loaded = False
        self.yolo: Any | None = None
        self.classifier: Any | None = None

    def ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded:
                return
            try:
                self._load_all()
            except ModelUnavailableError:
                self._clear()
                raise
            except Exception as exc:
                self._clear()
                message = "Fusion v3 model artifacts could not be loaded"
                raise ModelUnavailableError(message) from exc
            self._loaded = True

    def _clear(self) -> None:
        self._loaded = False
        self.yolo = None
        self.classifier = None

    def _load_all(self) -> None:
        settings = get_settings()
        yolo_bytes = self.store.download_model(settings.yolo_a_s3_uri)
        classifier_bytes = self.store.download_model(settings.yolo_fusion_v3_classifier_s3_uri)
        self.yolo = self._yolo_builder(yolo_bytes)
        self.classifier = self._classifier_builder(classifier_bytes)


class YoloFusionV3Gateway:
    """YOLO detect → margin crop → ConvNeXt+EdgeNeXt fusion classify (notebook §11)."""

    def __init__(
        self,
        weights: YoloFusionV3Weights,
        *,
        yolo_predict_fn: Callable[[Any, Any], list[Any]] | None = None,
        classifier_probs_fn: Callable[[Any], Any] | None = None,
        score_threshold: float | None = None,
        crop_margin: float = 0.15,
    ) -> None:
        self.weights = weights
        self._yolo_predict_fn = yolo_predict_fn
        self._classifier_probs_fn = classifier_probs_fn
        self._score_threshold = score_threshold
        self._crop_margin = crop_margin

    def ensure_model_loaded(self) -> Any:
        self.weights.ensure_loaded()
        return self.weights

    def predict(self, image_array: Any) -> list[dict[str, float | str]]:
        import numpy as np
        from PIL import Image
        from torchvision import transforms as T

        self.ensure_model_loaded()
        array = np.asarray(image_array)
        if array.ndim == 2:
            array = np.stack([array, array, array], axis=-1)
        elif array.ndim == 3 and array.shape[-1] == 4:
            array = array[..., :3]
        if array.ndim != 3 or array.shape[-1] != 3:
            raise ModelUnavailableError("Model expects an HWC RGB or grayscale image array")
        if array.dtype != np.uint8:
            array = np.clip(array, 0, 255).astype(np.uint8)

        image = Image.fromarray(array, mode="RGB")
        width, height = image.size
        threshold = (
            self._score_threshold
            if self._score_threshold is not None
            else get_settings().detector_score_threshold
        )

        if self._yolo_predict_fn is not None:
            boxes = self._yolo_predict_fn(image, threshold)
        else:
            boxes = self._run_yolo(image, threshold)

        if not boxes:
            return []

        transform = T.Compose(
            [
                T.Resize((FUSION_V3_IMG_SIZE, FUSION_V3_IMG_SIZE)),
                T.ToTensor(),
            ]
        )
        results: list[dict[str, float | str]] = []
        for xmin, ymin, xmax, ymax, detector_score in boxes:
            bw, bh = xmax - xmin, ymax - ymin
            xmin_m = max(0.0, xmin - bw * self._crop_margin)
            ymin_m = max(0.0, ymin - bh * self._crop_margin)
            xmax_m = min(float(width), xmax + bw * self._crop_margin)
            ymax_m = min(float(height), ymax + bh * self._crop_margin)
            crop = image.crop((xmin_m, ymin_m, xmax_m, ymax_m))
            batch = transform(crop).unsqueeze(0)
            probs = self._classifier_probabilities(batch)[0]
            class_index = int(np.argmax(probs))
            label = FUSION_V3_CLASS_NAMES[class_index]
            confidence = float(probs[class_index])
            results.append(
                {
                    "x1": float(xmin),
                    "y1": float(ymin),
                    "x2": float(xmax),
                    "y2": float(ymax),
                    "detector_score": float(detector_score),
                    "label": label,
                    "confidence": confidence,
                }
            )
        return results

    def _run_yolo(
        self, image: Any, threshold: float
    ) -> list[tuple[float, float, float, float, float]]:
        assert self.weights.yolo is not None
        output = self.weights.yolo.predict(
            image,
            conf=threshold,
            verbose=False,
        )[0]
        if not len(output.boxes):
            return []
        rows: list[tuple[float, float, float, float, float]] = []
        for box in output.boxes:
            xmin, ymin, xmax, ymax = box.xyxy[0].tolist()
            score = float(box.conf[0])
            rows.append((xmin, ymin, xmax, ymax, score))
        return rows

    def _classifier_probabilities(self, batch: Any) -> Any:
        import torch

        if self._classifier_probs_fn is not None:
            return self._classifier_probs_fn(batch)

        assert self.weights.classifier is not None
        with torch.inference_mode():
            logits = self.weights.classifier(batch)
            return torch.softmax(logits, dim=1).cpu().numpy()
