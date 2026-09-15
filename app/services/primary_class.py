from collections.abc import Sequence
from typing import Literal

from app.schemas.analysis import Detection

PrimaryClass = Literal["MILCO", "NOMBO"]


def count_milco(detections: Sequence[Detection]) -> int:
    return sum(1 for detection in detections if detection.label == "MILCO")


def compute_primary_class(detections: Sequence[Detection]) -> PrimaryClass | None:
    if not detections:
        return None
    if count_milco(detections) > 0:
        return "MILCO"
    best = max(detections, key=lambda detection: detection.confidence)
    return best.label
