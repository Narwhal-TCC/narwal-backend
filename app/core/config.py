from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AWS / local emulators
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_public_endpoint: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT")
    s3_force_path_style: bool = Field(default=True, alias="S3_FORCE_PATH_STYLE")
    s3_bucket: str = Field(default="narwal", alias="S3_BUCKET")

    sqlite_path: str = Field(default="db/narwal.db", alias="SQLITE_PATH")

    # Auth
    jwt_secret: str = Field(default="dev-only-change-me", alias="JWT_SECRET")
    access_token_ttl_seconds: int = Field(default=3600, alias="ACCESS_TOKEN_TTL")

    platform_admin_username: str = Field(default="admin", alias="PLATFORM_ADMIN_USERNAME")
    platform_admin_password: str = Field(default="admin", alias="PLATFORM_ADMIN_PASSWORD")
    platform_admin_org_id: str = Field(default="platform", alias="PLATFORM_ADMIN_ORG_ID")

    seed_demo_username: str = Field(default="demo", alias="SEED_DEMO_USERNAME")
    seed_demo_password: str = Field(default="demo", alias="SEED_DEMO_PASSWORD")
    seed_demo_org_id: str = Field(default="demo", alias="SEED_DEMO_ORG_ID")

    # Model / inference (dual-stage PyTorch)
    detector_local_path: str | None = Field(
        default="data/models/retinanet_melhor.pt",
        alias="DETECTOR_LOCAL_PATH",
    )
    detector_s3_uri: str = Field(
        default="s3://narwal/models/v1/retinanet_melhor.pt",
        alias="DETECTOR_S3_URI",
    )
    classifier_local_path: str | None = Field(
        default="data/models/fusion_ghostnetv2_mobilenetv2_melhor.pt",
        alias="CLASSIFIER_LOCAL_PATH",
    )
    classifier_s3_uri: str = Field(
        default="s3://narwal/models/v1/fusion_ghostnetv2_mobilenetv2_melhor.pt",
        alias="CLASSIFIER_S3_URI",
    )
    inference_timeout_seconds: int = Field(default=60, alias="INFERENCE_TIMEOUT_SECONDS")
    detector_score_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        alias="DETECTOR_SCORE_THRESHOLD",
        description=(
            "Minimum RetinaNet score; must match training eval (notebook score_thresh=0.5)."
        ),
    )

    # Analysis list / metadata bounds
    list_scan_cap: int = Field(default=500, alias="LIST_SCAN_CAP")
    max_metadata_length: int = Field(default=256, alias="MAX_METADATA_LENGTH")


@lru_cache
def get_settings() -> Settings:
    return Settings()
