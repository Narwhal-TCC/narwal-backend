from pathlib import Path

from app.repositories.users import UserRepository


def test_create_org_and_user_then_fetch_by_username(tmp_path: Path):
    db_path = tmp_path / "users.db"
    repository = UserRepository(str(db_path))

    repository.put_org(org_id="org-1", name="Sonar Team")
    repository.put_user(
        user_id="user-1",
        org_id="org-1",
        username="operator",
        password_hash="hashed-password",
        role="member",
    )

    assert repository.get_org("org-1") == {
        "org_id": "org-1",
        "name": "Sonar Team",
    }
    assert repository.get_by_username("operator") == {
        "user_id": "user-1",
        "org_id": "org-1",
        "username": "operator",
        "password_hash": "hashed-password",
        "role": "member",
    }


def test_get_user_returns_row_for_org_and_user_id(tmp_path: Path):
    db_path = tmp_path / "users.db"
    repository = UserRepository(str(db_path))
    repository.put_user(
        user_id="admin-1",
        org_id="platform",
        username="admin",
        password_hash="hashed-password",
        role="platform_admin",
    )

    assert repository.get_user("platform", "admin-1") == {
        "user_id": "admin-1",
        "org_id": "platform",
        "username": "admin",
        "password_hash": "hashed-password",
        "role": "platform_admin",
    }
