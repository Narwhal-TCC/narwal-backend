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
    assert first.label == "mine"
    second = detections[1]
    assert (second.x1, second.y1, second.x2, second.y2) == pytest.approx(
        (0.0, 48.0, 128.0, 144.0)
    )
    assert second.confidence == 0.42


def test_boxes_are_clamped_to_uploaded_image_bounds():
    raw = [(0.95, 0.95, 0.4, 0.4, 1.2)]

    detection = to_detections(raw, image_width=100, image_height=200)[0]

    assert (detection.x1, detection.y1) == (75.0, 150.0)
    assert (detection.x2, detection.y2) == (100.0, 200.0)
    assert detection.confidence == 1.0


def test_class_index_resolves_label_from_adapter_labels():
    raw = [(0.5, 0.5, 0.2, 0.2, 0.8, 1)]

    detection = to_detections(raw, 100, 100, labels=("mine", "debris"))[0]

    assert detection.label == "debris"
