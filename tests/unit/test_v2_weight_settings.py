import pytest

from app.bootstrap.seed import seed_v2_model_artifacts
from app.core.config import convnext_s3_uri_list, get_settings


def test_v2_s3_uri_defaults(monkeypatch):
    monkeypatch.delenv("YOLO_G5_S3_URI", raising=False)
    monkeypatch.delenv("YOLO_A_S3_URI", raising=False)
    monkeypatch.delenv("CONVNEXT_S3_URIS", raising=False)
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.yolo_g5_s3_uri == "s3://narwal/models/v2/G5_best.pt"
    assert settings.yolo_a_s3_uri == "s3://narwal/models/v2/yolo_a_best.pt"
    assert convnext_s3_uri_list(settings) == [
        "s3://narwal/models/v2/convnext_pico_224_s42.pt",
        "s3://narwal/models/v2/convnext_pico_224_s43.pt",
        "s3://narwal/models/v2/convnext_pico_224_s44.pt",
    ]
    get_settings.cache_clear()


def test_v2_s3_uri_env_override(monkeypatch):
    monkeypatch.setenv("YOLO_G5_S3_URI", "s3://custom/g5.pt")
    monkeypatch.setenv("YOLO_A_S3_URI", "s3://custom/yolo_a.pt")
    monkeypatch.setenv(
        "CONVNEXT_S3_URIS",
        "s3://custom/c42.pt,s3://custom/c43.pt,s3://custom/c44.pt",
    )
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.yolo_g5_s3_uri == "s3://custom/g5.pt"
    assert settings.yolo_a_s3_uri == "s3://custom/yolo_a.pt"
    assert convnext_s3_uri_list(settings) == [
        "s3://custom/c42.pt",
        "s3://custom/c43.pt",
        "s3://custom/c44.pt",
    ]
    get_settings.cache_clear()


def test_convnext_s3_uris_must_be_exactly_three(monkeypatch):
    monkeypatch.setenv("CONVNEXT_S3_URIS", "s3://narwal/a.pt,s3://narwal/b.pt")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="exactly three"):
        convnext_s3_uri_list()
    get_settings.cache_clear()


def test_seed_v2_uploads_each_present_local_file(tmp_path, monkeypatch):
    g5 = tmp_path / "G5_best.pt"
    yolo_a = tmp_path / "yolo_a_best.pt"
    c42 = tmp_path / "convnext_pico_224_s42.pt"
    c43 = tmp_path / "convnext_pico_224_s43.pt"
    c44 = tmp_path / "convnext_pico_224_s44.pt"
    for path in (g5, yolo_a, c42, c43, c44):
        path.write_bytes(b"weights")

    monkeypatch.setenv("YOLO_G5_LOCAL_PATH", str(g5))
    monkeypatch.setenv("YOLO_A_LOCAL_PATH", str(yolo_a))
    monkeypatch.setenv(
        "CONVNEXT_LOCAL_PATHS",
        f"{c42},{c43},{c44}",
    )
    get_settings.cache_clear()

    calls: list[tuple[str, str]] = []

    class CountingStore:
        def seed_model_if_missing(self, local_path, s3_uri):
            calls.append((str(local_path), s3_uri))
            return True

    seed_v2_model_artifacts(CountingStore())

    assert len(calls) == 5
    assert calls[0][1] == "s3://narwal/models/v2/G5_best.pt"
    assert calls[1][1] == "s3://narwal/models/v2/yolo_a_best.pt"
    assert [uri for _, uri in calls[2:]] == convnext_s3_uri_list()
    get_settings.cache_clear()
