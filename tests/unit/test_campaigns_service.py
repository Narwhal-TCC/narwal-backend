from datetime import UTC, datetime

import pytest

from app.core.errors import CampaignNotFoundError
from app.services.campaigns import CampaignService

CAMPAIGN_ROW = {
    "campaign_id": "camp-1",
    "org_id": "org-1",
    "name": "Alpha",
    "min_lat": 38.6,
    "max_lat": 38.7,
    "min_lon": -9.5,
    "max_lon": -9.35,
    "simulated": True,
    "created_at": "2026-09-01T12:00:00+00:00",
    "analyses_count": 2,
}


class FakeCampaignRepository:
    def __init__(self, campaigns: list[dict] | None = None) -> None:
        self._campaigns = campaigns or [CAMPAIGN_ROW]

    def list_by_org(self, org_id: str) -> list[dict]:
        return [row for row in self._campaigns if row["org_id"] == org_id]

    def get_campaign(self, org_id: str, campaign_id: str) -> dict | None:
        for row in self._campaigns:
            if row["org_id"] == org_id and row["campaign_id"] == campaign_id:
                return row
        return None


class FakeAnalysisRepository:
    def __init__(self, points: list[dict] | None = None) -> None:
        self._points = points or []
        self.last_list_args: tuple[str, str, int] | None = None

    def list_by_campaign(self, org_id: str, campaign_id: str, limit: int = 500) -> list[dict]:
        self.last_list_args = (org_id, campaign_id, limit)
        return [
            row
            for row in self._points
            if row["org_id"] == org_id and row["campaign_id"] == campaign_id
        ]


def build_service(
    campaigns: list[dict] | None = None,
    points: list[dict] | None = None,
    list_scan_cap: int = 500,
) -> CampaignService:
    return CampaignService(
        campaign_repository=FakeCampaignRepository(campaigns),
        analysis_repository=FakeAnalysisRepository(points),
        list_scan_cap=list_scan_cap,
    )


def test_list_campaigns_maps_campaign_shape():
    service = build_service()

    campaigns = service.list_campaigns("org-1")

    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign.id == "camp-1"
    assert campaign.name == "Alpha"
    assert campaign.area.min_lat == 38.6
    assert campaign.area.max_lon == -9.35
    assert campaign.simulated is True
    assert campaign.analyses_count == 2
    assert campaign.created_at == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_get_points_empty_campaign_returns_empty_list():
    service = build_service(points=[])

    response = service.get_points("org-1", "camp-1")

    assert response.campaign.id == "camp-1"
    assert response.points == []


def test_get_points_unknown_campaign_raises_not_found():
    service = build_service(campaigns=[])

    with pytest.raises(CampaignNotFoundError) as excinfo:
        service.get_points("org-1", "missing")

    assert excinfo.value.status_code == 404


def test_get_points_maps_positioned_analyses():
    service = build_service(
        points=[
            {
                "id": "an-1",
                "org_id": "org-1",
                "campaign_id": "camp-1",
                "latitude": 38.65,
                "longitude": -9.42,
                "location_source": "simulated",
                "primary_class": "MILCO",
                "milco_detection_count": 1,
                "detections": [{"label": "MILCO"}],
                "created_at": "2026-09-13T12:00:00+00:00",
            }
        ]
    )

    response = service.get_points("org-1", "camp-1")

    assert len(response.points) == 1
    point = response.points[0]
    assert point.analysis_id == "an-1"
    assert point.lat == 38.65
    assert point.lon == -9.42
    assert point.location_source == "simulated"
    assert point.primary_class == "MILCO"
    assert point.milco_detection_count == 1
    assert point.detection_count == 1


def test_get_points_uses_list_scan_cap():
    service = build_service(list_scan_cap=321)

    service.get_points("org-1", "camp-1")

    assert service.analysis_repository.last_list_args == ("org-1", "camp-1", 321)
