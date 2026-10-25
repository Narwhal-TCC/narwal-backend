import numpy as np
import pytest

from app.services.yolo_fusion_v3 import YoloFusionV3Gateway, YoloFusionV3Weights


class NoLoadWeights(YoloFusionV3Weights):
    def ensure_loaded(self) -> None:
        return None


def _gateway(yolo_boxes, classifier_probs, threshold=0.5):
    def yolo_fn(_image, conf):
        assert conf == threshold
        return yolo_boxes

    return YoloFusionV3Gateway(
        NoLoadWeights(),  # type: ignore[arg-type]
        yolo_predict_fn=yolo_fn,
        classifier_probs_fn=lambda _batch: classifier_probs,
        score_threshold=threshold,
    )


def test_milco_when_argmax_index_zero():
    boxes = [(10.0, 10.0, 50.0, 50.0, 0.91)]
    gateway = _gateway(boxes, np.array([[0.88, 0.12]]))
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert len(rows) == 1
    assert rows[0]["label"] == "MILCO"
    assert rows[0]["confidence"] == pytest.approx(0.88)
    assert rows[0]["detector_score"] == pytest.approx(0.91)


def test_nombo_when_argmax_index_one():
    boxes = [(10.0, 10.0, 50.0, 50.0, 0.75)]
    gateway = _gateway(boxes, np.array([[0.4, 0.6]]))
    rows = gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8))
    assert rows[0]["label"] == "NOMBO"
    assert rows[0]["confidence"] == pytest.approx(0.6)


def test_empty_yolo_returns_no_detections():
    gateway = _gateway([], np.zeros((0, 2)))
    assert gateway.predict(np.zeros((80, 100, 3), dtype=np.uint8)) == []


def test_resolve_model_id_accepts_fusion_v3():
    from app.services.model_registry import resolve_model_id

    assert resolve_model_id("yolo-fusion-v3") == "yolo-fusion-v3"
