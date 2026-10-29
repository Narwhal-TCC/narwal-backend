from app.bootstrap.seed import seed_v3_fusion_model_artifacts


def test_v3_classifier_s3_default(monkeypatch):
    monkeypatch.delenv("YOLO_FUSION_V3_CLASSIFIER_S3_URI", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert (
        settings.yolo_fusion_v3_classifier_s3_uri
        == "s3://narwal/models/v3/fusao_edgenext_small_best.pt"
    )


def test_seed_v3_uploads_yolo_and_classifier(tmp_path, monkeypatch):
    yolo = tmp_path / "yolo_a_best.pt"
    classifier = tmp_path / "fusao.pt"
    yolo.write_bytes(b"yolo")
    classifier.write_bytes(b"cls")

    monkeypatch.setenv("YOLO_A_LOCAL_PATH", str(yolo))
    monkeypatch.setenv("YOLO_FUSION_V3_CLASSIFIER_LOCAL_PATH", str(classifier))
    from app.core.config import get_settings

    get_settings.cache_clear()

    calls: list[tuple[str, str]] = []

    class CountingStore:
        def seed_model_if_missing(self, local_path, s3_uri):
            calls.append((str(local_path), s3_uri))
            return True

    seed_v3_fusion_model_artifacts(CountingStore())
    assert len(calls) == 3
    assert calls[0][1] == "s3://narwal/models/v2/yolo_a_best.pt"
    assert calls[1][1] == "s3://narwal/models/v3/fusao_edgenext_small_best.pt"
    assert calls[2][1] == "s3://narwal/models/v3/clf_fusao_mobilevitv2_100_s42.pt"
