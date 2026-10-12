from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.schemas.analysis import Detection, DetectionLabel

DEFAULT_LABEL: DetectionLabel = "NOMBO"
CLASS_LABELS = frozenset({"MILCO", "NOMBO"})
# RetinaNet NMS is per class. The same contact can clear the score threshold as both
# MILCO and NOMBO, and the fusion classifier then labels both crops. 0.5 matches
# torchvision's default nms_thresh, applied without regard to the detector class.
OVERLAP_IOU_THRESHOLD = 0.5


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def box_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if intersection == 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def kept_box_indices(
    boxes: Sequence[tuple[float, float, float, float]],
    scores: Sequence[float],
    iou_threshold: float = OVERLAP_IOU_THRESHOLD,
) -> list[int]:
    """Class-agnostic NMS. Higher score wins; equal scores keep the earlier box."""
    order = sorted(range(len(boxes)), key=lambda index: (-scores[index], index))
    kept: list[int] = []
    for index in order:
        if all(box_iou(boxes[index], boxes[other]) <= iou_threshold for other in kept):
            kept.append(index)
    kept.sort()
    return kept


def suppress_overlapping(
    detections: Sequence[Detection],
    iou_threshold: float = OVERLAP_IOU_THRESHOLD,
) -> list[Detection]:
    if len(detections) < 2:
        return list(detections)
    boxes = [(item.x1, item.y1, item.x2, item.y2) for item in detections]
    scores = [item.detector_score for item in detections]
    return [detections[index] for index in kept_box_indices(boxes, scores, iou_threshold)]


def _as_label(value: Any) -> DetectionLabel:
    if isinstance(value, str) and value in CLASS_LABELS:
        return value  # type: ignore[return-value]
    return DEFAULT_LABEL


def _from_stage_row(
    row: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> Detection:
    x1 = _clamp(float(row["x1"]), 0.0, float(image_width))
    y1 = _clamp(float(row["y1"]), 0.0, float(image_height))
    x2 = _clamp(float(row["x2"]), 0.0, float(image_width))
    y2 = _clamp(float(row["y2"]), 0.0, float(image_height))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return Detection(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        confidence=_clamp(float(row["confidence"]), 0.0, 1.0),
        label=_as_label(row.get("label")),
        detector_score=_clamp(float(row["detector_score"]), 0.0, 1.0),
    )


def to_detections(
    raw: Any,
    image_width: int,
    image_height: int,
    labels: Sequence[str] | None = None,  # noqa: ARG001 - kept for call-site compat
) -> list[Detection]:
    """Map two-stage gateway output to canonical detections.

    Expects an iterable of mappings with pixel boxes and scores::

        {x1, y1, x2, y2, detector_score, label, confidence}

    Empty / ``None`` input yields ``[]``.
    """
    del labels  # unused; labels come from each stage row
    if raw is None:
        return []

    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, Mapping)):
        return []

    rows = list(raw)
    if not rows:
        return []

    detections: list[Detection] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        required = ("x1", "y1", "x2", "y2", "detector_score", "confidence")
        if any(key not in row for key in required):
            continue
        detections.append(_from_stage_row(row, image_width, image_height))
    return suppress_overlapping(detections)
