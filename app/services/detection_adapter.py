from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.schemas.analysis import Detection, DetectionLabel

DEFAULT_LABEL: DetectionLabel = "NOMBO"
CLASS_LABELS = frozenset({"MILCO", "NOMBO"})


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


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
    return detections
