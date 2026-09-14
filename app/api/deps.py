import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import UnauthorizedError
from app.core.security import decode_access_token
from app.repositories.users import UserRepository
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository() -> UserRepository:
    return UserRepository()


def get_auth_service(
    repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repository)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str]:
    if credentials is None:
        raise UnauthorizedError()
    try:
        claims = decode_access_token(credentials.credentials)
        current_user = {
            "user_id": claims["sub"],
            "org_id": claims["org_id"],
            "role": claims["role"],
        }
    except (jwt.InvalidTokenError, KeyError):
        raise UnauthorizedError() from None
    if current_user["role"] not in {"member", "platform_admin"}:
        raise UnauthorizedError()
    return current_user
