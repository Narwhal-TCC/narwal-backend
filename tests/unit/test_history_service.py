import pytest

from app.core.errors import AnalysisNotFoundError
from app.services.history import HistoryService

DETECTIONS = [
    {"x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0, "confidence": 0.75, "label": "NOMBO"}
]


def record(analysis_id: str, org_id: str) -> dict:
    return {
        "id": analysis_id,
        "org_id": org_id,
        "user_id": "user-1",
        "status": "succeeded",
        "detections": DETECTIONS,
        "image_s3_key": f"analyses/{org_id}/{analysis_id}/original.png",
        "image_content_type": "image/png",
        "created_at": "2026-09-13T12:00:00+00:00",
        "inference_ms": 42,
    }


class FakeAnalysisRepository:
    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def list_by_org(self, org_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        scoped = [item for item in self.records if item["org_id"] == org_id]
        return scoped[offset : offset + limit]

    def get_analysis(self, org_id: str, analysis_id: str) -> dict | None:
        for item in self.records:
            if item["org_id"] == org_id and item["id"] == analysis_id:
                return item
        return None


class FakeObjectStore:
    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        return f"http://localhost:9000/narwal/{key}?X-Amz-Expires={expires_seconds}"


def build_service(records: list[dict]) -> HistoryService:
    return HistoryService(
        repository=FakeAnalysisRepository(records),
        object_store=FakeObjectStore(),
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
