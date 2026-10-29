from app.core.config import convnext_local_path_list, convnext_s3_uri_list, get_settings
from app.core.security import hash_password
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository


def seed_v3_fusion_model_artifacts(store: S3ObjectStore | None = None) -> None:
    """Upload local YOLO-A + fusion v3 classifier when absent from object storage."""
    settings = get_settings()
    s3 = store or S3ObjectStore()
    pairs: list[tuple[str | None, str]] = [
        (settings.yolo_a_local_path, settings.yolo_a_s3_uri),
        (
            settings.yolo_fusion_v3_classifier_local_path,
            settings.yolo_fusion_v3_classifier_s3_uri,
        ),
        (
            settings.yolo_fusion_mobilevit_classifier_local_path,
            settings.yolo_fusion_mobilevit_classifier_s3_uri,
        ),
    ]
    for local_path, s3_uri in pairs:
        if local_path:
            s3.seed_model_if_missing(local_path, s3_uri)


def seed_v2_model_artifacts(store: S3ObjectStore | None = None) -> None:
    """Upload local v2 YOLO / ConvNeXt weights when absent from object storage."""
    settings = get_settings()
    s3 = store or S3ObjectStore()
    pairs: list[tuple[str | None, str]] = [
        (settings.yolo_g5_local_path, settings.yolo_g5_s3_uri),
        (settings.yolo_a_local_path, settings.yolo_a_s3_uri),
    ]
    local_paths = convnext_local_path_list(settings)
    s3_uris = convnext_s3_uri_list(settings)
    pairs.extend(zip(local_paths, s3_uris, strict=True))
    for local_path, s3_uri in pairs:
        if local_path and s3.seed_model_if_missing(local_path, s3_uri):
            continue


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

    demo_org_id = settings.seed_demo_org_id
    if repo.get_org(demo_org_id) is None:
        repo.put_org(org_id=demo_org_id, name="Demo")

    if repo.get_by_username(settings.seed_demo_username) is None:
        repo.put_user(
            user_id="demo-user",
            org_id=demo_org_id,
            username=settings.seed_demo_username,
            password_hash=hash_password(settings.seed_demo_password),
            role="member",
        )


if __name__ == "__main__":
    run_seed()
