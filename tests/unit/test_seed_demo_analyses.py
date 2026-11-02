from pathlib import Path

import pytest

from app.bootstrap.seed_demo_analyses import (
    detections_from_label_file,
    iter_labeled_samples,
    seed_analysis_id,
    simulated_position,
    yolo_line_to_detection,
)


def test_yolo_line_to_detection_converts_normalized_box():
    detection = yolo_line_to_detection(
        "0 0.5 0.5 0.2 0.1",
        image_width=1000,
        image_height=800,
    )
    assert detection.label == "MILCO"
    assert detection.x1 == pytest.approx(400.0)
    assert detection.y1 == pytest.approx(360.0)
    assert detection.x2 == pytest.approx(600.0)
    assert detection.y2 == pytest.approx(440.0)


def test_detections_from_label_file_reads_matching_jpg(tmp_path: Path):
    sample = Path(__file__).resolve().parents[2] / "data" / "2018" / "0036_2018.jpg"
    if not sample.is_file():
        pytest.skip("sample image missing")
    txt = tmp_path / "0036_2018.txt"
    txt.write_text("0 0.2907421875 0.761787109375 0.044921875 0.0341796875\n", encoding="utf-8")
    jpg = tmp_path / "0036_2018.jpg"
    jpg.write_bytes(sample.read_bytes())

    detections = detections_from_label_file(txt, jpg)
    assert len(detections) == 1
    assert detections[0].label == "MILCO"


def test_iter_labeled_samples_skips_empty_txt(tmp_path: Path):
    year_dir = tmp_path / "2018"
    year_dir.mkdir()
    (year_dir / "empty.txt").write_text("\n", encoding="utf-8")
    (year_dir / "empty.jpg").write_bytes(b"jpg")
    (year_dir / "hit.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (year_dir / "hit.jpg").write_bytes(b"jpg")

    stems = [txt.stem for txt, _ in iter_labeled_samples(tmp_path, ("2018",))]
    assert stems == ["hit"]


def test_seed_analysis_id_is_stable():
    assert seed_analysis_id("0036_2018") == seed_analysis_id("0036_2018")
    assert seed_analysis_id("0036_2018") != seed_analysis_id("0037_2018")


def test_simulated_position_stays_inside_campaign_box():
    lat, lon = simulated_position(
        "0036_2018",
        min_lat=38.60,
        max_lat=38.70,
        min_lon=-9.50,
        max_lon=-9.35,
    )
    assert 38.60 <= lat <= 38.70
    assert -9.50 <= lon <= -9.35
