import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import (
    CampaignNotFoundError,
    InferenceTimeoutError,
    InvalidImageError,
    StorageError,
    ValidationError,
)
from app.repositories.analyses import AnalysisRepository, new_analysis_id
from app.repositories.campaigns import CampaignRepository
from app.repositories.s3_store import DEFAULT_PRESIGN_EXPIRES_SECONDS, S3ObjectStore
from app.schemas.analysis import AnalysisLocation, AnalysisResult, CampaignRef
from app.services.ai_analyst import AiAnalyst, AnalystContext
from app.services.detection_adapter import to_detections
from app.services.gateway_pool import GatewayPool
from app.services.model_registry import resolve_model_id
from app.services.primary_class import compute_primary_class, count_milco

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
ALLOWED_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg")}


class AnalyzeService:
    def __init__(
        self,
        gateway_pool: GatewayPool,
        object_store: S3ObjectStore | None = None,
        repository: AnalysisRepository | None = None,
        campaign_repository: CampaignRepository | None = None,
        timeout_seconds: int | None = None,
        ai_analyst: AiAnalyst | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.gateway_pool = gateway_pool
        self.object_store = object_store or S3ObjectStore()
        self.repository = repository or AnalysisRepository()
        self.campaign_repository = campaign_repository or CampaignRepository()
        self.timeout_seconds = timeout_seconds or get_settings().inference_timeout_seconds
        self.ai_analyst = ai_analyst or AiAnalyst()
        self._rng = rng or random.Random()

    def analyze_image(
        self,
        org_id: str,
        user_id: str,
        content_type: str | None,
        data: bytes,
        campaign_id: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        collected_at: str | datetime | None = None,
        model_id: str | None = None,
    ) -> AnalysisResult:
        collected_at_value = self._validate_collected_at(collected_at)
        location_ctx = self._resolve_location(
            org_id=org_id,
            campaign_id=campaign_id,
            latitude=latitude,
            longitude=longitude,
        )
        width, height, image_content_type, ext, image_array = self._validate_image(
            content_type, data
        )
        resolved_model_id = resolve_model_id(model_id)
        gateway = self.gateway_pool.get(resolved_model_id)

        # Loading happens before any write so a model failure never leaves an analysis behind.
        gateway.ensure_model_loaded()
        started = time.perf_counter()
        raw = self._predict_with_timeout(gateway, image_array)
        inference_ms = int((time.perf_counter() - started) * 1000)

        detections = to_detections(raw, image_width=width, image_height=height)
        primary_class = compute_primary_class(detections)
        milco_detection_count = count_milco(detections)
        ai_analysis = self.ai_analyst.analyze(
            AnalystContext(
                model_id=resolved_model_id,
                image_width=width,
                image_height=height,
                detections=detections,
                primary_class=primary_class,
                milco_detection_count=milco_detection_count,
            )
        )

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

        self.repository.put_analysis(
            analysis_id=analysis_id,
            org_id=org_id,
            user_id=user_id,
            status="succeeded",
            review_status="pending",
            primary_class=primary_class,
            campaign_id=location_ctx["campaign"].id,
            latitude=location_ctx["latitude"],
            longitude=location_ctx["longitude"],
            location_source=location_ctx["location_source"],
            collected_at=collected_at_value,
            milco_detection_count=milco_detection_count,
            detections=[detection.model_dump() for detection in detections],
            image_s3_key=image_s3_key,
            image_content_type=image_content_type,
            created_at=created_at.isoformat(),
            inference_ms=inference_ms,
            model_id=resolved_model_id,
            ai_analysis=ai_analysis,
        )
        location = AnalysisLocation(
            lat=location_ctx["latitude"],
            lon=location_ctx["longitude"],
            source=location_ctx["location_source"],
        )
        return AnalysisResult(
            id=analysis_id,
            org_id=org_id,
            user_id=user_id,
            status="succeeded",
            review_status="pending",
            primary_class=primary_class,
            campaign=location_ctx["campaign"],
            location=location,
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
            model_id=resolved_model_id,
            ai_analysis=ai_analysis,
        )

    def _resolve_location(
        self,
        *,
        org_id: str,
        campaign_id: str | None,
        latitude: float | None,
        longitude: float | None,
    ) -> dict[str, Any]:
        if campaign_id is None or not str(campaign_id).strip():
            raise ValidationError("campaign_id is required")

        campaign_row = self.campaign_repository.get_campaign(org_id, campaign_id)
        if campaign_row is None:
            raise CampaignNotFoundError()

        campaign_ref = CampaignRef(id=campaign_row["campaign_id"], name=campaign_row["name"])
        min_lat = float(campaign_row["min_lat"])
        max_lat = float(campaign_row["max_lat"])
        min_lon = float(campaign_row["min_lon"])
        max_lon = float(campaign_row["max_lon"])

        has_lat = latitude is not None
        has_lon = longitude is not None
        if has_lat != has_lon:
            raise ValidationError("latitude and longitude must be sent together")

        if has_lat and has_lon:
            lat = float(latitude)
            lon = float(longitude)
            if not math.isfinite(lat) or not math.isfinite(lon):
                raise ValidationError("latitude and longitude must be finite numbers")
            if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                raise ValidationError("position is outside the campaign area")
            return {
                "campaign": campaign_ref,
                "latitude": lat,
                "longitude": lon,
                "location_source": "entered",
            }

        lat = self._rng.uniform(min_lat, max_lat)
        lon = self._rng.uniform(min_lon, max_lon)
        return {
            "campaign": campaign_ref,
            "latitude": lat,
            "longitude": lon,
            "location_source": "simulated",
        }

    @staticmethod
    def _validate_collected_at(collected_at: str | datetime | None) -> str | None:
        if collected_at is None:
            return None
        if isinstance(collected_at, datetime):
            return collected_at.isoformat()
        try:
            return datetime.fromisoformat(collected_at).isoformat()
        except ValueError as exc:
            raise ValidationError("collected_at is not a valid datetime") from exc

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

    def _predict_with_timeout(self, gateway: Any, image_array: np.ndarray) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(gateway.predict, image_array)
            try:
                return future.result(timeout=self.timeout_seconds)
            except FutureTimeoutError as exc:
                raise InferenceTimeoutError(f"Inference exceeded {self.timeout_seconds}s") from exc
        finally:
            # Never wait on a hung inference thread; the timeout response must not block on it.
            executor.shutdown(wait=False, cancel_futures=True)
