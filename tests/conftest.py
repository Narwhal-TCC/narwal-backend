import logging
from pathlib import Path

import pytest

import app.main as main_module
from app.api.deps import (
    get_analysis_repository,
    get_gateway_pool,
    get_model_gateway,
    get_object_store,
    get_user_repository,
)
from app.bootstrap.seed import run_seed
from app.core.config import get_settings
from app.core.errors import StoreUnavailableError
from app.main import app
from app.services.gateway_pool import GatewayPool
from app.services.model_gateway import FakeModelGateway

logger = logging.getLogger("app.main")
_production_bootstrap = main_module.bootstrap


def _sqlite_only_bootstrap() -> None:
    try:
        run_seed()
    except StoreUnavailableError:
        logger.warning("metadata store unavailable", exc_info=True)
    except Exception:
        logger.warning("Could not seed organizations and users", exc_info=True)


@pytest.fixture(autouse=True)
def sqlite_only_bootstrap(monkeypatch):
    monkeypatch.setattr(main_module, "bootstrap", _sqlite_only_bootstrap)


@pytest.fixture
def production_bootstrap(monkeypatch):
    """Run the real app.main.bootstrap (autouse stub replaces it for most tests)."""
    monkeypatch.setattr(main_module, "bootstrap", _production_bootstrap)
    yield _production_bootstrap


def gateway_pool_for(gateway: FakeModelGateway) -> GatewayPool:
    return GatewayPool(
        gateway_factories={
            "yolo-convnext-balanced": lambda g=gateway: g,
            "yolo-convnext-recall": lambda g=gateway: g,
            "two-stage-pt": lambda g=gateway: g,
        }
    )


@pytest.fixture(autouse=True)
def fake_model_gateway_by_default():
    gateway = FakeModelGateway()
    app.dependency_overrides[get_gateway_pool] = lambda: gateway_pool_for(gateway)
    app.dependency_overrides[get_model_gateway] = lambda: gateway
    get_gateway_pool.cache_clear()
    get_model_gateway.cache_clear()
    yield
    app.dependency_overrides.pop(get_gateway_pool, None)
    app.dependency_overrides.pop(get_model_gateway, None)
    get_gateway_pool.cache_clear()
    get_model_gateway.cache_clear()


@pytest.fixture(autouse=True)
def temp_sqlite_database(monkeypatch, tmp_path):
    db_path = tmp_path / "narwal-test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "")
    get_settings.cache_clear()
    get_analysis_repository.cache_clear()
    get_object_store.cache_clear()
    get_gateway_pool.cache_clear()
    if hasattr(get_user_repository, "cache_clear"):
        get_user_repository.cache_clear()
    yield
    get_settings.cache_clear()
    get_analysis_repository.cache_clear()
    get_object_store.cache_clear()
    get_gateway_pool.cache_clear()
    if hasattr(get_user_repository, "cache_clear"):
        get_user_repository.cache_clear()


def test_suite_does_not_create_repo_root_database():
    assert not Path("db/narwal.db").exists()
