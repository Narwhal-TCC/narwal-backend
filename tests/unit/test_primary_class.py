from typing import Literal

from app.schemas.analysis import Detection
from app.services.primary_class import compute_primary_class, count_milco

DetectionLabel = Literal["MILCO", "NOMBO"]


def _detection(label: DetectionLabel, confidence: float) -> Detection:
    return Detection(
        x1=0.0,
        y1=0.0,
        x2=10.0,
        y2=10.0,
        confidence=confidence,
        label=label,
        detector_score=confidence,
    )


def test_empty_detections_yield_null_primary_class():
    assert compute_primary_class([]) is None
    assert count_milco([]) == 0


def test_any_milco_detection_sets_primary_class_to_milco():
    detections = [
        _detection("NOMBO", 0.95),
        _detection("MILCO", 0.1),
    ]

    assert compute_primary_class(detections) == "MILCO"
    assert count_milco(detections) == 1


def test_no_milco_uses_highest_confidence_nombo():
    detections = [
        _detection("NOMBO", 0.4),
        _detection("NOMBO", 0.9),
    ]

    assert compute_primary_class(detections) == "NOMBO"
    assert count_milco(detections) == 0


def test_equal_confidence_tie_breaks_to_first_in_list_order():
    detections = [
        _detection("NOMBO", 0.8),
        _detection("NOMBO", 0.8),
    ]

    assert compute_primary_class(detections) == "NOMBO"
