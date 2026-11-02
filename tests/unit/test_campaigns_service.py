from datetime import UTC, datetime

import pytest

from app.core.errors import CampaignConflictError, CampaignNotFoundError, ValidationError
from app.schemas.analysis import CampaignArea
from app.schemas.campaigns import CampaignCreateBody, CampaignPatchBody
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


VALID_AREA = CampaignArea(
    min_lat=38.6,
    min_lon=-9.5,
    max_lat=38.7,
    max_lon=-9.35,
)


class FakeCampaignRepository:
    def __init__(self, campaigns: list[dict] | None = None) -> None:
        self._campaigns = list(campaigns) if campaigns is not None else [dict(CAMPAIGN_ROW)]
        self.put_calls: list[dict] = []

    def list_by_org(self, org_id: str) -> list[dict]:
        return [row for row in self._campaigns if row["org_id"] == org_id]

    def get_campaign(self, org_id: str, campaign_id: str) -> dict | None:
        for row in self._campaigns:
            if row["org_id"] == org_id and row["campaign_id"] == campaign_id:
                return row
        return None

    def get_by_name(self, org_id: str, name: str) -> dict | None:
        for row in self._campaigns:
            if row["org_id"] == org_id and row["name"] == name:
                return row
        return None

    def put_campaign(self, **kwargs) -> None:
        self.put_calls.append(kwargs)
        for index, row in enumerate(self._campaigns):
            if row["org_id"] == kwargs["org_id"] and row["campaign_id"] == kwargs["campaign_id"]:
                self._campaigns[index] = {
                    **row,
                    "name": kwargs["name"],
                    "min_lat": kwargs["min_lat"],
                    "max_lat": kwargs["max_lat"],
                    "min_lon": kwargs["min_lon"],
                    "max_lon": kwargs["max_lon"],
                    "simulated": kwargs["simulated"],
                    "created_at": kwargs["created_at"],
                }
                return
        self._campaigns.append(
            {
                "campaign_id": kwargs["campaign_id"],
                "org_id": kwargs["org_id"],
                "name": kwargs["name"],
                "min_lat": kwargs["min_lat"],
                "max_lat": kwargs["max_lat"],
                "min_lon": kwargs["min_lon"],
                "max_lon": kwargs["max_lon"],
                "simulated": kwargs["simulated"],
                "created_at": kwargs["created_at"],
                "analyses_count": 0,
            }
        )


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
    assert point.created_at == datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def test_get_points_uses_list_scan_cap():
    service = build_service(list_scan_cap=321)

    service.get_points("org-1", "camp-1")

    assert service.analysis_repository.last_list_args == ("org-1", "camp-1", 321)


def test_get_campaign_returns_campaign_shape():
    service = build_service()

    campaign = service.get_campaign("org-1", "camp-1")

    assert campaign.id == "camp-1"
    assert campaign.analyses_count == 2


def test_get_campaign_unknown_raises_not_found():
    service = build_service(campaigns=[])

    with pytest.raises(CampaignNotFoundError):
        service.get_campaign("org-1", "missing")


def test_create_campaign_persists_with_analyses_count_zero():
    service = build_service(campaigns=[])

    created = service.create_campaign(
        "org-1",
        CampaignCreateBody(name="  New Campaign  ", area=VALID_AREA),
    )

    assert created.name == "New Campaign"
    assert created.analyses_count == 0
    assert created.simulated is False
    assert len(created.id) == 26
    assert service.campaign_repository.put_calls[0]["org_id"] == "org-1"


def test_create_campaign_rejects_empty_name():
    service = build_service(campaigns=[])

    with pytest.raises(ValidationError):
        service.create_campaign("org-1", CampaignCreateBody(name="   ", area=VALID_AREA))


def test_create_campaign_rejects_name_over_120_chars():
    service = build_service(campaigns=[])

    with pytest.raises(ValidationError):
        service.create_campaign(
            "org-1",
            CampaignCreateBody(name="x" * 121, area=VALID_AREA),
        )


def test_create_campaign_rejects_invalid_area_bounds():
    service = build_service(campaigns=[])

    with pytest.raises(ValidationError):
        service.create_campaign(
            "org-1",
            CampaignCreateBody(
                name="Bad",
                area=CampaignArea(
                    min_lat=38.7,
                    min_lon=-9.5,
                    max_lat=38.6,
                    max_lon=-9.35,
                ),
            ),
        )


def test_create_campaign_rejects_duplicate_name():
    service = build_service()

    with pytest.raises(CampaignConflictError) as excinfo:
        service.create_campaign("org-1", CampaignCreateBody(name="Alpha", area=VALID_AREA))

    assert excinfo.value.message == "campaign name already exists"


def test_update_campaign_rename_allowed_with_analyses():
    service = build_service()

    updated = service.update_campaign(
        "org-1",
        "camp-1",
        CampaignPatchBody(name="Renamed"),
    )

    assert updated.name == "Renamed"
    assert updated.analyses_count == 2


def test_update_campaign_area_blocked_when_analyses_exist():
    service = build_service()
    new_area = CampaignArea(
        min_lat=38.61,
        min_lon=-9.51,
        max_lat=38.71,
        max_lon=-9.36,
    )

    with pytest.raises(CampaignConflictError) as excinfo:
        service.update_campaign(
            "org-1",
            "camp-1",
            CampaignPatchBody(area=new_area),
        )

    assert excinfo.value.message == "campaign area cannot be changed while analyses exist"


def test_update_campaign_area_allowed_when_no_analyses():
    row = {**CAMPAIGN_ROW, "analyses_count": 0}
    service = build_service(campaigns=[row])
    new_area = CampaignArea(
        min_lat=38.61,
        min_lon=-9.51,
        max_lat=38.71,
        max_lon=-9.36,
    )

    updated = service.update_campaign(
        "org-1",
        "camp-1",
        CampaignPatchBody(area=new_area),
    )

    assert updated.area == new_area


def test_update_campaign_unknown_raises_not_found():
    service = build_service(campaigns=[])

    with pytest.raises(CampaignNotFoundError):
        service.update_campaign(
            "org-1",
            "missing",
            CampaignPatchBody(name="X"),
        )


def test_update_campaign_rejects_duplicate_name():
    service = build_service(
        campaigns=[
            CAMPAIGN_ROW,
            {
                **CAMPAIGN_ROW,
                "campaign_id": "camp-2",
                "name": "Beta",
                "analyses_count": 0,
            },
        ]
    )

    with pytest.raises(CampaignConflictError) as excinfo:
        service.update_campaign(
            "org-1",
            "camp-1",
            CampaignPatchBody(name="Beta"),
        )

    assert excinfo.value.message == "campaign name already exists"
