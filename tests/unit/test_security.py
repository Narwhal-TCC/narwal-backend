from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_verify_password_rejects_wrong_password():
    password_hash = hash_password("correct-password")

    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_access_token_round_trip_preserves_required_claims(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    get_settings.cache_clear()

    token = create_access_token("user-123", "org-456", "member")

    claims = decode_access_token(token)
    assert claims["sub"] == "user-123"
    assert claims["org_id"] == "org-456"
    assert claims["role"] == "member"


def test_decode_access_token_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    get_settings.cache_clear()
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "user-123",
            "org_id": "org-456",
            "role": "member",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_invalid_token():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-jwt")
