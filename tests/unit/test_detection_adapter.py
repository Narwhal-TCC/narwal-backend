import numpy as np
import pytest

from app.services.detection_adapter import to_detections


def test_empty_raw_output_maps_to_empty_detections():
    assert to_detections([], image_width=640, image_height=480) == []


def test_yolo_like_rows_map_to_pixel_boxes_with_confidence():
    raw = [
        (0.5, 0.5, 0.25, 0.5, 0.9),
        (0.1, 0.2, 0.2, 0.2, 0.42),
    ]

    detections = to_detections(raw, image_width=640, image_height=480)

    assert len(detections) == 2
    first = detections[0]
    assert (first.x1, first.y1, first.x2, first.y2) == (240.0, 120.0, 400.0, 360.0)
    assert first.confidence == 0.9
    assert first.label == "NOMBO"
    second = detections[1]
    assert (second.x1, second.y1, second.x2, second.y2) == pytest.approx(
        (0.0, 48.0, 128.0, 144.0)
    )
    assert second.confidence == 0.42
    assert second.label == "NOMBO"


def test_boxes_use_half_open_pixel_intervals_clamped_to_image_bounds():
    raw = [(0.95, 0.95, 0.4, 0.4, 1.2)]

    detection = to_detections(raw, image_width=100, image_height=200)[0]

    # Half-open [x1, x2) × [y1, y2): exclusive ends may equal image width/height.
    assert (detection.x1, detection.y1) == (75.0, 150.0)
    assert (detection.x2, detection.y2) == (100.0, 200.0)
    assert detection.confidence == 1.0
    assert detection.x1 < detection.x2
    assert detection.y1 < detection.y2
    assert detection.label == "NOMBO"


def test_class_index_resolves_milco_and_nombo_from_default_labels():
    milco = to_detections([(0.5, 0.5, 0.2, 0.2, 0.8, 0)], 100, 100)[0]
    nombo = to_detections([(0.5, 0.5, 0.2, 0.2, 0.8, 1)], 100, 100)[0]

    assert milco.label == "MILCO"
    assert nombo.label == "NOMBO"


def test_unknown_or_missing_class_index_falls_back_to_nombo():
    missing_index = to_detections([(0.5, 0.5, 0.2, 0.2, 0.8)], 100, 100)[0]
    out_of_range = to_detections([(0.5, 0.5, 0.2, 0.2, 0.8, 99)], 100, 100)[0]

    assert missing_index.label == "NOMBO"
    assert out_of_range.label == "NOMBO"


def test_classifier_score_maps_to_full_image_milco_detection():
    detection = to_detections(np.array([[0.73]], dtype=np.float32), 640, 480)[0]

    assert (detection.x1, detection.y1, detection.x2, detection.y2) == (0.0, 0.0, 640.0, 480.0)
    assert detection.label == "MILCO"
    assert detection.confidence == pytest.approx(0.73)


def test_classifier_score_below_threshold_maps_to_nombo():
    detection = to_detections([[0.2]], 100, 50)[0]

    assert detection.label == "NOMBO"
    assert detection.confidence == pytest.approx(0.8)
    assert (detection.x1, detection.y1, detection.x2, detection.y2) == (0.0, 0.0, 100.0, 50.0)
