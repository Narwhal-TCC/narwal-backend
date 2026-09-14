from app.core.errors import AnalysisNotFoundError
from app.repositories.analyses import DEFAULT_LIST_LIMIT, AnalysisRepository
from app.repositories.s3_store import DEFAULT_PRESIGN_EXPIRES_SECONDS, S3ObjectStore
from app.schemas.analysis import AnalysisListResponse, AnalysisResult, AnalysisSummary


class HistoryService:
    def __init__(
        self,
        repository: AnalysisRepository | None = None,
        object_store: S3ObjectStore | None = None,
        presign_expires_seconds: int = DEFAULT_PRESIGN_EXPIRES_SECONDS,
    ) -> None:
        self.repository = repository or AnalysisRepository()
        self.object_store = object_store or S3ObjectStore()
        self.presign_expires_seconds = presign_expires_seconds

    def list_analyses(
        self,
        org_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> AnalysisListResponse:
        records = self.repository.list_by_org(org_id, limit=limit, offset=offset)
        return AnalysisListResponse(
            items=[
                AnalysisSummary(
                    id=record["id"],
                    org_id=record["org_id"],
                    user_id=record["user_id"],
                    status=record["status"],
                    created_at=record["created_at"],
                    inference_ms=record["inference_ms"],
                    detection_count=len(record["detections"]),
                )
                for record in records
            ],
            limit=limit,
            offset=offset,
        )

    def get_analysis(self, org_id: str, analysis_id: str) -> AnalysisResult:
        # The org id is part of the key, so another org's id is indistinguishable from a miss.
        record = self.repository.get_analysis(org_id, analysis_id)
        if record is None:
            raise AnalysisNotFoundError()
        return AnalysisResult(
            id=record["id"],
            org_id=record["org_id"],
            user_id=record["user_id"],
            status=record["status"],
            detections=record["detections"],
            image_content_type=record["image_content_type"],
            image_s3_key=record["image_s3_key"],
            image_url=self.object_store.presign_get(
                record["image_s3_key"],
                expires_seconds=self.presign_expires_seconds,
            ),
            created_at=record["created_at"],
            inference_ms=record["inference_ms"],
        )
