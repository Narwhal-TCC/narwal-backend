from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import convnext_s3_uri_list, get_settings
from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore

YoloBuilder = Callable[[bytes], Any]
ClassifierBuilder = Callable[[bytes], tuple[Any, dict]]


def _import_ultralytics_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ModelUnavailableError("YOLO runtime is not installed") from exc
    return YOLO


def default_yolo_builder(payload: bytes) -> Any:
    yolo_cls = _import_ultralytics_yolo()
    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as handle:
        handle.write(payload)
        path = handle.name
    try:
        return yolo_cls(path)
    finally:
        Path(path).unlink(missing_ok=True)


def build_convnext_classifier(payload: bytes) -> tuple[Any, dict]:
    torch = _import_torch()
    import timm
    import torch.nn as nn

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "classifier.pt"
        path.write_bytes(payload)
        try:
            ck = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError:
            ck = torch.load(path, map_location="cpu")
    if not isinstance(ck, dict) or "state_dict" not in ck or "cfg" not in ck:
        raise ModelUnavailableError("Model artifact could not be loaded")

    cfg = ck["cfg"]
    names = cfg["backbone"] if isinstance(cfg["backbone"], list) else [cfg["backbone"]]
    nc = 3 if cfg.get("fundo") else 2

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = nn.ModuleList(
                [timm.create_model(name, pretrained=False, num_classes=0) for name in names]
            )
            stats = []
            for backbone in self.backbone:
                dc = timm.data.resolve_data_config({}, model=backbone)
                stats.append(
                    (
                        torch.tensor(dc["mean"]).view(1, 3, 1, 1),
                        torch.tensor(dc["std"]).view(1, 3, 1, 1),
                    )
                )
            self.stats = stats
            with torch.no_grad():
                nf = sum(
                    b.eval()(torch.zeros(1, 3, 64, 64)).shape[1] for b in self.backbone
                )
            if len(names) == 1:
                self.head = nn.Sequential(nn.Dropout(0.0), nn.Linear(nf, nc))
            else:
                self.head = nn.Sequential(
                    nn.Linear(nf, 256),
                    nn.ReLU(inplace=True),
                    nn.Dropout(0.0),
                    nn.Linear(256, nc),
                )

        def forward(self, x: Any) -> Any:
            parts = [
                b((x - mu) / sd) for b, (mu, sd) in zip(self.backbone, self.stats, strict=True)
            ]
            return self.head(torch.cat(parts, 1))

    model = Net()
    state = {k: v.float() for k, v in ck["state_dict"].items()}
    model.load_state_dict(state)
    return model.eval(), cfg


def default_classifier_builder(payload: bytes) -> tuple[Any, dict]:
    return build_convnext_classifier(payload)


def _import_torch():
    try:
        import torch
    except ImportError as exc:
        raise ModelUnavailableError("PyTorch runtime is not installed") from exc
    return torch


class YoloConvnextWeights:
    """Downloads v2 artifacts once and builds two YOLO detectors plus three ConvNeXt classifiers."""

    def __init__(
        self,
        store: S3ObjectStore | None = None,
        *,
        yolo_builder: YoloBuilder | None = None,
        classifier_builder: ClassifierBuilder | None = None,
    ) -> None:
        self.store = store or S3ObjectStore()
        self._yolo_builder = yolo_builder or default_yolo_builder
        self._classifier_builder = classifier_builder or default_classifier_builder
        self._lock = threading.Lock()
        self._loaded = False
        self.yolo_g5: Any | None = None
        self.yolo_a: Any | None = None
        self.classifiers: list[Any] = []

    @property
    def is_loaded(self) -> bool:
        return self._loaded

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
                raise ModelUnavailableError("Model artifacts could not be loaded") from exc
            self._loaded = True

    def _clear(self) -> None:
        self._loaded = False
        self.yolo_g5 = None
        self.yolo_a = None
        self.classifiers = []

    def _load_all(self) -> None:
        settings = get_settings()
        g5_bytes = self.store.download_model(settings.yolo_g5_s3_uri)
        yolo_a_bytes = self.store.download_model(settings.yolo_a_s3_uri)
        convnext_bytes = [self.store.download_model(uri) for uri in convnext_s3_uri_list(settings)]

        self.yolo_g5 = self._yolo_builder(g5_bytes)
        self.yolo_a = self._yolo_builder(yolo_a_bytes)
        self.classifiers = [self._classifier_builder(payload)[0] for payload in convnext_bytes]


