import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import InferenceTimeoutError, InvalidImageError, StorageError, ValidationError
from app.repositories.analyses import AnalysisRepository, new_analysis_id
from app.repositories.s3_store import DEFAULT_PRESIGN_EXPIRES_SECONDS, S3ObjectStore
from app.schemas.analysis import AnalysisResult
from app.services.detection_adapter import to_detections
from app.services.model_gateway import ModelGateway
from app.services.primary_class import compute_primary_class, count_milco

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
ALLOWED_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg")}


class AnalyzeService:
    def __init__(
        self,
        model_gateway: ModelGateway,
        object_store: S3ObjectStore | None = None,
        repository: AnalysisRepository | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.object_store = object_store or S3ObjectStore()
        self.repository = repository or AnalysisRepository()
        self.timeout_seconds = timeout_seconds or get_settings().inference_timeout_seconds

    def analyze_image(
        self,
        org_id: str,
        user_id: str,
        content_type: str | None,
        data: bytes,
        campaign_name: str | None = None,
        coordinates: str | None = None,
        collected_at: str | datetime | None = None,
    ) -> AnalysisResult:
        validated_metadata = self._validate_metadata(
            campaign_name=campaign_name,
            coordinates=coordinates,
            collected_at=collected_at,
        )
        width, height, image_content_type, ext, image_array = self._validate_image(
            content_type, data
        )

        # Loading happens before any write so a model failure never leaves an analysis behind.
        self.model_gateway.ensure_model_loaded()
        started = time.perf_counter()
        raw = self._predict_with_timeout(image_array)
        inference_ms = int((time.perf_counter() - started) * 1000)

        detections = to_detections(raw, image_width=width, image_height=height)
        primary_class = compute_primary_class(detections)
        milco_detection_count = count_milco(detections)

        analysis_id = new_analysis_id()
        created_at = datetime.now(UTC)
        try:
            image_s3_key = self.object_store.put_analysis_image(
                org_id=org_id,
                analysis_id=analysis_id,
                ext=ext,
                data=data,
                content_type=image_content_type,
            )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Failed to store analysis image") from exc
        collected_at_value = validated_metadata["collected_at"]
        self.repository.put_analysis(
            analysis_id=analysis_id,
            org_id=org_id,
            user_id=user_id,
            status="succeeded",
            review_status="pending",
            primary_class=primary_class,
            campaign_name=validated_metadata["campaign_name"],
            coordinates=validated_metadata["coordinates"],
            collected_at=collected_at_value,
            milco_detection_count=milco_detection_count,
            detections=[detection.model_dump() for detection in detections],
            image_s3_key=image_s3_key,
            image_content_type=image_content_type,
            created_at=created_at.isoformat(),
            inference_ms=inference_ms,
        )
        return AnalysisResult(
            id=analysis_id,
            org_id=org_id,
            user_id=user_id,
            status="succeeded",
            review_status="pending",
            primary_class=primary_class,
            campaign_name=validated_metadata["campaign_name"],
            coordinates=validated_metadata["coordinates"],
            collected_at=(
                datetime.fromisoformat(collected_at_value)
                if collected_at_value is not None
                else None
            ),
            milco_detection_count=milco_detection_count,
            detections=detections,
            image_content_type=image_content_type,
            image_s3_key=image_s3_key,
            image_url=self.object_store.presign_get(
                image_s3_key,
                expires_seconds=DEFAULT_PRESIGN_EXPIRES_SECONDS,
            ),
            created_at=created_at,
            inference_ms=inference_ms,
        )

    def _validate_metadata(
        self,
        campaign_name: str | None,
        coordinates: str | None,
        collected_at: str | datetime | None,
    ) -> dict[str, str | None]:
        max_length = get_settings().max_metadata_length
        if campaign_name is not None and len(campaign_name) > max_length:
            raise ValidationError(
                f"campaign_name exceeds the maximum length of {max_length} characters"
            )
        if coordinates is not None and len(coordinates) > max_length:
            raise ValidationError(
                f"coordinates exceeds the maximum length of {max_length} characters"
            )
        collected_at_value: str | None = None
        if collected_at is not None:
            if isinstance(collected_at, datetime):
                collected_at_value = collected_at.isoformat()
            else:
                try:
                    collected_at_value = datetime.fromisoformat(collected_at).isoformat()
                except ValueError as exc:
                    raise ValidationError("collected_at is not a valid datetime") from exc
        return {
            "campaign_name": campaign_name,
            "coordinates": coordinates,
            "collected_at": collected_at_value,
        }

    def _validate_image(
        self,
        content_type: str | None,
        data: bytes,
    ) -> tuple[int, int, str, str, np.ndarray]:
        if not data:
            raise InvalidImageError("Uploaded image is empty")
        if len(data) > MAX_IMAGE_BYTES:
            raise InvalidImageError("Uploaded image exceeds the 10 MB limit")
        if (content_type or "").split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
            raise InvalidImageError(f"Unsupported image content type: {content_type!r}")
        try:
            with Image.open(BytesIO(data)) as probe:
                probe.verify()
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                width, height = image.size
                image_array = np.asarray(image.convert("RGB"), dtype=np.uint8)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidImageError("Uploaded file is not a readable image") from exc
        if image_format not in ALLOWED_FORMATS:
            raise InvalidImageError(f"Unsupported image format: {image_format}")
        image_content_type, ext = ALLOWED_FORMATS[image_format]
        return width, height, image_content_type, ext, image_array

    def _predict_with_timeout(self, image_array: np.ndarray) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.model_gateway.predict, image_array)
            try:
                return future.result(timeout=self.timeout_seconds)
            except FutureTimeoutError as exc:
                raise InferenceTimeoutError(f"Inference exceeded {self.timeout_seconds}s") from exc
        finally:
            # Never wait on a hung inference thread; the timeout response must not block on it.
            executor.shutdown(wait=False, cancel_futures=True)
