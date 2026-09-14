from fastapi import APIRouter, Depends, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_analyze_service, get_current_user, get_history_service
from app.repositories.analyses import DEFAULT_LIST_LIMIT
from app.schemas.analysis import AnalysisListResponse, AnalysisResult
from app.services.analyze import AnalyzeService
from app.services.history import HistoryService

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=AnalysisResult)
async def create_analysis(
    file: UploadFile = File(...),
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
    )


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> AnalysisListResponse:
    return service.list_analyses(current_user["org_id"], limit=limit, offset=offset)


@router.get("/{analysis_id}", response_model=AnalysisResult)
def get_analysis(
    analysis_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    service: HistoryService = Depends(get_history_service),
) -> AnalysisResult:
    return service.get_analysis(current_user["org_id"], analysis_id)