DetectorListsFn = Callable[[Any], list[Any]]
ClassifierProbsFn = Callable[[Any], Any]

G5_DETECTOR = {"imgsz": 1024, "iou_nms": 0.5, "augment": True}
YOLO_A_DETECTOR = {"imgsz": 640, "iou_nms": 0.5, "augment": True}
WBF_IOU = 0.55
POST_WBF_NMS_IOU = 0.5
DETECTOR_PREDICT_CONF = 0.001
CROP_MODE = "m0.15"
CLASSIFIER_SIZE = 224
MILCO_THRESHOLD = 0.6


class YoloConvnextGateway:
    def __init__(
        self,
        weights: YoloConvnextWeights,
        fusion_conf: float,
        *,
        detector_lists_fn: DetectorListsFn | None = None,
        classifier_probs_fn: ClassifierProbsFn | None = None,
    ) -> None:
        self.weights = weights
        self.fusion_conf = fusion_conf
        self._detector_lists_fn = detector_lists_fn
        self._classifier_probs_fn = classifier_probs_fn

    def ensure_model_loaded(self) -> Any:
        self.weights.ensure_loaded()
        return self.weights

    def predict(self, image_array: Any) -> list[dict[str, float | str]]:
        import numpy as np
        import torch
        from PIL import Image

        from app.services.yolo_convnext_math import caixa_recorte, nms, wbf

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

        if self._detector_lists_fn is not None:
            listas = self._detector_lists_fn(image)
        else:
            listas = self._run_yolo_detectors(image)

        detector_cfgs = (G5_DETECTOR, YOLO_A_DETECTOR)
        listas = [
            nms(np.asarray(boxes, dtype=np.float64), cfg["iou_nms"])
            for boxes, cfg in zip(listas, detector_cfgs, strict=True)
        ]
        fused = nms(wbf(listas, iou_thr=WBF_IOU), POST_WBF_NMS_IOU)
        if len(fused):
            fused = fused[fused[:, 4] >= self.fusion_conf]
        if len(fused) == 0:
            return []

        boxes = fused[:, :4]
        scores = fused[:, 4]
        crops = np.stack(
            [
                np.asarray(
                    image.crop(caixa_recorte(tuple(box), width, height, CROP_MODE)).resize(
                        (CLASSIFIER_SIZE, CLASSIFIER_SIZE), Image.BILINEAR
                    )
                )
                for box in boxes
            ]
        )
        batch = torch.from_numpy(crops).permute(0, 3, 1, 2).float() / 255.0
        probs = self._classifier_probabilities(batch)
        results: list[dict[str, float | str]] = []
        for box, detector_score, prob_row in zip(boxes, scores, probs, strict=True):
            p_milco = float(prob_row[0])
            p_nombo = float(prob_row[1])
            if p_milco >= MILCO_THRESHOLD:
                label = "MILCO"
                confidence = p_milco
            else:
                label = "NOMBO"
                confidence = p_nombo
            results.append(
                {
                    "x1": float(box[0]),
                    "y1": float(box[1]),
                    "x2": float(box[2]),
                    "y2": float(box[3]),
                    "detector_score": float(detector_score),
                    "label": label,
                    "confidence": confidence,
                }
            )
        return results

    def _run_yolo_detectors(self, image: Any) -> list[Any]:
        import numpy as np

        assert self.weights.yolo_g5 is not None and self.weights.yolo_a is not None
        configs = (G5_DETECTOR, YOLO_A_DETECTOR)
        models = (self.weights.yolo_g5, self.weights.yolo_a)
        listas: list[np.ndarray] = []
        for cfg, model in zip(configs, models, strict=True):
            result = model.predict(
                image,
                imgsz=cfg["imgsz"],
                conf=DETECTOR_PREDICT_CONF,
                iou=0.9,
                augment=cfg["augment"],
                device="cpu",
                verbose=False,
            )[0]
            if len(result.boxes):
                boxes = np.concatenate(
                    [result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()[:, None]],
                    axis=1,
                )
            else:
                boxes = np.zeros((0, 5))
            listas.append(boxes)
        return listas

    def _classifier_probabilities(self, batch: Any) -> Any:
        import numpy as np
        import torch

        if self._classifier_probs_fn is not None:
            return self._classifier_probs_fn(batch)

        assert self.weights.classifiers
        with torch.inference_mode():
            stacked = [
                torch.softmax(model(batch), dim=1).cpu().numpy()
                for model in self.weights.classifiers
            ]
        return np.mean(stacked, axis=0)
