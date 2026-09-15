import os

from app.core.config import Settings, get_settings


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-cache-check")
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_endpoint_urls_load_from_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://dynamodb:8000")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.s3_endpoint_url == "http://minio:9000"
    assert settings.s3_public_endpoint == "http://localhost:9000"
    assert settings.dynamodb_endpoint_url == "http://dynamodb:8000"


def test_list_scan_cap_loads_from_env(monkeypatch):
    monkeypatch.setenv("LIST_SCAN_CAP", "750")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.list_scan_cap == 750


def test_local_defaults_are_safe_for_dev():
    env_keys = (
        "S3_ENDPOINT_URL",
        "S3_PUBLIC_ENDPOINT",
        "DYNAMODB_ENDPOINT_URL",
        "JWT_SECRET",
    )
    saved = {key: os.environ.pop(key, None) for key in env_keys}
    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.s3_bucket == "narwal"
        assert settings.ddb_table == "narwal"
        assert settings.aws_region == "us-east-1"
        assert settings.inference_timeout_seconds == 60
        assert settings.list_scan_cap == 500
        assert settings.max_metadata_length == 256
        assert settings.jwt_secret != ""
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value
        get_settings.cache_clear()
