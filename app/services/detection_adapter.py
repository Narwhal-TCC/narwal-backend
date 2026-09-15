from collections.abc import Iterable, Sequence

from app.schemas.analysis import Detection

DEFAULT_LABEL = "NOMBO"
DEFAULT_LABELS = ("MILCO", "NOMBO")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _label_for(row: Sequence, labels: Sequence[str]) -> str:
    if len(row) < 6:
        return DEFAULT_LABEL
    class_index = int(row[5])
    if 0 <= class_index < len(labels):
        return labels[class_index]
    return DEFAULT_LABEL


def to_detections(
    raw: Iterable[Sequence] | None,
    image_width: int,
    image_height: int,
    labels: Sequence[str] = DEFAULT_LABELS,
) -> list[Detection]:
    """Map YOLO-like rows to canonical detections.

    Each row is ``(x_center, y_center, width, height, confidence[, class_index])`` with
    box values normalized to 0..1. Output boxes are pixel coordinates of the uploaded image
    using half-open intervals ``[x1, x2)`` × ``[y1, y2)`` (inclusive start, exclusive end).
    """
    if not raw:
        return []

    detections: list[Detection] = []
    for row in raw:
        x_center, y_center, width, height, confidence = (float(value) for value in row[:5])
        detections.append(
            Detection(
                x1=_clamp((x_center - width / 2) * image_width, 0.0, float(image_width)),
                y1=_clamp((y_center - height / 2) * image_height, 0.0, float(image_height)),
                x2=_clamp((x_center + width / 2) * image_width, 0.0, float(image_width)),
                y2=_clamp((y_center + height / 2) * image_height, 0.0, float(image_height)),
                confidence=_clamp(confidence, 0.0, 1.0),
                label=_label_for(row, labels),
            )
        )
    return detections
