from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError as PydanticValidationError

from app.api.deps import get_campaign_service, get_current_user
from app.core.errors import ValidationError
from app.schemas.analysis import Campaign, CampaignPointsResponse
from app.schemas.campaigns import CampaignCreateBody, CampaignPatchBody
from app.services.campaigns import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _parse_create_body(body: dict) -> CampaignCreateBody:
    try:
        return CampaignCreateBody.model_validate(body)
    except PydanticValidationError as exc:
        raise ValidationError("request validation failed") from exc


def _parse_patch_body(body: dict) -> CampaignPatchBody:
    try:
        return CampaignPatchBody.model_validate(body)
    except PydanticValidationError as exc:
        raise ValidationError("request validation failed") from exc


@router.get("", response_model=list[Campaign])
def list_campaigns(
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> list[Campaign]:
    return service.list_campaigns(current_user["org_id"])


@router.post("", response_model=Campaign, status_code=201)
def create_campaign(
    body: dict = Body(...),
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> Campaign:
    payload = _parse_create_body(body)
    return service.create_campaign(current_user["org_id"], payload)


@router.get("/{campaign_id}", response_model=Campaign)
def get_campaign(
    campaign_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> Campaign:
    return service.get_campaign(current_user["org_id"], campaign_id)


@router.patch("/{campaign_id}", response_model=Campaign)
def update_campaign(
    campaign_id: str,
    body: dict = Body(...),
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> Campaign:
    payload = _parse_patch_body(body)
    return service.update_campaign(current_user["org_id"], campaign_id, payload)


@router.get("/{campaign_id}/points", response_model=CampaignPointsResponse)
def get_campaign_points(
    campaign_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignPointsResponse:
    return service.get_points(current_user["org_id"], campaign_id)
