import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import compare_models  # noqa: E402


def test_greedy_match_counts_iou_at_least_half_as_hit():
    gt = [(0.0, 0.0, 10.0, 10.0)]
    pred_hit = [(1.0, 1.0, 11.0, 11.0)]
    pred_miss = [(50.0, 50.0, 60.0, 60.0)]
    matched, false_alarms = compare_models.greedy_match(gt, pred_hit)
    assert matched == 1
    assert false_alarms == 0
    matched, false_alarms = compare_models.greedy_match(gt, pred_miss)
    assert matched == 0
    assert false_alarms == 1


def test_one_gt_matches_at_most_one_prediction():
    gt = [(0.0, 0.0, 100.0, 100.0)]
    preds = [
        (5.0, 5.0, 95.0, 95.0),
        (10.0, 10.0, 90.0, 90.0),
    ]
    matched, false_alarms = compare_models.greedy_match(gt, preds)
    assert matched == 1
    assert false_alarms == 1


def test_empty_ground_truth_counts_all_predictions_as_false_alarms():
    preds = [(0.0, 0.0, 1.0, 1.0), (2.0, 2.0, 3.0, 3.0)]
    metrics = compare_models.metrics_for_image("empty", [], preds)
    assert metrics.gt_mine_count == 0
    assert metrics.matched_mines == 0
    assert metrics.false_alarms == 2
    assert not metrics.contributes_to_recall


def test_aggregate_recall_excludes_empty_gt_images():
    rows = [
        compare_models.ImageComparisonMetrics("a", 2, 1, 0),
        compare_models.ImageComparisonMetrics("b", 0, 0, 3),
        compare_models.ImageComparisonMetrics("c", 1, 1, 0),
    ]
    assert compare_models.aggregate_recall(rows) == pytest.approx(2 / 3)
    assert compare_models.mean_false_alarms_per_image(rows) == pytest.approx(1.0)
