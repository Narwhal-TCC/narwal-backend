import sqlite3
from pathlib import Path

import pytest

from app.core.errors import StoreUnavailableError
from app.repositories.analyses import AnalysisRepository, _to_record, new_analysis_id
from app.repositories.campaigns import CampaignRepository, new_campaign_id

DETECTIONS = [
    {
        "x1": 12.5,
        "y1": 30.0,
        "x2": 80.25,
        "y2": 140.75,
        "confidence": 0.87,
        "label": "MILCO",
        "detector_score": 0.91,
    }
]

DETECTIONS_088 = [
    {
        "x1": 1.0,
        "y1": 2.0,
        "x2": 3.0,
        "y2": 4.0,
        "confidence": 0.88,
        "label": "MILCO",
        "detector_score": 0.9,
    }
]


@pytest.fixture
def repository(tmp_path: Path):
    db_path = tmp_path / "analyses.db"
    return AnalysisRepository(str(db_path)), db_path


def _put(
    repository,
    analysis_id,
    org_id,
    user_id="user-1",
    created_at="2026-09-13T12:00:00+00:00",
    detections=None,
):
    return repository.put_analysis(
        analysis_id=analysis_id,
        org_id=org_id,
        user_id=user_id,
        detections=detections or DETECTIONS,
        image_s3_key=f"analyses/{org_id}/{analysis_id}/original.png",
        image_content_type="image/png",
        created_at=created_at,
        inference_ms=42,
    )


