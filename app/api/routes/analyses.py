from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_analyze_service, get_current_user, get_history_service
from app.repositories.analyses import DEFAULT_LIST_LIMIT
from app.schemas.analysis import (
    AnalysisListResponse,
    AnalysisResult,
    OrgStatsResponse,
    ReviewStatusUpdate,
)
from app.services.analyze import AnalyzeService
from app.services.history import HistoryService

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=AnalysisResult)
async def create_analysis(
    file: UploadFile = File(...),
    campaign_name: str | None = Form(None),
    coordinates: str | None = Form(None),
    collected_at: str | None = Form(None),
    model_id: str | None = Form(default=None),
    current_user: dict[str, str] = Depends(get_current_user),
    service: AnalyzeService = Depends(get_analyze_service),
) -> AnalysisResult:
    data = await file.read()
    # Inference blocks for up to the configured timeout, so keep it off the event loop.
    return await run_in_threadpool(
        service.analyze_image,
        org_id=current_user["org_id"],
        user_id=current_user["user_id"],
        content_type=file.content_type,
        data=data,
        campaign_name=campaign_name,
        coordinates=coordinates,
        collected_at=collected_at,
        model_id=model_id,
    )


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    class_filter: str | None = Query(default=None, alias="class"),
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> AnalysisListResponse:
    return service.list_analyses(
        current_user["org_id"],
        limit=limit,
        offset=offset,
        q=q,
        class_filter=class_filter,
    )


@router.get("/stats", response_model=OrgStatsResponse)
def get_org_stats(
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> OrgStatsResponse:
    return service.get_org_stats(current_user["org_id"])


@router.patch("/{analysis_id}", response_model=AnalysisResult)
def update_review_status(
    analysis_id: str,
    body: ReviewStatusUpdate,
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> AnalysisResult:
    org_id = current_user["org_id"]
    service.update_review_status(org_id, analysis_id, body.review_status)  # type: ignore[arg-type]
    return service.get_analysis(org_id, analysis_id)


@router.get("/{analysis_id}", response_model=AnalysisResult)
def get_analysis(
    analysis_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> AnalysisResult:
    return service.get_analysis(current_user["org_id"], analysis_id)
