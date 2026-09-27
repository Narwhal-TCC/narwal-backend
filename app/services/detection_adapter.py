from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from app.schemas.analysis import Detection, DetectionLabel

DEFAULT_LABEL = "NOMBO"
DEFAULT_LABELS = ("MILCO", "NOMBO")
CLASSIFIER_POSITIVE_LABEL: DetectionLabel = "MILCO"
CLASSIFIER_NEGATIVE_LABEL: DetectionLabel = "NOMBO"
CLASSIFIER_THRESHOLD = 0.5


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _label_for(row: Sequence, labels: Sequence[str]) -> str:
    if len(row) < 6:
        return DEFAULT_LABEL
    class_index = int(row[5])
    if 0 <= class_index < len(labels):
        return labels[class_index]
    return DEFAULT_LABEL


def _classifier_score(raw: Any) -> float | None:
    """Return a sigmoid score when ``raw`` is a single scalar tensor, else ``None``."""
    try:
        values = np.asarray(raw, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if values.size != 1:
        return None
    return float(values[0])


def _from_classifier_score(
    score: float,
    image_width: int,
    image_height: int,
) -> list[Detection]:
    """Map a whole-image binary classifier score to one full-frame detection."""
    positive = score >= CLASSIFIER_THRESHOLD
    label: DetectionLabel = CLASSIFIER_POSITIVE_LABEL if positive else CLASSIFIER_NEGATIVE_LABEL
    confidence = score if positive else (1.0 - score)
    return [
        Detection(
            x1=0.0,
            y1=0.0,
            x2=float(image_width),
            y2=float(image_height),
            confidence=_clamp(confidence, 0.0, 1.0),
            label=label,
            detector_score=_clamp(confidence, 0.0, 1.0),
        )
    ]


def to_detections(
    raw: Any,
    image_width: int,
    image_height: int,
    labels: Sequence[str] = DEFAULT_LABELS,
) -> list[Detection]:
    """Map model output to canonical detections.

    Supports:

    - Binary classifier score (shape ``(1,)`` / ``(1, 1)`` / nested scalar) from
      ``MobileNetV2_fase_congelada.keras`` → one full-image box.
    - YOLO-like rows ``(x_center, y_center, width, height, confidence[, class_index])``
      with box values normalized to 0..1 → pixel boxes on the uploaded image using
      half-open intervals ``[x1, x2)`` × ``[y1, y2)``.
    """
    if raw is None:
        return []

    score = _classifier_score(raw)
    if score is not None:
        return _from_classifier_score(score, image_width, image_height)

    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return []

    rows = list(raw)
    if not rows:
        return []

    detections: list[Detection] = []
    for row in rows:
        x_center, y_center, width, height, confidence = (float(value) for value in row[:5])
        detections.append(
            Detection(
                x1=_clamp((x_center - width / 2) * image_width, 0.0, float(image_width)),
                y1=_clamp((y_center - height / 2) * image_height, 0.0, float(image_height)),
                x2=_clamp((x_center + width / 2) * image_width, 0.0, float(image_width)),
                y2=_clamp((y_center + height / 2) * image_height, 0.0, float(image_height)),
                confidence=_clamp(confidence, 0.0, 1.0),
                label=_label_for(row, labels),
                detector_score=_clamp(confidence, 0.0, 1.0),
            )
        )
    return detections
