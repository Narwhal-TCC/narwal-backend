from types import SimpleNamespace
from unittest.mock import MagicMock

from botocore.config import Config

from app.core import aws


def _settings(**overrides):
    defaults = {
        "aws_region": "us-east-1",
        "aws_access_key_id": "test-key",
        "aws_secret_access_key": "test-secret",
        "s3_endpoint_url": "http://minio:9000",
        "s3_force_path_style": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_s3_client_passes_endpoint_and_path_style(monkeypatch):
    monkeypatch.setattr(aws, "get_settings", lambda: _settings())
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(aws.boto3, "client", fake_client)

    aws.s3_client()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://minio:9000"
    assert captured["region_name"] == "us-east-1"
    assert isinstance(captured["config"], Config)
    assert captured["config"].s3["addressing_style"] == "path"


def test_s3_client_omits_endpoint_when_unset(monkeypatch):
    monkeypatch.setattr(
        aws,
        "get_settings",
        lambda: _settings(s3_endpoint_url=None, s3_force_path_style=False),
    )
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(aws.boto3, "client", fake_client)

    aws.s3_client()

    assert "endpoint_url" not in captured
    assert "config" not in captured
