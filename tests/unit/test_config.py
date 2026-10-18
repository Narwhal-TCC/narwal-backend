import os

from app.core.config import Settings, get_settings


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-cache-check")
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_sqlite_path_loads_from_env(monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", "/tmp/custom-narwal.db")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.sqlite_path == "/tmp/custom-narwal.db"


def test_endpoint_urls_load_from_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.s3_endpoint_url == "http://minio:9000"
    assert settings.s3_public_endpoint == "http://localhost:9000"


def test_list_scan_cap_loads_from_env(monkeypatch):
    monkeypatch.setenv("LIST_SCAN_CAP", "750")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.list_scan_cap == 750


def test_llm_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.llm_base_url == "http://llm.test/v1"
    assert settings.llm_model == "test-model"
    assert settings.llm_api_key == "secret-key"
    assert settings.llm_timeout_seconds == 15.0


def test_local_defaults_are_safe_for_dev():
    env_keys = (
        "S3_ENDPOINT_URL",
        "S3_PUBLIC_ENDPOINT",
        "SQLITE_PATH",
        "JWT_SECRET",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
    )
    saved = {key: os.environ.pop(key, None) for key in env_keys}
    get_settings.cache_clear()
    try:
        settings = Settings(_env_file=None)
        assert settings.s3_bucket == "narwal"
        assert settings.sqlite_path == "db/narwal.db"
        assert settings.aws_region == "us-east-1"
        assert settings.inference_timeout_seconds == 60
        assert settings.list_scan_cap == 500
        assert settings.max_metadata_length == 256
        assert settings.jwt_secret != ""
        assert settings.llm_base_url == "https://api.groq.com/openai/v1"
        assert settings.llm_model == "openai/gpt-oss-120b"
        assert settings.llm_api_key == ""
        assert settings.llm_timeout_seconds == 10.0
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value
        get_settings.cache_clear()
