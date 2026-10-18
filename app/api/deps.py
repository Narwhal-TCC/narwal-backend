from functools import lru_cache

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import UnauthorizedError
from app.core.security import decode_access_token
from app.repositories.analyses import AnalysisRepository
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository
from app.services.analyze import AnalyzeService
from app.services.auth import AuthService
from app.services.gateway_pool import GatewayPool
from app.services.history import HistoryService
from app.services.model_gateway import ModelGateway

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


@lru_cache
def get_object_store() -> S3ObjectStore:
    return S3ObjectStore()


@lru_cache
def get_analysis_repository() -> AnalysisRepository:
    return AnalysisRepository()


@lru_cache
def get_gateway_pool() -> GatewayPool:
    return GatewayPool(store=get_object_store())


@lru_cache
def get_model_gateway() -> ModelGateway:
    # Back-compat for tests that override a single gateway via the default pipeline id.
    return get_gateway_pool().get("yolo-convnext-balanced")


def get_analyze_service(
    gateway_pool: GatewayPool = Depends(get_gateway_pool),
    object_store: S3ObjectStore = Depends(get_object_store),
    repository: AnalysisRepository = Depends(get_analysis_repository),
) -> AnalyzeService:
    return AnalyzeService(
        gateway_pool=gateway_pool,
        object_store=object_store,
        repository=repository,
    )


def get_history_service(
    object_store: S3ObjectStore = Depends(get_object_store),
    repository: AnalysisRepository = Depends(get_analysis_repository),
) -> HistoryService:
    return HistoryService(repository=repository, object_store=object_store)
