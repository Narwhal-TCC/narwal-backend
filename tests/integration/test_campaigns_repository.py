import sqlite3
from pathlib import Path

from app.repositories.campaigns import CampaignRepository


def _insert_analysis(
    db_path: Path,
    *,
    analysis_id: str,
    org_id: str,
    campaign_id: str | None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO analyses (
              analysis_id, org_id, user_id, status, review_status,
              milco_detection_count, detections, image_s3_key,
              image_content_type, created_at, model_id, campaign_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                org_id,
                "user-1",
                "succeeded",
                "pending",
                0,
                "[]",
                f"analyses/{org_id}/{analysis_id}/original.png",
                "image/png",
                "2026-09-13T12:00:00+00:00",
                "two-stage-pt",
                campaign_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_get_campaign_returns_none_for_other_org(tmp_path: Path):
    db_path = tmp_path / "campaigns-org.db"
    repository = CampaignRepository(str(db_path))
    repository.put_campaign(
        campaign_id="camp-1",
        org_id="org-a",
        name="Alpha",
        min_lat=38.6,
        max_lat=38.7,
        min_lon=-9.5,
        max_lon=-9.35,
        simulated=True,
        created_at="2026-11-01T10:00:00+00:00",
    )

    assert repository.get_campaign("org-a", "camp-1") is not None
    assert repository.get_campaign("org-b", "camp-1") is None


def test_get_campaign_includes_analyses_count(tmp_path: Path):
    db_path = tmp_path / "campaigns-get-count.db"
    repository = CampaignRepository(str(db_path))
    repository.put_campaign(
        campaign_id="camp-1",
        org_id="org-1",
        name="Alpha",
        min_lat=38.6,
        max_lat=38.7,
        min_lon=-9.5,
        max_lon=-9.35,
        simulated=True,
        created_at="2026-11-01T10:00:00+00:00",
    )
    _insert_analysis(db_path, analysis_id="an-1", org_id="org-1", campaign_id="camp-1")
    _insert_analysis(db_path, analysis_id="an-2", org_id="org-1", campaign_id="camp-1")

    row = repository.get_campaign("org-1", "camp-1")

    assert row is not None
    assert row["analyses_count"] == 2


def test_list_by_org_orders_newest_first_and_counts_analyses(tmp_path: Path):
    db_path = tmp_path / "campaigns-list.db"
    repository = CampaignRepository(str(db_path))
    repository.put_campaign(
        campaign_id="camp-old",
        org_id="org-1",
        name="Older",
        min_lat=38.6,
        max_lat=38.7,
        min_lon=-9.5,
        max_lon=-9.35,
        simulated=True,
        created_at="2026-10-01T10:00:00+00:00",
    )
    repository.put_campaign(
        campaign_id="camp-new",
        org_id="org-1",
        name="Newer",
        min_lat=38.6,
        max_lat=38.7,
        min_lon=-9.5,
        max_lon=-9.35,
        simulated=True,
        created_at="2026-11-01T10:00:00+00:00",
    )
    _insert_analysis(db_path, analysis_id="an-1", org_id="org-1", campaign_id="camp-old")
    _insert_analysis(db_path, analysis_id="an-2", org_id="org-1", campaign_id="camp-old")
    _insert_analysis(db_path, analysis_id="an-3", org_id="org-1", campaign_id="camp-new")

    listed = repository.list_by_org("org-1")

    assert [row["campaign_id"] for row in listed] == ["camp-new", "camp-old"]
    counts = {row["campaign_id"]: row["analyses_count"] for row in listed}
    assert counts == {"camp-old": 2, "camp-new": 1}
