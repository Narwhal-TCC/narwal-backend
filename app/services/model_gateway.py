from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore

DEFAULT_FAKE_STAGE_OUTPUT: tuple[dict, ...] = (
    {
        "x1": 240.0,
        "y1": 120.0,
        "x2": 400.0,
        "y2": 360.0,
        "detector_score": 0.9,
        "label": "NOMBO",
        "confidence": 0.9,
    },
)


class ModelGateway(Protocol):
    def ensure_model_loaded(self) -> Any: ...

    def predict(self, image_array: Any) -> Any: ...


def _import_torch():
    try:
        import torch
    except ImportError as exc:
        raise ModelUnavailableError("PyTorch runtime is not installed") from exc
    return torch


class TwoStageTorchGateway:
    """Loads RetinaNet + fusion classifier from object storage and runs detect→classify."""

    def __init__(self, store: S3ObjectStore | None = None) -> None:
        self.store = store or S3ObjectStore()
        self._detector: Any | None = None
        self._classifier: Any | None = None
        self._device: Any | None = None

    def ensure_model_loaded(self) -> Any:
        if self._detector is None or self._classifier is None:
            self._load_models()
        return self._detector

    def predict(self, image_array: Any) -> list[dict]:
        torch = _import_torch()
        from torchvision.transforms import functional as TF
        from torchvision import transforms as T

        from app.services.two_stage_models import (
            CLASS_NAMES,
            CROP_MARGIN,
            FUSION_IMG_SIZE,
        )

        self.ensure_model_loaded()
        assert self._detector is not None and self._classifier is not None
        assert self._device is not None

        array = np.asarray(image_array)
        if array.ndim != 3 or array.shape[-1] != 3:
            raise ModelUnavailableError("Model expects an HWC RGB image array")
        if array.dtype != np.uint8:
            array = np.clip(array, 0, 255).astype(np.uint8)

        image = Image.fromarray(array, mode="RGB")
        width, height = image.size
        device = self._device

        self._detector.eval()
        self._classifier.eval()

        transform_cls = T.Compose(
            [
                T.Resize((FUSION_IMG_SIZE, FUSION_IMG_SIZE)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

        with torch.no_grad():
            img_tensor = TF.to_tensor(image).to(device)
            try:
                pred = self._detector([img_tensor])[0]
            except Exception as exc:
                raise ModelUnavailableError("Detector inference failed") from exc

            boxes = pred["boxes"].detach().cpu().numpy()
            scores = pred["scores"].detach().cpu().numpy()

            score_threshold = get_settings().detector_score_threshold
            results: list[dict] = []
            for box, score in zip(boxes, scores, strict=False):
                if float(score) < score_threshold:
                    continue
                xmin, ymin, xmax, ymax = (float(v) for v in box)
                bw, bh = xmax - xmin, ymax - ymin
                xmin_m = max(0.0, xmin - bw * CROP_MARGIN)
                ymin_m = max(0.0, ymin - bh * CROP_MARGIN)
                xmax_m = min(float(width), xmax + bw * CROP_MARGIN)
                ymax_m = min(float(height), ymax + bh * CROP_MARGIN)

                crop = image.crop((xmin_m, ymin_m, xmax_m, ymax_m))
                crop_tensor = transform_cls(crop).unsqueeze(0).to(device)
                try:
                    logits = self._classifier(crop_tensor)
                    probs = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()
                except Exception as exc:
                    raise ModelUnavailableError("Classifier inference failed") from exc

                class_idx = int(np.argmax(probs))
                label = CLASS_NAMES[class_idx]
                results.append(
                    {
                        "x1": xmin,
                        "y1": ymin,
                        "x2": xmax,
                        "y2": ymax,
                        "detector_score": float(score),
                        "label": label,
                        "confidence": float(probs[class_idx]),
                    }
                )
            return results

    def _load_models(self) -> None:
        torch = _import_torch()
        from app.services.two_stage_models import (
            FusionGhostNetV2MobileNetV2,
            build_retinanet,
        )

        settings = get_settings()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            detector_bytes = self.store.download_model(settings.detector_s3_uri)
            classifier_bytes = self.store.download_model(settings.classifier_s3_uri)
        except ModelUnavailableError:
            raise
        except Exception as exc:
            raise ModelUnavailableError("Model artifacts could not be downloaded") from exc

        try:
            detector = build_retinanet()
            classifier = FusionGhostNetV2MobileNetV2(pretrained=False)
            detector.load_state_dict(_load_state_dict(detector_bytes, torch))
            classifier.load_state_dict(_load_state_dict(classifier_bytes, torch))
        except Exception as exc:
            raise ModelUnavailableError("Model artifact could not be loaded") from exc

        self._detector = detector.to(device)
        self._classifier = classifier.to(device)
        self._device = device


def _load_state_dict(payload: bytes, torch: Any) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.pt"
        path.write_bytes(payload)
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError:
            state = torch.load(path, map_location="cpu")
        except Exception as exc:
            raise ModelUnavailableError("Model artifact could not be loaded") from exc
    if not isinstance(state, dict):
        raise ModelUnavailableError("Model artifact could not be loaded")
    # Some checkpoints wrap weights under "state_dict" / "model".
    if "state_dict" in state and isinstance(state["state_dict"], dict):
        return state["state_dict"]
    if "model" in state and isinstance(state["model"], dict):
        return state["model"]
    return state


class FakeModelGateway:
    """Deterministic gateway so tests and smoke runs need no PyTorch weights."""

    def __init__(self, raw_output: Sequence[dict] = DEFAULT_FAKE_STAGE_OUTPUT) -> None:
        self.raw_output = list(raw_output)
        self.loaded = False
        self.last_image_array: Any | None = None

    def ensure_model_loaded(self) -> Any:
        self.loaded = True
        return self

    def predict(self, image_array: Any) -> list[dict]:
        self.ensure_model_loaded()
        self.last_image_array = image_array
        return [dict(row) for row in self.raw_output]
