from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError

from app.core.aws import s3_client
from app.core.config import Settings, get_settings
from app.core.errors import ModelUnavailableError, StorageError

DEFAULT_PRESIGN_EXPIRES_SECONDS = 900


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri or "")
    key = parsed.path.lstrip("/")
    if parsed.scheme != "s3" or not parsed.netloc or not key:
        raise ValueError(f"Invalid S3 URI: {uri!r}")
    return parsed.netloc, key


def analysis_image_key(org_id: str, analysis_id: str, ext: str) -> str:
    return f"analyses/{org_id}/{analysis_id}/original.{ext.lower().lstrip('.')}"


class S3ObjectStore:
    def __init__(
        self,
        client: Any | None = None,
        bucket: str | None = None,
        presign_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.client = client or s3_client()
        self.bucket = bucket or settings.s3_bucket
        # Presigned URLs are signed against the host in the URL, so a browser-reachable
        # public endpoint needs its own client rather than a rewritten hostname.
        self.presign_client = presign_client or self._build_presign_client(settings)

    def _build_presign_client(self, settings: Settings) -> Any:
        if settings.s3_public_endpoint:
            return s3_client(endpoint_url=settings.s3_public_endpoint)
        return self.client

    def object_exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey"}:
                return False
            raise

    def seed_model_if_missing(self, local_path: str | Path) -> bool:
        """Upload a local `.keras` artifact when it is absent from object storage."""
        path = Path(local_path)
        if not path.is_file():
            return False
        bucket, key = parse_s3_uri(get_settings().model_s3_uri)
        if self.object_exists(bucket, key):
            return False
        try:
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType="application/octet-stream",
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Could not upload model artifact to s3://{bucket}/{key}") from exc
        return True

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NoSuchKey"}:
                raise
        region = get_settings().aws_region
        kwargs: dict = {"Bucket": self.bucket}
        if region and region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        self.client.create_bucket(**kwargs)

    def download_model(self) -> bytes:
        uri = get_settings().model_s3_uri
        try:
            bucket, key = parse_s3_uri(uri)
        except ValueError as exc:
            raise ModelUnavailableError(f"Model S3 URI is not configured: {uri!r}") from exc
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            raise ModelUnavailableError(f"Model object {uri} could not be downloaded") from exc

    def put_analysis_image(
        self,
        org_id: str,
        analysis_id: str,
        ext: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = analysis_image_key(org_id, analysis_id, ext)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Could not store analysis image {key}") from exc
        return key

    def presign_get(
        self,
        key: str,
        expires_seconds: int = DEFAULT_PRESIGN_EXPIRES_SECONDS,
    ) -> str:
        return self.presign_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
