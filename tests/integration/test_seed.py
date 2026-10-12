from pathlib import Path

from app.bootstrap.seed import run_seed
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.repositories.users import UserRepository


def test_run_seed_creates_env_platform_admin_idempotently(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "seed.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("PLATFORM_ADMIN_USERNAME", "root-admin")
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "strong-test-password")
    monkeypatch.setenv("PLATFORM_ADMIN_ORG_ID", "platform-org")
    monkeypatch.setenv("SEED_DEMO_USERNAME", "frontend-user")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "frontend-password")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "frontend-org")
    get_settings.cache_clear()
    repository = UserRepository(str(db_path))

    run_seed(repository)
    first_user = repository.get_by_username("root-admin")
    run_seed(repository)
    second_user = repository.get_by_username("root-admin")

    assert first_user is not None
    assert first_user["org_id"] == "platform-org"
    assert first_user["role"] == "platform_admin"
    assert verify_password("strong-test-password", first_user["password_hash"]) is True
    assert second_user == first_user
    assert repository.get_user("platform-org", first_user["user_id"]) == first_user


def test_run_seed_creates_demo_member_idempotently(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "seed-demo.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SEED_DEMO_USERNAME", "frontend-user")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "frontend-password")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "frontend-org")
    get_settings.cache_clear()
    repository = UserRepository(str(db_path))

    run_seed(repository)
    first_user = repository.get_by_username("frontend-user")
    run_seed(repository)
    second_user = repository.get_by_username("frontend-user")
    demo_org = repository.get_org("frontend-org")

    assert demo_org is not None
    assert demo_org["name"] == "Demo"
    assert first_user is not None
    assert first_user["org_id"] == "frontend-org"
    assert first_user["role"] == "member"
    assert verify_password("frontend-password", first_user["password_hash"]) is True
    assert second_user == first_user


def test_run_seed_leaves_existing_password_hash_unchanged(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "seed-password.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SEED_DEMO_USERNAME", "demo-user")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "env-password")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "demo-org")
    get_settings.cache_clear()
    repository = UserRepository(str(db_path))
    repository.put_org("demo-org", "Demo")
    custom_hash = hash_password("custom-password")
    repository.put_user(
        user_id="demo-user",
        org_id="demo-org",
        username="demo-user",
        password_hash=custom_hash,
        role="member",
    )

    run_seed(repository)

    user = repository.get_by_username("demo-user")
    assert user is not None
    assert user["password_hash"] == custom_hash
    assert verify_password("env-password", user["password_hash"]) is False
