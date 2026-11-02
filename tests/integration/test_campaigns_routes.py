from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_campaign_service, get_user_repository
from app.core.config import get_settings
from app.core.security import hash_password
from app.main import app
from app.repositories.analyses import AnalysisRepository
from app.repositories.campaigns import CampaignRepository
from app.repositories.users import UserRepository
from app.services.campaigns import CampaignService

CAMPAIGN_AREA = {
    "min_lat": 38.6,
    "max_lat": 38.7,
    "min_lon": -9.5,
    "max_lon": -9.35,
}


def _put_campaign(
    repo: CampaignRepository,
    *,
    org_id: str,
    campaign_id: str,
    name: str,
) -> None:
    repo.put_campaign(
        campaign_id=campaign_id,
        org_id=org_id,
        name=name,
        simulated=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
        **CAMPAIGN_AREA,
    )


@pytest.fixture
def campaigns_client(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "campaigns-routes.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    get_settings.cache_clear()

    users = UserRepository(str(db_path))
    users.put_org("org-1", "Sonar Team")
    users.put_user("user-1", "org-1", "operator", hash_password("pw"), "member")
    users.put_org("org-2", "Rival Team")
    users.put_user("user-2", "org-2", "rival", hash_password("pw"), "member")

    campaign_repo = CampaignRepository(str(db_path))
    campaign_repo.put_campaign(
        campaign_id="camp-older",
        org_id="org-1",
        name="Older Campaign",
        simulated=True,
        created_at=datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
        **CAMPAIGN_AREA,
    )
    campaign_repo.put_campaign(
        campaign_id="camp-newer",
        org_id="org-1",
        name="Newer Campaign",
        simulated=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
        **CAMPAIGN_AREA,
    )
    _put_campaign(
        campaign_repo,
        org_id="org-2",
        campaign_id="camp-rival",
        name="Rival Campaign",
    )

    analyses = AnalysisRepository(str(db_path))
    analyses.put_analysis(
        analysis_id="an-pointed",
        org_id="org-1",
        user_id="user-1",
        status="succeeded",
        primary_class="MILCO",
        campaign_id="camp-newer",
        latitude=38.65,
        longitude=-9.42,
        location_source="entered",
        milco_detection_count=1,
        detections=[{"label": "MILCO", "confidence": 0.9}],
        image_s3_key="analyses/org-1/an-pointed/original.png",
        image_content_type="image/png",
        created_at=datetime(2026, 9, 15, tzinfo=UTC).isoformat(),
    )

    campaign_service = CampaignService(
        campaign_repository=campaign_repo,
        analysis_repository=analyses,
    )
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_campaign_service] = lambda: campaign_service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _auth_headers(client: TestClient, username: str) -> dict[str, str]:
    token = client.post("/auth/login", json={"username": username, "password": "pw"}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_list_campaigns_returns_org_campaigns_newest_first(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == "camp-newer"
    assert body[0]["name"] == "Newer Campaign"
    assert body[0]["area"] == CAMPAIGN_AREA
    assert body[0]["simulated"] is True
    assert body[0]["analyses_count"] == 1
    assert body[1]["id"] == "camp-older"
    assert body[1]["analyses_count"] == 0


def test_list_campaigns_empty_org_returns_empty_array(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "campaigns-empty.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-at-least-32-bytes")
    get_settings.cache_clear()
    users = UserRepository(str(db_path))
    users.put_org("empty-org", "Empty")
    users.put_user("empty-user", "empty-org", "lonely", hash_password("pw"), "member")
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_campaign_service] = lambda: CampaignService()
    with TestClient(app) as client:
        headers = _auth_headers(client, "lonely")
        response = client.get("/campaigns", headers=headers)
    app.dependency_overrides.clear()
    get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == []


def test_list_campaigns_without_token_returns_401(campaigns_client):
    response = campaigns_client.get("/campaigns")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_get_campaign_points_returns_positioned_analyses(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns/camp-newer/points", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["campaign"]["id"] == "camp-newer"
    assert len(body["points"]) == 1
    point = body["points"][0]
    assert point["analysis_id"] == "an-pointed"
    assert point["lat"] == 38.65
    assert point["lon"] == -9.42
    assert point["location_source"] == "entered"
    assert point["primary_class"] == "MILCO"
    assert point["milco_detection_count"] == 1
    assert point["detection_count"] == 1
    assert point["created_at"] == "2026-09-15T00:00:00Z"


def test_get_campaign_points_empty_campaign_returns_empty_points(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns/camp-older/points", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["campaign"]["id"] == "camp-older"
    assert body["points"] == []


def test_get_campaign_points_cross_org_returns_404(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns/camp-rival/points", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "CAMPAIGN_NOT_FOUND"


def test_create_campaign_returns_201_with_defaults(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.post(
        "/campaigns",
        headers=headers,
        json={"name": "Created Campaign", "area": CAMPAIGN_AREA},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Created Campaign"
    assert body["area"] == CAMPAIGN_AREA
    assert body["simulated"] is False
    assert body["analyses_count"] == 0
    assert body["id"]


def test_create_campaign_duplicate_name_returns_409(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.post(
        "/campaigns",
        headers=headers,
        json={"name": "Newer Campaign", "area": CAMPAIGN_AREA},
    )

    assert response.status_code == 409
    assert response.json()["message"] == "campaign name already exists"


def test_create_campaign_invalid_name_returns_400(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.post(
        "/campaigns",
        headers=headers,
        json={"name": "   ", "area": CAMPAIGN_AREA},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_campaign_without_token_returns_401(campaigns_client):
    response = campaigns_client.post(
        "/campaigns",
        json={"name": "No Auth", "area": CAMPAIGN_AREA},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_get_campaign_returns_org_campaign(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns/camp-newer", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "camp-newer"
    assert body["name"] == "Newer Campaign"
    assert body["analyses_count"] == 1


def test_get_campaign_cross_org_returns_404(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.get("/campaigns/camp-rival", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "CAMPAIGN_NOT_FOUND"


def test_get_campaign_without_token_returns_401(campaigns_client):
    response = campaigns_client.get("/campaigns/camp-newer")

    assert response.status_code == 401


def test_patch_campaign_rename_succeeds_with_analyses(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.patch(
        "/campaigns/camp-newer",
        headers=headers,
        json={"name": "Renamed Campaign"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Campaign"
    assert response.json()["analyses_count"] == 1


def test_patch_campaign_area_blocked_when_analyses_exist(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.patch(
        "/campaigns/camp-newer",
        headers=headers,
        json={
            "area": {
                "min_lat": 38.61,
                "min_lon": -9.51,
                "max_lat": 38.71,
                "max_lon": -9.36,
            }
        },
    )

    assert response.status_code == 409
    assert response.json()["message"] == "campaign area cannot be changed while analyses exist"


def test_patch_campaign_empty_body_returns_400(campaigns_client):
    headers = _auth_headers(campaigns_client, "operator")

    response = campaigns_client.patch("/campaigns/camp-older", headers=headers, json={})

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_patch_campaign_without_token_returns_401(campaigns_client):
    response = campaigns_client.patch("/campaigns/camp-older", json={"name": "X"})

    assert response.status_code == 401
