from fastapi import APIRouter, Depends

from app.api.deps import get_campaign_service, get_current_user
from app.schemas.analysis import Campaign, CampaignPointsResponse
from app.services.campaigns import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[Campaign])
def list_campaigns(
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> list[Campaign]:
    return service.list_campaigns(current_user["org_id"])


@router.get("/{campaign_id}/points", response_model=CampaignPointsResponse)
def get_campaign_points(
    campaign_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignPointsResponse:
    return service.get_points(current_user["org_id"], campaign_id)
