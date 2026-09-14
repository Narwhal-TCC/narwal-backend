import boto3
from botocore.config import Config

from app.core.config import Settings, get_settings


def _credential_kwargs(settings: Settings) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
    if settings.aws_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return kwargs


def s3_client():
    settings = get_settings()
    kwargs: dict = {
        "service_name": "s3",
        "region_name": settings.aws_region,
        **_credential_kwargs(settings),
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_force_path_style:
        kwargs["config"] = Config(s3={"addressing_style": "path"})
    return boto3.client(**kwargs)


def dynamodb_resource():
    settings = get_settings()
    kwargs: dict = {
        "service_name": "dynamodb",
        "region_name": settings.aws_region,
        **_credential_kwargs(settings),
    }
    if settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
    return boto3.resource(**kwargs)
