import math
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.errors import CampaignConflictError, CampaignNotFoundError, ValidationError
from app.repositories.analyses import AnalysisRepository
from app.repositories.campaigns import CampaignRepository, new_campaign_id
from app.schemas.analysis import (
    Campaign,
    CampaignArea,
    CampaignPoint,
    CampaignPointsResponse,
)
from app.schemas.campaigns import CampaignCreateBody, CampaignPatchBody

MAX_CAMPAIGN_NAME_LEN = 120


class CampaignService:
    def __init__(
        self,
        campaign_repository: CampaignRepository | None = None,
        analysis_repository: AnalysisRepository | None = None,
        list_scan_cap: int | None = None,
    ) -> None:
        self.campaign_repository = campaign_repository or CampaignRepository()
        self.analysis_repository = analysis_repository or AnalysisRepository()
        self.list_scan_cap = list_scan_cap or get_settings().list_scan_cap

    def list_campaigns(self, org_id: str) -> list[Campaign]:
        rows = self.campaign_repository.list_by_org(org_id)
        return [self._to_campaign(row) for row in rows]

    def get_campaign(self, org_id: str, campaign_id: str) -> Campaign:
        row = self.campaign_repository.get_campaign(org_id, campaign_id)
        if row is None:
            raise CampaignNotFoundError()
        return self._to_campaign(row)

    def create_campaign(self, org_id: str, body: CampaignCreateBody) -> Campaign:
        name = _validate_name(body.name)
        area = _validate_area(body.area)
        if self.campaign_repository.get_by_name(org_id, name) is not None:
            raise CampaignConflictError("campaign name already exists")
        campaign_id = new_campaign_id()
        created_at = datetime.now(UTC).isoformat()
        self.campaign_repository.put_campaign(
            campaign_id=campaign_id,
            org_id=org_id,
            name=name,
            min_lat=area.min_lat,
            max_lat=area.max_lat,
            min_lon=area.min_lon,
            max_lon=area.max_lon,
            simulated=body.simulated,
            created_at=created_at,
        )
        row = self.campaign_repository.get_campaign(org_id, campaign_id)
        assert row is not None
        return self._to_campaign(row)

    def update_campaign(
        self,
        org_id: str,
        campaign_id: str,
        body: CampaignPatchBody,
    ) -> Campaign:
        existing = self.campaign_repository.get_campaign(org_id, campaign_id)
        if existing is None:
            raise CampaignNotFoundError()

        name = existing["name"]
        if body.name is not None:
            name = _validate_name(body.name)
            duplicate = self.campaign_repository.get_by_name(org_id, name)
            if duplicate is not None and duplicate["campaign_id"] != campaign_id:
                raise CampaignConflictError("campaign name already exists")

        min_lat = float(existing["min_lat"])
        max_lat = float(existing["max_lat"])
        min_lon = float(existing["min_lon"])
        max_lon = float(existing["max_lon"])
        if body.area is not None:
            area = _validate_area(body.area)
            if _area_changed(existing, area):
                analyses_count = int(existing.get("analyses_count") or 0)
                if analyses_count > 0:
                    raise CampaignConflictError(
                        "campaign area cannot be changed while analyses exist"
                    )
                min_lat = area.min_lat
                max_lat = area.max_lat
                min_lon = area.min_lon
                max_lon = area.max_lon

        simulated = bool(existing["simulated"])
        if body.simulated is not None:
            simulated = body.simulated

        self.campaign_repository.put_campaign(
            campaign_id=campaign_id,
            org_id=org_id,
            name=name,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            simulated=simulated,
            created_at=existing["created_at"],
        )
        row = self.campaign_repository.get_campaign(org_id, campaign_id)
        assert row is not None
        return self._to_campaign(row)

    def get_points(self, org_id: str, campaign_id: str) -> CampaignPointsResponse:
        campaign_row = self.campaign_repository.get_campaign(org_id, campaign_id)
        if campaign_row is None:
            raise CampaignNotFoundError()
        records = self.analysis_repository.list_by_campaign(
            org_id,
            campaign_id,
            limit=self.list_scan_cap,
        )
        campaign = self._to_campaign(campaign_row)
        points = [self._to_point(record) for record in records]
        return CampaignPointsResponse(campaign=campaign, points=points)

    @staticmethod
    def _to_campaign(row: dict) -> Campaign:
        return Campaign(
            id=row["campaign_id"],
            name=row["name"],
            area=CampaignArea(
                min_lat=float(row["min_lat"]),
                min_lon=float(row["min_lon"]),
                max_lat=float(row["max_lat"]),
                max_lon=float(row["max_lon"]),
            ),
            simulated=bool(row["simulated"]),
            analyses_count=int(row.get("analyses_count") or 0),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _to_point(record: dict) -> CampaignPoint:
        raw_detections = record.get("detections") or []
        primary = record.get("primary_class")
        return CampaignPoint(
            analysis_id=record["id"],
            lat=float(record["latitude"]),
            lon=float(record["longitude"]),
            location_source=record["location_source"],  # type: ignore[arg-type]
            primary_class=primary if primary in {"MILCO", "NOMBO"} else None,
            primary_confidence=_primary_confidence_from_raw(raw_detections),
            milco_detection_count=int(record.get("milco_detection_count") or 0),
            detection_count=len(raw_detections),
            created_at=datetime.fromisoformat(record["created_at"]),
        )


def _primary_confidence_from_raw(raw_detections: list) -> float | None:
    scored: list[tuple[str, float]] = []
    for row in raw_detections:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        confidence = row.get("confidence")
        if label not in {"MILCO", "NOMBO"} or confidence is None:
            continue
        try:
            scored.append((label, float(confidence)))
        except (TypeError, ValueError):
            continue
    if not scored:
        return None
    milco_scores = [value for label, value in scored if label == "MILCO"]
    if milco_scores:
        return max(milco_scores)
    return max(value for _, value in scored)


def _validate_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValidationError("name is required")
    if len(name) > MAX_CAMPAIGN_NAME_LEN:
        raise ValidationError("name must be at most 120 characters")
    return name


def _validate_area(area: CampaignArea) -> CampaignArea:
    values = (area.min_lat, area.max_lat, area.min_lon, area.max_lon)
    if not all(math.isfinite(value) for value in values):
        raise ValidationError("area bounds must be finite numbers")
    if area.min_lat >= area.max_lat:
        raise ValidationError("min_lat must be less than max_lat")
    if area.min_lon >= area.max_lon:
        raise ValidationError("min_lon must be less than max_lon")
    if not (-90 <= area.min_lat <= 90 and -90 <= area.max_lat <= 90):
        raise ValidationError("latitude must be between -90 and 90")
    if not (-180 <= area.min_lon <= 180 and -180 <= area.max_lon <= 180):
        raise ValidationError("longitude must be between -180 and 180")
    return area


def _area_changed(existing: dict, area: CampaignArea) -> bool:
    return (
        float(existing["min_lat"]) != area.min_lat
        or float(existing["max_lat"]) != area.max_lat
        or float(existing["min_lon"]) != area.min_lon
        or float(existing["max_lon"]) != area.max_lon
    )
