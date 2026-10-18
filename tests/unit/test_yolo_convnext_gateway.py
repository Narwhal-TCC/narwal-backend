import numpy as np
import pytest
from PIL import Image

from app.services.yolo_convnext import YoloConvnextGateway, YoloConvnextWeights


class NoLoadWeights:
    def ensure_loaded(self) -> None:
        return None


def _box(score: float) -> np.ndarray:
    return np.array([[10.0, 10.0, 60.0, 60.0, score]], dtype=np.float64)


def _gateway(fusion_conf: float, detector_lists, classifier_probs):
    return YoloConvnextGateway(
        NoLoadWeights(),  # type: ignore[arg-type]
        fusion_conf,
        detector_lists_fn=lambda _image: detector_lists,
        classifier_probs_fn=classifier_probs,
    )


def test_milco_when_mean_prob_at_threshold():
    gateway = _gateway(
        0.4,
        [_box(0.9), _box(0.9)],
        lambda _batch: np.array([[0.6, 0.4]]),
    )
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert rows[0]["label"] == "MILCO"
    assert rows[0]["confidence"] == pytest.approx(0.6)


def test_nombo_when_mean_prob_just_below_threshold():
    gateway = _gateway(
        0.4,
        [_box(0.9), _box(0.9)],
        lambda _batch: np.array([[0.5999, 0.4001]]),
    )
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert rows[0]["label"] == "NOMBO"
    assert rows[0]["confidence"] == pytest.approx(0.4001)


def test_confidence_is_probability_of_emitted_label():
    gateway = _gateway(
        0.4,
        [_box(0.9), _box(0.9)],
        lambda _batch: np.array([[0.85, 0.15]]),
    )
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert rows[0]["label"] == "MILCO"
    assert rows[0]["confidence"] == pytest.approx(0.85)


def test_fusion_conf_filters_low_score_boxes():
    lists = [_box(0.3), _box(0.3)]
    recall = _gateway(0.2, lists, lambda _batch: np.array([[0.1, 0.9]]))
    balanced = _gateway(0.4, lists, lambda _batch: np.array([[0.1, 0.9]]))
    assert len(recall.predict(np.zeros((80, 100, 3), dtype=np.uint8))) == 1
    assert balanced.predict(np.zeros((80, 100, 3), dtype=np.uint8)) == []


def test_empty_detector_output_returns_no_rows():
    gateway = _gateway(
        0.4,
        [np.zeros((0, 5)), np.zeros((0, 5))],
        lambda _batch: np.array([]),
    )
    assert gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8)) == []


def test_grayscale_input_is_converted_to_rgb():
    seen: dict[str, tuple[int, int]] = {}

    def capture_image(_image: Image.Image):
        seen["size"] = _image.size
        return [_box(0.9), _box(0.9)]

    gateway = YoloConvnextGateway(
        NoLoadWeights(),  # type: ignore[arg-type]
        0.4,
        detector_lists_fn=capture_image,
        classifier_probs_fn=lambda _batch: np.array([[0.9, 0.1]]),
    )
    gateway.predict(np.zeros((80, 100), dtype=np.uint8))
    assert seen["size"] == (100, 80)


def test_predict_is_deterministic_for_same_input():
    gateway = _gateway(
        0.4,
        [_box(0.9), _box(0.9)],
        lambda _batch: np.array([[0.75, 0.25]]),
    )
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    first = gateway.predict(image)
    second = gateway.predict(image)
    assert first == second
