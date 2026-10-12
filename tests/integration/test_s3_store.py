import pytest
from moto import mock_aws

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.repositories.s3_store import S3ObjectStore

BUCKET = "narwal-test"
DETECTOR_KEY = "models/v1/retinanet_melhor.pt"
CLASSIFIER_KEY = "models/v1/fusion_ghostnetv2_mobilenetv2_melhor.pt"


@pytest.fixture
def local_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.setenv("DETECTOR_S3_URI", f"s3://{BUCKET}/{DETECTOR_KEY}")
    monkeypatch.setenv("CLASSIFIER_S3_URI", f"s3://{BUCKET}/{CLASSIFIER_KEY}")
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


@pytest.fixture
def store(local_env):
    import boto3

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        object_store = S3ObjectStore(client=s3, bucket=BUCKET)
        object_store.ensure_bucket()
        yield object_store


def test_put_analysis_image_round_trip_returns_stored_bytes(store):
    key = store.put_analysis_image(
        org_id="org-1",
        analysis_id="an-1",
        ext="png",
        data=b"fake-png-bytes",
        content_type="image/png",
    )

    assert key == "analyses/org-1/an-1/original.png"
    stored = store.client.get_object(Bucket=BUCKET, Key=key)
    assert stored["Body"].read() == b"fake-png-bytes"
    assert stored["ContentType"] == "image/png"


def test_download_model_returns_object_bytes(store):
    store.client.put_object(Bucket=BUCKET, Key=DETECTOR_KEY, Body=b"pt-artifact")

    assert store.download_model() == b"pt-artifact"


def test_download_model_accepts_explicit_uri(store):
    store.client.put_object(Bucket=BUCKET, Key=CLASSIFIER_KEY, Body=b"fusion-bytes")
    uri = f"s3://{BUCKET}/{CLASSIFIER_KEY}"

    assert store.download_model(uri) == b"fusion-bytes"


def test_download_model_missing_key_raises_model_unavailable(store):
    with pytest.raises(ModelUnavailableError) as excinfo:
        store.download_model()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"
    assert excinfo.value.status_code == 503


def test_download_model_with_misconfigured_uri_raises_model_unavailable(local_env):
    local_env.setenv("DETECTOR_S3_URI", "")
    get_settings.cache_clear()
    with mock_aws():
        store = S3ObjectStore()

        with pytest.raises(ModelUnavailableError) as excinfo:
            store.download_model()

    assert excinfo.value.code == "MODEL_UNAVAILABLE"


def test_seed_model_if_missing_uploads_local_file(store, tmp_path):
    model_path = tmp_path / "retinanet_melhor.pt"
    model_path.write_bytes(b"pt-artifact")

    uploaded = store.seed_model_if_missing(model_path)

    assert uploaded is True
    stored = store.client.get_object(Bucket=BUCKET, Key=DETECTOR_KEY)
    assert stored["Body"].read() == b"pt-artifact"


def test_seed_dual_artifacts_to_distinct_keys(store, tmp_path):
    detector = tmp_path / "retinanet_melhor.pt"
    classifier = tmp_path / "fusion.pt"
    detector.write_bytes(b"detector-bytes")
    classifier.write_bytes(b"classifier-bytes")
    detector_uri = f"s3://{BUCKET}/{DETECTOR_KEY}"
    classifier_uri = f"s3://{BUCKET}/{CLASSIFIER_KEY}"

    assert store.seed_model_if_missing(detector, detector_uri) is True
    assert store.seed_model_if_missing(classifier, classifier_uri) is True
    assert store.download_model(detector_uri) == b"detector-bytes"
    assert store.download_model(classifier_uri) == b"classifier-bytes"


def test_seed_model_if_missing_is_idempotent(store, tmp_path):
    model_path = tmp_path / "retinanet_melhor.pt"
    model_path.write_bytes(b"pt-artifact")
    store.client.put_object(Bucket=BUCKET, Key=DETECTOR_KEY, Body=b"existing")

    uploaded = store.seed_model_if_missing(model_path)

    assert uploaded is False
    stored = store.client.get_object(Bucket=BUCKET, Key=DETECTOR_KEY)
    assert stored["Body"].read() == b"existing"


def test_seed_model_if_missing_noops_when_local_file_absent(store, tmp_path):
    uploaded = store.seed_model_if_missing(tmp_path / "missing.pt")

    assert uploaded is False


def test_presign_get_signs_against_public_endpoint_when_set(local_env):
    import boto3

    local_env.setenv("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
    get_settings.cache_clear()
    from app.core.aws import s3_client

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        presign_client = s3_client(endpoint_url="http://localhost:9000")
        store = S3ObjectStore(client=s3, presign_client=presign_client, bucket=BUCKET)
        store.ensure_bucket()
        key = store.put_analysis_image("org-1", "an-1", "png", b"bytes", "image/png")

        url = store.presign_get(key, expires_seconds=600)

    assert url.startswith(f"http://localhost:9000/{BUCKET}/{key}")
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=600" in url
