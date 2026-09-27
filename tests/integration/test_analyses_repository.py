import boto3
import pytest
from moto import mock_aws

from app.repositories.analyses import AnalysisRepository, new_analysis_id
from app.repositories.users import ensure_table

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


@pytest.fixture
def repository():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ensure_table(dynamodb, "analyses-test")
        yield AnalysisRepository(table)


def _put(repository, analysis_id, org_id, user_id="user-1", created_at="2026-09-13T12:00:00+00:00"):
    return repository.put_analysis(
        analysis_id=analysis_id,
        org_id=org_id,
        user_id=user_id,
        detections=DETECTIONS,
        image_s3_key=f"analyses/{org_id}/{analysis_id}/original.png",
        image_content_type="image/png",
        created_at=created_at,
        inference_ms=42,
    )


def test_put_then_get_returns_same_detections(repository):
    _put(repository, "an-1", "org-1")

    record = repository.get_analysis("org-1", "an-1")

    assert record["detections"] == DETECTIONS
    assert record["id"] == "an-1"
    assert record["org_id"] == "org-1"
    assert record["user_id"] == "user-1"
    assert record["status"] == "succeeded"
    assert record["image_s3_key"] == "analyses/org-1/an-1/original.png"
    assert record["image_content_type"] == "image/png"
    assert record["created_at"] == "2026-09-13T12:00:00+00:00"
    assert record["inference_ms"] == 42


def test_list_returns_only_requested_org_newest_first(repository):
    _put(repository, "an-1", "org-1")
    _put(repository, "an-2", "org-1")
    _put(repository, "an-3", "org-2")

    records = repository.list_by_org("org-1")

    assert [record["id"] for record in records] == ["an-2", "an-1"]


def test_get_with_other_org_returns_none(repository):
    _put(repository, "an-1", "org-1")

    assert repository.get_analysis("org-2", "an-1") is None


def test_list_for_org_without_analyses_returns_empty(repository):
    _put(repository, "an-1", "org-1")

    assert repository.list_by_org("org-2") == []


def test_list_applies_limit_and_offset(repository):
    _put(repository, "an-1", "org-1")
    _put(repository, "an-2", "org-1")
    _put(repository, "an-3", "org-1")

    page = repository.list_by_org("org-1", limit=1, offset=1)

    assert [record["id"] for record in page] == ["an-2"]


def test_new_analysis_id_is_unique_and_time_sortable():
    first = new_analysis_id()
    second = new_analysis_id()

    assert first != second
    assert first < second


def test_put_parity_fields_round_trip(repository):
    repository.put_analysis(
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
        coordinates="-23.5,-46.6",
        collected_at="2026-09-12T08:30:00+00:00",
        milco_detection_count=1,
    )

    record = repository.get_analysis("org-1", "an-parity")

    assert record["review_status"] == "pending"
    assert record["primary_class"] == "MILCO"
    assert record["campaign_name"] == "Alpha"
    assert record["coordinates"] == "-23.5,-46.6"
    assert record["collected_at"] == "2026-09-12T08:30:00+00:00"
    assert record["milco_detection_count"] == 1


def test_update_review_status_updates_only_review_status(repository):
    _put(repository, "an-1", "org-1")

    updated = repository.update_review_status("org-1", "an-1", "confirmed")

    assert updated is not None
    assert updated["review_status"] == "confirmed"
    assert updated["status"] == "succeeded"
    assert updated["detections"] == DETECTIONS
    assert repository.get_analysis("org-1", "an-1")["review_status"] == "confirmed"


def test_update_review_status_missing_returns_none(repository):
    assert repository.update_review_status("org-1", "missing", "confirmed") is None
