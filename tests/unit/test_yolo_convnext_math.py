import numpy as np

from app.services.yolo_convnext_math import caixa_recorte, iou, nms, wbf


def test_iou_identical_boxes_is_one():
    box = (10.0, 10.0, 50.0, 50.0)
    assert abs(iou(box, box) - 1.0) < 1e-6


def test_iou_disjoint_boxes_is_zero():
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_iou_partial_overlap_hand_computed():
    # Intersection 10x10 = 100; union 400 + 400 - 100 = 700
    assert abs(iou((0, 0, 20, 20), (10, 10, 30, 30)) - (100 / 700)) < 1e-6


def test_nms_keeps_higher_score_and_suppresses_overlap():
    boxes = np.array(
        [
            [0, 0, 10, 10, 0.9],
            [1, 1, 11, 11, 0.5],
            [50, 50, 60, 60, 0.8],
        ],
        dtype=np.float64,
    )
    kept = nms(boxes, 0.5)
    assert len(kept) == 2
    scores = sorted(kept[:, 4].tolist(), reverse=True)
    assert scores == [0.9, 0.8]


def test_wbf_merges_overlapping_detectors():
    det_a = np.array([[10, 10, 30, 30, 0.8]], dtype=np.float64)
    det_b = np.array([[12, 12, 32, 32, 0.6]], dtype=np.float64)
    fused = wbf([det_a, det_b], iou_thr=0.55)
    assert fused.shape == (1, 5)
    assert fused[0, 0] > 10 and fused[0, 2] > 30
    assert 0 < fused[0, 4] <= 0.8


def test_wbf_keeps_non_overlapping_boxes():
    det_a = np.array([[0, 0, 10, 10, 0.7]], dtype=np.float64)
    det_b = np.array([[50, 50, 60, 60, 0.6]], dtype=np.float64)
    fused = wbf([det_a, det_b], iou_thr=0.55)
    assert fused.shape == (2, 5)


def test_caixa_recorte_margin_clamped_to_image_bounds():
    # Box flush to top-left; 15% margin would go negative without clamp
    crop = caixa_recorte((0, 0, 10, 10), w=100, h=80, modo="m0.15")
    assert crop[0] == 0.0
    assert crop[1] == 0.0
    assert crop[2] <= 100
    assert crop[3] <= 80


def test_caixa_recorte_expands_by_fifteen_percent():
    crop = caixa_recorte((40, 40, 60, 60), w=200, h=200, modo="m0.15")
    # width 20 -> margin 3 each side
    assert crop == (37.0, 37.0, 63.0, 63.0)
