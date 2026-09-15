from datetime import datetime

from app.core.config import get_settings
from app.core.errors import AnalysisNotFoundError, ValidationError
from app.repositories.analyses import DEFAULT_LIST_LIMIT, AnalysisRepository
from app.repositories.s3_store import DEFAULT_PRESIGN_EXPIRES_SECONDS, S3ObjectStore
from app.schemas.analysis import (
    AnalysisListResponse,
    AnalysisResult,
    AnalysisSummary,
    OrgStatsResponse,
    PrimaryClass,
    ReviewStatus,
)

VALID_PRIMARY_CLASSES = frozenset({"MILCO", "NOMBO"})
VALID_REVIEW_STATUSES = frozenset({"pending", "confirmed", "false_positive"})


class HistoryService:
    def __init__(
        self,
        repository: AnalysisRepository | None = None,
        object_store: S3ObjectStore | None = None,
        presign_expires_seconds: int = DEFAULT_PRESIGN_EXPIRES_SECONDS,
        list_scan_cap: int | None = None,
    ) -> None:
        self.repository = repository or AnalysisRepository()
        self.object_store = object_store or S3ObjectStore()
        self.presign_expires_seconds = presign_expires_seconds
        self.list_scan_cap = list_scan_cap or get_settings().list_scan_cap

    def list_analyses(
        self,
        org_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
        q: str | None = None,
        class_filter: PrimaryClass | None = None,
    ) -> AnalysisListResponse:
        if class_filter is not None and class_filter not in VALID_PRIMARY_CLASSES:
            raise ValidationError(f"class must be one of: {', '.join(sorted(VALID_PRIMARY_CLASSES))}")

        records = self.repository.list_by_org(
            org_id,
            limit=self.list_scan_cap,
            offset=0,
        )
        q_fold = self._normalize_q(q)
        filtered = [
            record
            for record in records
            if self._matches_q(record, q_fold) and self._matches_class(record, class_filter)
        ]
        page = filtered[offset : offset + limit]
        return AnalysisListResponse(
            items=[self._to_summary(record) for record in page],
            limit=limit,
            offset=offset,
        )

    def get_analysis(self, org_id: str, analysis_id: str) -> AnalysisResult:
        # The org id is part of the key, so another org's id is indistinguishable from a miss.
        record = self.repository.get_analysis(org_id, analysis_id)
        if record is None:
            raise AnalysisNotFoundError()
        return self._to_result(record)

    def update_review_status(
        self,
        org_id: str,
        analysis_id: str,
        review_status: ReviewStatus,
    ) -> AnalysisSummary:
        if review_status not in VALID_REVIEW_STATUSES:
            raise ValidationError(
                f"review_status must be one of: {', '.join(sorted(VALID_REVIEW_STATUSES))}"
            )
        updated = self.repository.update_review_status(org_id, analysis_id, review_status)
        if updated is None:
            raise AnalysisNotFoundError()
        return self._to_summary(updated)

    def get_org_stats(self, org_id: str) -> OrgStatsResponse:
        records = self.repository.list_by_org(
            org_id,
            limit=self.list_scan_cap,
            offset=0,
        )
        if not records:
            return OrgStatsResponse(
                analyses_count=0,
                milco_detections_count=0,
                last_analysis=None,
                active_campaign=None,
            )

        active_campaign = None
        for item in records:
            campaign_name = item.get("campaign_name")
            if campaign_name:
                active_campaign = campaign_name
                break

        return OrgStatsResponse(
            analyses_count=len(records),
            milco_detections_count=sum(
                item.get("milco_detection_count", 0) for item in records
            ),
            last_analysis=self._to_summary(records[0]),
            active_campaign=active_campaign,
        )

    @staticmethod
    def _normalize_q(q: str | None) -> str | None:
        if q is None:
            return None
        stripped = q.strip()
        if not stripped:
            return None
        return stripped.casefold()

    @staticmethod
    def _matches_q(record: dict, q_fold: str | None) -> bool:
        if q_fold is None:
            return True
        if q_fold in record["id"].casefold():
            return True
        campaign_name = record.get("campaign_name") or ""
        return q_fold in campaign_name.casefold()

    @staticmethod
    def _matches_class(record: dict, class_filter: PrimaryClass | None) -> bool:
        if class_filter is None:
            return True
        return record.get("primary_class") == class_filter

    @staticmethod
    def _parse_collected_at(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    def _to_summary(self, record: dict) -> AnalysisSummary:
        return AnalysisSummary(
            id=record["id"],
            org_id=record["org_id"],
            user_id=record["user_id"],
            status=record["status"],
            review_status=record.get("review_status", "pending"),
            primary_class=record.get("primary_class"),
            campaign_name=record.get("campaign_name"),
            coordinates=record.get("coordinates"),
            collected_at=self._parse_collected_at(record.get("collected_at")),
            milco_detection_count=record.get("milco_detection_count", 0),
            created_at=record["created_at"],
            inference_ms=record.get("inference_ms"),
            detection_count=len(record["detections"]),
        )

    def _to_result(self, record: dict) -> AnalysisResult:
        return AnalysisResult(
            id=record["id"],
            org_id=record["org_id"],
            user_id=record["user_id"],
            status=record["status"],
            review_status=record.get("review_status", "pending"),
            primary_class=record.get("primary_class"),
            campaign_name=record.get("campaign_name"),
            coordinates=record.get("coordinates"),
            collected_at=self._parse_collected_at(record.get("collected_at")),
            milco_detection_count=record.get("milco_detection_count", 0),
            detections=record["detections"],
            image_content_type=record["image_content_type"],
            image_s3_key=record["image_s3_key"],
            image_url=self.object_store.presign_get(
                record["image_s3_key"],
                expires_seconds=self.presign_expires_seconds,
            ),
            created_at=record["created_at"],
            inference_ms=record.get("inference_ms"),
        )