def test_put_then_get_returns_same_detections(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")

    record = repo.get_analysis("org-1", "an-1")

    assert record["detections"] == DETECTIONS
    assert record["id"] == "an-1"
    assert record["org_id"] == "org-1"
    assert record["user_id"] == "user-1"
    assert record["status"] == "succeeded"
    assert record["image_s3_key"] == "analyses/org-1/an-1/original.png"
    assert record["image_content_type"] == "image/png"
    assert record["created_at"] == "2026-09-13T12:00:00+00:00"
    assert record["inference_ms"] == 42


def test_confidence_088_round_trips_as_float(repository):
    repo, _ = repository
    _put(repo, "an-float", "org-1", detections=DETECTIONS_088)

    record = repo.get_analysis("org-1", "an-float")

    confidence = record["detections"][0]["confidence"]
    assert confidence == 0.88
    assert isinstance(confidence, float)


def test_list_returns_newest_created_at_first(repository):
    repo, _ = repository
    _put(repo, "an-older", "org-1", created_at="2026-09-10T12:00:00+00:00")
    _put(repo, "an-newer", "org-1", created_at="2026-09-13T12:00:00+00:00")

    records = repo.list_by_org("org-1")

    assert [record["id"] for record in records] == ["an-newer", "an-older"]


def test_list_returns_only_requested_org(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")
    _put(repo, "an-2", "org-1")
    _put(repo, "an-3", "org-2")

    records = repo.list_by_org("org-1")

    assert len(records) == 2
    assert all(record["org_id"] == "org-1" for record in records)


def test_get_with_other_org_returns_none(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")

    assert repo.get_analysis("org-2", "an-1") is None


def test_list_for_org_without_analyses_returns_empty(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")

    assert repo.list_by_org("org-2") == []


def test_list_applies_limit_and_offset(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1", created_at="2026-09-11T12:00:00+00:00")
    _put(repo, "an-2", "org-1", created_at="2026-09-12T12:00:00+00:00")
    _put(repo, "an-3", "org-1", created_at="2026-09-13T12:00:00+00:00")

    page = repo.list_by_org("org-1", limit=1, offset=1)

    assert [record["id"] for record in page] == ["an-2"]


def test_new_analysis_id_is_unique_and_time_sortable():
    first = new_analysis_id()
    second = new_analysis_id()

    assert first != second
    assert first < second


def test_put_parity_fields_round_trip(repository):
    repo, _ = repository
    repo.put_analysis(
        analysis_id="an-parity",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-parity/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
        inference_ms=42,
        review_status="pending",
        primary_class="MILCO",
        campaign_name="Alpha",
        collected_at="2026-09-12T08:30:00+00:00",
        milco_detection_count=1,
    )

    record = repo.get_analysis("org-1", "an-parity")

    assert record["review_status"] == "pending"
    assert record["primary_class"] == "MILCO"
    assert record["campaign_name"] == "Alpha"
    assert record["coordinates"] is None
    assert record["collected_at"] == "2026-09-12T08:30:00+00:00"
    assert record["milco_detection_count"] == 1


def test_update_review_status_confirmed_round_trips(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")

    updated = repo.update_review_status("org-1", "an-1", "confirmed")

    assert updated is not None
    assert updated["review_status"] == "confirmed"
    assert updated["status"] == "succeeded"
    assert updated["detections"] == DETECTIONS
    assert repo.get_analysis("org-1", "an-1")["review_status"] == "confirmed"


def test_update_review_status_missing_returns_none(repository):
    repo, _ = repository
    assert repo.update_review_status("org-1", "missing", "confirmed") is None


def test_image_s3_key_persisted_without_blob_column(repository):
    repo, db_path = repository
    _put(repo, "an-1", "org-1")

    conn = sqlite3.connect(db_path)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
    }
    conn.close()

    record = repo.get_analysis("org-1", "an-1")
    assert record["image_s3_key"] == "analyses/org-1/an-1/original.png"
    assert "image_blob" not in columns


def test_put_get_round_trips_default_model_id_balanced(repository):
    repo, _ = repository
    _put(repo, "an-model", "org-1")

    record = repo.get_analysis("org-1", "an-model")

    assert record["model_id"] == "yolo-convnext-balanced"


def test_null_model_id_in_sql_reads_back_as_two_stage_pt():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE analyses (
          analysis_id TEXT, org_id TEXT, user_id TEXT, status TEXT,
          review_status TEXT, primary_class TEXT, campaign_name TEXT,
          coordinates TEXT, collected_at TEXT, milco_detection_count INTEGER,
          detections TEXT, image_s3_key TEXT, image_content_type TEXT,
          created_at TEXT, inference_ms INTEGER, model_id TEXT,
          ai_analysis_json TEXT, ai_status TEXT, ai_reason TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "an-null-model",
            "org-1",
            "user-1",
            "succeeded",
            "pending",
            None,
            None,
            None,
            None,
            0,
            "[]",
            "analyses/org-1/an-null-model/original.png",
            "image/png",
            "2026-09-13T12:00:00+00:00",
            42,
            None,
            None,
            None,
            None,
        ),
    )
    row = conn.execute("SELECT * FROM analyses").fetchone()
    conn.close()

    assert _to_record(row)["model_id"] == "two-stage-pt"


def test_reopen_same_path_returns_stored_analysis(repository):
    repo, db_path = repository
    _put(repo, "an-persist", "org-1", created_at="2026-09-14T10:00:00+00:00")

    reopened = AnalysisRepository(str(db_path))
    record = reopened.get_analysis("org-1", "an-persist")

    assert record is not None
    assert record["id"] == "an-persist"
    assert record["created_at"] == "2026-09-14T10:00:00+00:00"


class _ConnectionProxy:
    def __init__(self, inner: sqlite3.Connection) -> None:
        self._inner = inner

    def execute(self, sql, params=(), /, **kwargs):
        if "INSERT INTO analyses" in str(sql):
            raise sqlite3.OperationalError("forced insert failure")
        return self._inner.execute(sql, params, **kwargs)

    def commit(self):
        return self._inner.commit()

    def rollback(self):
        return self._inner.rollback()

    def close(self):
        return self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_location_fields_round_trip(repository):
    repo, _ = repository
    repo.put_analysis(
        analysis_id="an-loc",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-loc/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
        campaign_id="camp-1",
        latitude=38.6500001,
        longitude=-9.4200001,
        location_source="entered",
    )

    record = repo.get_analysis("org-1", "an-loc")

    assert record["latitude"] == 38.6500001
    assert record["longitude"] == -9.4200001
    assert record["location_source"] == "entered"
    assert record["coordinates"] is None


def test_list_by_campaign_returns_only_positioned_rows_for_campaign_and_org(repository):
    repo, db_path = repository
    campaigns = CampaignRepository(str(db_path))
    campaign_a = new_campaign_id()
    campaign_b = new_campaign_id()
    for campaign_id, org_id in (
        (campaign_a, "org-1"),
        (campaign_b, "org-1"),
        (campaign_a, "org-2"),
    ):
        campaigns.put_campaign(
            campaign_id=campaign_id,
            org_id=org_id,
            name=f"Campaign {campaign_id}",
            min_lat=38.6,
            max_lat=38.7,
            min_lon=-9.5,
            max_lon=-9.35,
            simulated=True,
            created_at="2026-09-01T12:00:00+00:00",
        )

    repo.put_analysis(
        analysis_id="an-in-a",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-in-a/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
        campaign_id=campaign_a,
        latitude=38.65,
        longitude=-9.42,
        location_source="simulated",
    )
    repo.put_analysis(
        analysis_id="an-other-campaign",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-other-campaign/original.png",
        image_content_type="image/png",
        created_at="2026-09-12T12:00:00+00:00",
        campaign_id=campaign_b,
        latitude=38.61,
        longitude=-9.41,
        location_source="simulated",
    )
    repo.put_analysis(
        analysis_id="an-no-position",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-no-position/original.png",
        image_content_type="image/png",
        created_at="2026-09-11T12:00:00+00:00",
        campaign_id=campaign_a,
    )
    repo.put_analysis(
        analysis_id="an-other-org",
        org_id="org-2",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-2/an-other-org/original.png",
        image_content_type="image/png",
        created_at="2026-09-10T12:00:00+00:00",
        campaign_id=campaign_a,
        latitude=38.62,
        longitude=-9.43,
        location_source="simulated",
    )

    points = repo.list_by_campaign("org-1", campaign_a)

    assert [row["id"] for row in points] == ["an-in-a"]


def test_failed_insert_raises_store_unavailable_and_leaves_list_unchanged(repository):
    repo, _ = repository
    _put(repo, "an-1", "org-1")
    real_with_connection = repo._with_connection

    def failing_with_connection():
        return _ConnectionProxy(real_with_connection())

    repo._with_connection = failing_with_connection  # type: ignore[method-assign]
    with pytest.raises(StoreUnavailableError):
        repo.put_analysis(
            analysis_id="an-2",
            org_id="org-1",
            user_id="user-1",
            detections=DETECTIONS,
            image_s3_key="analyses/org-1/an-2/original.png",
            image_content_type="image/png",
            created_at="2026-09-14T11:00:00+00:00",
        )

    assert [row["id"] for row in repo.list_by_org("org-1")] == ["an-1"]
