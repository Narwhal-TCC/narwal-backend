from app.core.config import get_settings
from app.core.security import hash_password
from app.repositories.users import UserRepository


def run_seed(repository: UserRepository | None = None) -> None:
    repo = repository or UserRepository()
    settings = get_settings()
    org_id = settings.platform_admin_org_id

    if repo.get_org(org_id) is None:
        repo.put_org(org_id=org_id, name="Platform")

    if repo.get_by_username(settings.platform_admin_username) is None:
        repo.put_user(
            user_id="platform-admin",
            org_id=org_id,
            username=settings.platform_admin_username,
            password_hash=hash_password(settings.platform_admin_password),
            role="platform_admin",
        )


if __name__ == "__main__":
    run_seed()
