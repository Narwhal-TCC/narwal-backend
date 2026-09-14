import pytest

from app.core.errors import InvalidCredentialsError
from app.core.security import decode_access_token, hash_password
from app.services.auth import AuthService


class FakeUserRepository:
    def __init__(self, user: dict | None) -> None:
        self.user = user

    def get_by_username(self, username: str) -> dict | None:
        if self.user is not None and self.user["username"] == username:
            return self.user
        return None


def test_valid_user_yields_access_token():
    repository = FakeUserRepository(
        {
            "user_id": "user-1",
            "org_id": "org-1",
            "username": "operator",
            "password_hash": hash_password("correct-password"),
            "role": "member",
        }
    )

    response = AuthService(repository).authenticate("operator", "correct-password")
    claims = decode_access_token(response.access_token)

    assert response.token_type == "bearer"
    assert claims["sub"] == "user-1"
    assert claims["org_id"] == "org-1"
    assert claims["role"] == "member"


def test_bad_password_raises_invalid_credentials():
    repository = FakeUserRepository(
        {
            "user_id": "user-1",
            "org_id": "org-1",
            "username": "operator",
            "password_hash": hash_password("correct-password"),
            "role": "member",
        }
    )

    with pytest.raises(InvalidCredentialsError) as exc_info:
        AuthService(repository).authenticate("operator", "wrong-password")

    assert exc_info.value.code == "INVALID_CREDENTIALS"
