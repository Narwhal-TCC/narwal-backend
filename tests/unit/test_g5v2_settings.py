import pytest

from app.core.config import (
    g5v2_ensemble_local_path_list,
    g5v2_ensemble_s3_uri_list,
    get_settings,
)

ENSEMBLE_S3_DEFAULT = [
    "s3://narwal/models/v3/solo_convnext_pico_s42.pt",
    "s3://narwal/models/v3/solo_convnext_pico_s43.pt",
    "s3://narwal/models/v3/solo_convnext_pico_s44.pt",
    "s3://narwal/models/v3/solo_mobilevitv2_100_s42.pt",
    "s3://narwal/models/v3/solo_mobilevitv2_100_s43.pt",
    "s3://narwal/models/v3/solo_mobilevitv2_100_s44.pt",
]

ENSEMBLE_LOCAL_DEFAULT = [
    "data/models/v3/solo_convnext_pico_s42.pt",
    "data/models/v3/solo_convnext_pico_s43.pt",
    "data/models/v3/solo_convnext_pico_s44.pt",
    "data/models/v3/solo_mobilevitv2_100_s42.pt",
    "data/models/v3/solo_mobilevitv2_100_s43.pt",
    "data/models/v3/solo_mobilevitv2_100_s44.pt",
]


def test_g5v2_defaults_and_ensemble_order(monkeypatch):
    monkeypatch.delenv("YOLO_G5V2_LOCAL_PATH", raising=False)
    monkeypatch.delenv("YOLO_G5V2_S3_URI", raising=False)
    monkeypatch.delenv("YOLO_G5V2_ENSEMBLE_S3_URIS", raising=False)
    monkeypatch.delenv("YOLO_G5V2_ENSEMBLE_LOCAL_PATHS", raising=False)
    monkeypatch.delenv("YOLO_G5_LOCAL_PATH", raising=False)
    monkeypatch.delenv("YOLO_G5_S3_URI", raising=False)
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.yolo_g5v2_local_path == "data/models/v2/G5_best_v2.pt"
    assert settings.yolo_g5v2_s3_uri == "s3://narwal/models/v2/G5_best_v2.pt"
    assert g5v2_ensemble_s3_uri_list(settings) == ENSEMBLE_S3_DEFAULT
    assert g5v2_ensemble_local_path_list(settings) == ENSEMBLE_LOCAL_DEFAULT
    assert settings.yolo_g5_local_path == "data/models/v2/G5_best.pt"
    assert settings.yolo_g5_s3_uri == "s3://narwal/models/v2/G5_best.pt"
    get_settings.cache_clear()


def test_g5v2_ensemble_s3_uris_must_be_exactly_six(monkeypatch):
    monkeypatch.setenv(
        "YOLO_G5V2_ENSEMBLE_S3_URIS",
        "s3://narwal/a.pt,s3://narwal/b.pt",
    )
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="exactly six"):
        g5v2_ensemble_s3_uri_list()
    get_settings.cache_clear()
