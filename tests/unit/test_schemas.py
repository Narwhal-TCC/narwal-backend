from datetime import UTC, datetime

from app.schemas.analysis import AnalysisResult, AnalysisSummary, Detection
from app.schemas.auth import LoginRequest, TokenResponse


def test_analysis_result_accepts_empty_detections():
    result = AnalysisResult(
        id="01JABCDEF",
        org_id="org-demo",
        user_id="user-1",
        status="succeeded",
        detections=[],
        image_content_type="image/png",
        image_s3_key="analyses/org-demo/01JABCDEF/original.png",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        inference_ms=42,
        model_id="two-stage-pt",
    )
    assert result.detections == []
    assert result.model_id == "two-stage-pt"


def test_analysis_summary_includes_model_id():
    summary = AnalysisSummary(
        id="01JABCDEF",
        org_id="org-demo",
        user_id="user-1",
        status="succeeded",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        detection_count=0,
        model_id="two-stage-pt",
    )
    assert summary.model_id == "two-stage-pt"


def test_detection_accepts_milco_and_nombo_labels():
    milco = Detection(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, label="MILCO", detector_score=0.8
    )
    nombo = Detection(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, label="NOMBO", detector_score=0.7
    )
    assert milco.label == "MILCO"
    assert milco.detector_score == 0.8
    assert nombo.label == "NOMBO"
    assert nombo.detector_score == 0.7


def test_detection_requires_detector_score_in_unit_interval():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Detection(x1=0, y1=0, x2=10, y2=10, confidence=0.9, label="MILCO", detector_score=1.5)
    with pytest.raises(ValidationError):
        Detection(x1=0, y1=0, x2=10, y2=10, confidence=0.9, label="MILCO")


def test_login_and_token_schemas_round_trip():
    login = LoginRequest(username="alice", password="secret")
    token = TokenResponse(access_token="jwt-token")
    assert login.username == "alice"
    assert token.token_type == "bearer"
