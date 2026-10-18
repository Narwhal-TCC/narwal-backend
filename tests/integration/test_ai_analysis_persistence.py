import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.repositories.analyses import AnalysisRepository, _to_record
from app.repositories.metadata_db import connect
from app.schemas.analysis import AiAnalysis, AiDetectionNote
from app.services.history import HistoryService

DETECTIONS = [
    {
        "x1": 1.0,
        "y1": 2.0,
        "x2": 3.0,
        "y2": 4.0,
        "confidence": 0.9,
        "label": "MILCO",
        "detector_score": 0.8,
    }
]


def _ready_ai() -> AiAnalysis:
    return AiAnalysis(
        status="ready",
        reason=None,
        summary="Resumo persistido.",
        detections=[AiDetectionNote(index=0, note="Nota.")],
        recommendation="Recomendação.",
        caveats=["Limite."],
        model="openai/gpt-oss-120b",
        generated_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
    )


def _unavailable_ai(reason: str = "timeout") -> AiAnalysis:
    return AiAnalysis(status="unavailable", reason=reason)  # type: ignore[arg-type]


@pytest.fixture
def repository(tmp_path: Path):
    db_path = tmp_path / "ai-analysis.db"
    return AnalysisRepository(str(db_path)), db_path


def test_put_get_round_trips_ready_ai_analysis(repository):
    repo, _ = repository
    ai = _ready_ai()
    repo.put_analysis(
        analysis_id="an-ready",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-ready/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
        ai_analysis=ai,
    )

    record = repo.get_analysis("org-1", "an-ready")
    assert record is not None
    stored = record["ai_analysis"]
    assert stored.status == "ready"
    assert stored.reason is None
    assert stored.summary == "Resumo persistido."
    assert stored.detections[0].note == "Nota."
    assert stored.model == "openai/gpt-oss-120b"
    assert stored.generated_at == ai.generated_at


def test_put_get_round_trips_unavailable_ai_analysis(repository):
    repo, _ = repository
    ai = _unavailable_ai("rate_limited")
    repo.put_analysis(
        analysis_id="an-unavail",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-unavail/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
        ai_analysis=ai,
    )

    record = repo.get_analysis("org-1", "an-unavail")
    assert record is not None
    stored = record["ai_analysis"]
    assert stored.status == "unavailable"
    assert stored.reason == "rate_limited"
    assert stored.summary is None


def _legacy_analyses_schema_without_ai() -> str:
    return """
CREATE TABLE IF NOT EXISTS analyses (
  analysis_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  primary_class TEXT,
  campaign_name TEXT,
  coordinates TEXT,
  collected_at TEXT,
  milco_detection_count INTEGER NOT NULL DEFAULT 0,
  detections TEXT NOT NULL,
  image_s3_key TEXT NOT NULL,
  image_content_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  inference_ms INTEGER,
  model_id TEXT NOT NULL DEFAULT 'two-stage-pt',
  PRIMARY KEY (org_id, analysis_id)
);
"""


def test_legacy_database_gains_ai_columns_on_connect(tmp_path: Path):
    db_path = tmp_path / "legacy-ai.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_legacy_analyses_schema_without_ai())
    conn.execute(
        """
        INSERT INTO analyses (
          analysis_id, org_id, user_id, status, review_status,
          milco_detection_count, detections, image_s3_key,
          image_content_type, created_at, model_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "an-legacy",
            "org-1",
            "user-1",
            "succeeded",
            "pending",
            0,
            "[]",
            "analyses/org-1/an-legacy/original.png",
            "image/png",
            "2026-09-13T12:00:00+00:00",
            "two-stage-pt",
        ),
    )
    conn.commit()
    conn.close()

    migrated = connect(db_path)
    try:
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(analyses)").fetchall()}
        assert {"ai_analysis_json", "ai_status", "ai_reason"}.issubset(columns)
    finally:
        migrated.close()

    repo = AnalysisRepository(str(db_path))
    record = repo.get_analysis("org-1", "an-legacy")
    assert record is not None
    assert record["ai_analysis"].status == "unavailable"
    assert record["ai_analysis"].reason == "disabled"


def test_history_maps_legacy_row_to_disabled_ai(repository):
    repo, _ = repository
    repo.put_analysis(
        analysis_id="an-old",
        org_id="org-1",
        user_id="user-1",
        detections=DETECTIONS,
        image_s3_key="analyses/org-1/an-old/original.png",
        image_content_type="image/png",
        created_at="2026-09-13T12:00:00+00:00",
    )

    class _Store:
        def presign_get(self, key: str, expires_seconds: int = 900) -> str:
            return f"https://example.test/{key}"

    service = HistoryService(repository=repo, object_store=_Store())
    result = service.get_analysis("org-1", "an-old")
    assert result.ai_analysis is not None
    assert result.ai_analysis.status == "unavailable"
    assert result.ai_analysis.reason == "disabled"
