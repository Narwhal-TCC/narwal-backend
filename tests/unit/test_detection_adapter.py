import pytest

from app.services.detection_adapter import to_detections


def test_empty_raw_output_maps_to_empty_detections():
    assert to_detections([], image_width=640, image_height=480) == []
    assert to_detections(None, image_width=640, image_height=480) == []


def test_stage_rows_map_to_detections_with_detector_score():
    raw = [
        {
            "x1": 240.0,
            "y1": 120.0,
            "x2": 400.0,
            "y2": 360.0,
            "detector_score": 0.91,
            "label": "MILCO",
            "confidence": 0.88,
        },
        {
            "x1": 10.0,
            "y1": 20.0,
            "x2": 30.0,
            "y2": 40.0,
            "detector_score": 0.55,
            "label": "NOMBO",
            "confidence": 0.62,
        },
    ]

    detections = to_detections(raw, image_width=640, image_height=480)

    assert len(detections) == 2
    first = detections[0]
    assert (first.x1, first.y1, first.x2, first.y2) == (240.0, 120.0, 400.0, 360.0)
    assert first.confidence == 0.88
    assert first.detector_score == 0.91
    assert first.label == "MILCO"
    assert detections[1].label == "NOMBO"
    assert detections[1].detector_score == 0.55


def test_boxes_clamped_to_image_bounds():
    raw = [
        {
            "x1": -10.0,
            "y1": -5.0,
            "x2": 150.0,
            "y2": 250.0,
            "detector_score": 0.9,
            "label": "NOMBO",
            "confidence": 0.7,
        }
    ]

    detection = to_detections(raw, image_width=100, image_height=200)[0]

    assert (detection.x1, detection.y1) == (0.0, 0.0)
    assert (detection.x2, detection.y2) == (100.0, 200.0)
    assert detection.x1 < detection.x2
    assert detection.y1 < detection.y2


def test_unknown_label_falls_back_to_nombo():
    raw = [
        {
            "x1": 0.0,
            "y1": 0.0,
            "x2": 10.0,
            "y2": 10.0,
            "detector_score": 0.5,
            "label": "OTHER",
            "confidence": 0.5,
        }
    ]

    assert to_detections(raw, 100, 100)[0].label == "NOMBO"


def test_keras_scalar_and_yolo_rows_are_ignored():
    assert to_detections([[0.73]], 640, 480) == []
    assert to_detections([(0.5, 0.5, 0.25, 0.5, 0.9)], 640, 480) == []


def test_incomplete_stage_rows_are_skipped():
    raw = [{"x1": 0.0, "y1": 0.0, "confidence": 0.9}]
    assert to_detections(raw, 100, 100) == []


def test_overlapping_boxes_collapse_to_the_stronger_proposal():
    raw = [
        {
            "x1": 148.9163055419922,
            "y1": 282.54498291015625,
            "x2": 166.50328063964844,
            "y2": 308.2796630859375,
            "detector_score": 0.7409245371818542,
            "label": "NOMBO",
            "confidence": 0.8330937623977661,
        },
        {
            "x1": 148.9770965576172,
            "y1": 281.77630615234375,
            "x2": 166.58802795410156,
            "y2": 308.5933532714844,
            "detector_score": 0.520520806312561,
            "label": "NOMBO",
            "confidence": 0.7268542051315308,
        },
    ]

    detections = to_detections(raw, image_width=640, image_height=480)

    assert len(detections) == 1
    assert detections[0].detector_score == pytest.approx(0.7409245371818542)
    assert detections[0].confidence == pytest.approx(0.8330937623977661)


def test_separated_boxes_are_both_kept():
    raw = [
        {
            "x1": 67.9,
            "y1": 365.6,
            "x2": 83.9,
            "y2": 375.3,
            "detector_score": 0.577,
            "label": "MILCO",
            "confidence": 0.971,
        },
        {
            "x1": 261.9,
            "y1": 106.5,
            "x2": 275.5,
            "y2": 120.4,
            "detector_score": 0.532,
            "label": "MILCO",
            "confidence": 0.910,
        },
    ]

    assert len(to_detections(raw, image_width=640, image_height=480)) == 2


def test_scores_clamped_to_unit_interval():
    raw = [
        {
            "x1": 0.0,
            "y1": 0.0,
            "x2": 10.0,
            "y2": 10.0,
            "detector_score": 1.2,
            "label": "MILCO",
            "confidence": -0.1,
        }
    ]

    detection = to_detections(raw, 100, 100)[0]
    assert detection.detector_score == pytest.approx(1.0)
    assert detection.confidence == pytest.approx(0.0)
