from datetime import datetime

from app.core.config import get_settings
from app.core.errors import CampaignNotFoundError
from app.repositories.analyses import AnalysisRepository
from app.repositories.campaigns import CampaignRepository
from app.schemas.analysis import (
    Campaign,
    CampaignArea,
    CampaignPoint,
    CampaignPointsResponse,
)


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
        detections = record.get("detections") or []
        primary = record.get("primary_class")
        return CampaignPoint(
            analysis_id=record["id"],
            lat=float(record["latitude"]),
            lon=float(record["longitude"]),
            location_source=record["location_source"],  # type: ignore[arg-type]
            primary_class=primary if primary in {"MILCO", "NOMBO"} else None,
            milco_detection_count=int(record.get("milco_detection_count") or 0),
            detection_count=len(detections),
            created_at=datetime.fromisoformat(record["created_at"]),
        )
