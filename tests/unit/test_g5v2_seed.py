from app.bootstrap.seed import seed_g5v2_model_artifacts, seed_v2_model_artifacts
from app.core.config import (
    convnext_s3_uri_list,
    g5v2_ensemble_s3_uri_list,
    get_settings,
)


def test_seed_g5v2_uploads_seven_new_artifacts(tmp_path, monkeypatch):
    g5v2 = tmp_path / "G5_best_v2.pt"
    paths = [
        tmp_path / f"solo_convnext_pico_s4{i}.pt" for i in (2, 3, 4)
    ] + [tmp_path / f"solo_mobilevitv2_100_s4{i}.pt" for i in (2, 3, 4)]
    g5v2.write_bytes(b"g5v2")
    for path in paths:
        path.write_bytes(b"solo")

    monkeypatch.setenv("YOLO_G5V2_LOCAL_PATH", str(g5v2))
    monkeypatch.setenv(
        "YOLO_G5V2_ENSEMBLE_LOCAL_PATHS",
        ",".join(str(p) for p in paths),
    )
    get_settings.cache_clear()

    calls: list[tuple[str, str]] = []

    class CountingStore:
        def seed_model_if_missing(self, local_path, s3_uri):
            calls.append((str(local_path), s3_uri))
            return True

    seed_g5v2_model_artifacts(CountingStore())

    assert len(calls) == 7
    assert calls[0] == (str(g5v2), "s3://narwal/models/v2/G5_best_v2.pt")
    assert [uri for _, uri in calls[1:]] == g5v2_ensemble_s3_uri_list()
    get_settings.cache_clear()


def test_seed_v2_unchanged_after_g5v2_settings_present(tmp_path, monkeypatch):
    g5 = tmp_path / "G5_best.pt"
    yolo_a = tmp_path / "yolo_a_best.pt"
    c42 = tmp_path / "convnext_pico_224_s42.pt"
    c43 = tmp_path / "convnext_pico_224_s43.pt"
    c44 = tmp_path / "convnext_pico_224_s44.pt"
    for path in (g5, yolo_a, c42, c43, c44):
        path.write_bytes(b"weights")

    monkeypatch.setenv("YOLO_G5_LOCAL_PATH", str(g5))
    monkeypatch.setenv("YOLO_A_LOCAL_PATH", str(yolo_a))
    monkeypatch.setenv("CONVNEXT_LOCAL_PATHS", f"{c42},{c43},{c44}")
    get_settings.cache_clear()

    calls: list[tuple[str, str]] = []

    class CountingStore:
        def seed_model_if_missing(self, local_path, s3_uri):
            calls.append((str(local_path), s3_uri))
            return True

    seed_v2_model_artifacts(CountingStore())

    assert len(calls) == 5
    assert calls[0][1] == "s3://narwal/models/v2/G5_best.pt"
    assert [uri for _, uri in calls[2:]] == convnext_s3_uri_list()
    get_settings.cache_clear()
