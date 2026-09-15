import pytest

from app.core.errors import AnalysisNotFoundError, ValidationError
from app.services.history import HistoryService

DETECTIONS = [
    {"x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0, "confidence": 0.75, "label": "NOMBO"}
]


def record(
    analysis_id: str,
    org_id: str,
    *,
    primary_class: str | None = "NOMBO",
    campaign_name: str | None = None,
    review_status: str = "pending",
    milco_detection_count: int = 0,
    coordinates: str | None = None,
    collected_at: str | None = None,
    created_at: str = "2026-09-13T12:00:00+00:00",
) -> dict:
    return {
        "id": analysis_id,
        "org_id": org_id,
        "user_id": "user-1",
        "status": "succeeded",
        "review_status": review_status,
        "primary_class": primary_class,
        "campaign_name": campaign_name,
        "coordinates": coordinates,
        "collected_at": collected_at,
        "milco_detection_count": milco_detection_count,
        "detections": DETECTIONS,
        "image_s3_key": f"analyses/{org_id}/{analysis_id}/original.png",
        "image_content_type": "image/png",
        "created_at": created_at,
        "inference_ms": 42,
    }


class FakeAnalysisRepository:
    def __init__(self, records: list[dict]) -> None:
        self.records = [dict(item) for item in records]
        self.last_list_limit: int | None = None

    def list_by_org(self, org_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        self.last_list_limit = limit
        scoped = [item for item in self.records if item["org_id"] == org_id]
        return scoped[offset : offset + limit]

    def get_analysis(self, org_id: str, analysis_id: str) -> dict | None:
        for item in self.records:
            if item["org_id"] == org_id and item["id"] == analysis_id:
                return item
        return None

    def update_review_status(
        self,
        org_id: str,
        analysis_id: str,
        review_status: str,
    ) -> dict | None:
        for item in self.records:
            if item["org_id"] == org_id and item["id"] == analysis_id:
                item["review_status"] = review_status
                return dict(item)
        return None


class FakeObjectStore:
    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        return f"http://localhost:9000/narwal/{key}?X-Amz-Expires={expires_seconds}"


def build_service(records: list[dict], list_scan_cap: int = 500) -> HistoryService:
    return HistoryService(
        repository=FakeAnalysisRepository(records),
        object_store=FakeObjectStore(),
        list_scan_cap=list_scan_cap,
    )


def test_list_returns_only_caller_org_analyses():
    service = build_service([record("an-1", "org-1"), record("an-2", "org-2")])

    page = service.list_analyses("org-1")

    assert [item.id for item in page.items] == ["an-1"]
    assert page.items[0].org_id == "org-1"
    assert page.items[0].detection_count == 1
    assert page.items[0].status == "succeeded"


def test_list_for_org_without_analyses_returns_empty_page():
    service = build_service([record("an-1", "org-2")])

    page = service.list_analyses("org-1", limit=10, offset=0)

    assert page.items == []
    assert page.limit == 10
    assert page.offset == 0


def test_get_returns_detections_and_presigned_image_url():
    service = build_service([record("an-1", "org-1")])

    result = service.get_analysis("org-1", "an-1")

    assert result.id == "an-1"
    assert result.image_s3_key == "analyses/org-1/an-1/original.png"
    assert result.image_url == (
        "http://localhost:9000/narwal/analyses/org-1/an-1/original.png?X-Amz-Expires=900"
    )
    assert len(result.detections) == 1
    assert result.detections[0].confidence == 0.75


def test_get_for_another_org_analysis_raises_not_found():
    service = build_service([record("an-1", "org-2")])

    with pytest.raises(AnalysisNotFoundError) as excinfo:
        service.get_analysis("org-1", "an-1")

    assert excinfo.value.code == "ANALYSIS_NOT_FOUND"
    assert excinfo.value.status_code == 404


def test_get_for_unknown_analysis_raises_not_found():
    service = build_service([record("an-1", "org-1")])

    with pytest.raises(AnalysisNotFoundError) as excinfo:
        service.get_analysis("org-1", "missing")

    assert excinfo.value.code == "ANALYSIS_NOT_FOUND"


def test_list_q_filters_by_id_substring():
    service = build_service(
        [
            record("alpha-1", "org-1"),
            record("beta-2", "org-1"),
        ]
    )

    page = service.list_analyses("org-1", q="alpha")

    assert [item.id for item in page.items] == ["alpha-1"]


def test_list_q_filters_by_campaign_name_case_insensitive():
    service = build_service(
        [
            record("an-1", "org-1", campaign_name="North Survey"),
            record("an-2", "org-1", campaign_name="South Run"),
        ]
    )

    page = service.list_analyses("org-1", q="north")

    assert [item.id for item in page.items] == ["an-1"]


def test_list_whitespace_q_is_no_op():
    records = [record("an-1", "org-1"), record("an-2", "org-1")]
    service = build_service(records)

    page = service.list_analyses("org-1", q="   ")

    assert [item.id for item in page.items] == ["an-1", "an-2"]


def test_list_class_milco_excludes_nombo_and_null_primary():
    service = build_service(
        [
            record("milco-1", "org-1", primary_class="MILCO"),
            record("nombo-1", "org-1", primary_class="NOMBO"),
            record("null-1", "org-1", primary_class=None),
        ]
    )

    page = service.list_analyses("org-1", class_filter="MILCO")

    assert [item.id for item in page.items] == ["milco-1"]


def test_list_class_nombo():
    service = build_service(
        [
            record("milco-1", "org-1", primary_class="MILCO"),
            record("nombo-1", "org-1", primary_class="NOMBO"),
        ]
    )

    page = service.list_analyses("org-1", class_filter="NOMBO")

    assert [item.id for item in page.items] == ["nombo-1"]


def test_list_invalid_class_raises_validation_error():
    service = build_service([record("an-1", "org-1")])

    with pytest.raises(ValidationError) as excinfo:
        service.list_analyses("org-1", class_filter="UNKNOWN")  # type: ignore[arg-type]

    assert excinfo.value.status_code == 400


def test_list_q_and_class_apply_together():
    service = build_service(
        [
            record("alpha-milco", "org-1", primary_class="MILCO", campaign_name="Alpha"),
            record("alpha-nombo", "org-1", primary_class="NOMBO", campaign_name="Alpha"),
            record("beta-milco", "org-1", primary_class="MILCO", campaign_name="Beta"),
        ]
    )

    page = service.list_analyses("org-1", q="alpha", class_filter="MILCO")

    assert [item.id for item in page.items] == ["alpha-milco"]


def test_list_maps_parity_fields_on_summary():
    service = build_service(
        [
            record(
                "an-1",
                "org-1",
                primary_class="MILCO",
                campaign_name="Alpha",
                coordinates="-23.5,-46.6",
                collected_at="2026-09-12T08:30:00+00:00",
                review_status="confirmed",
                milco_detection_count=2,
            )
        ]
    )

    summary = service.list_analyses("org-1").items[0]

    assert summary.review_status == "confirmed"
    assert summary.primary_class == "MILCO"
    assert summary.campaign_name == "Alpha"
    assert summary.coordinates == "-23.5,-46.6"
    assert summary.collected_at is not None
    assert summary.milco_detection_count == 2


@pytest.mark.parametrize(
    ("initial", "updated"),
    [
        ("pending", "confirmed"),
        ("confirmed", "false_positive"),
        ("false_positive", "pending"),
    ],
)
def test_update_review_status_accepts_free_transitions(initial, updated):
    service = build_service([record("an-1", "org-1", review_status=initial)])

    summary = service.update_review_status("org-1", "an-1", updated)

    assert summary.review_status == updated
    assert service.get_analysis("org-1", "an-1").review_status == updated


def test_update_review_status_invalid_value_raises_validation_error():
    service = build_service([record("an-1", "org-1")])

    with pytest.raises(ValidationError) as excinfo:
        service.update_review_status("org-1", "an-1", "invalid")  # type: ignore[arg-type]

    assert excinfo.value.status_code == 400
    assert service.get_analysis("org-1", "an-1").review_status == "pending"


def test_update_review_status_missing_raises_not_found():
    service = build_service([record("an-1", "org-1")])

    with pytest.raises(AnalysisNotFoundError) as excinfo:
        service.update_review_status("org-1", "missing", "confirmed")

    assert excinfo.value.status_code == 404


def test_update_review_status_cross_org_raises_not_found():
    service = build_service([record("an-1", "org-2")])

    with pytest.raises(AnalysisNotFoundError):
        service.update_review_status("org-1", "an-1", "confirmed")


def test_list_uses_scan_cap_when_loading_candidates():
    repository = FakeAnalysisRepository([record("an-1", "org-1")])
    service = HistoryService(
        repository=repository,
        object_store=FakeObjectStore(),
        list_scan_cap=123,
    )

    service.list_analyses("org-1")

    assert repository.last_list_limit == 123
