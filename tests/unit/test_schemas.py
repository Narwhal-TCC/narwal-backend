from datetime import UTC, datetime

from app.schemas.analysis import AnalysisResult, Detection
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
    )
    assert result.detections == []


def test_detection_defaults_label_to_mine():
    detection = Detection(x1=0, y1=0, x2=10, y2=10, confidence=0.9)
    assert detection.label == "mine"


def test_login_and_token_schemas_round_trip():
    login = LoginRequest(username="alice", password="secret")
    token = TokenResponse(access_token="jwt-token")
    assert login.username == "alice"
    assert token.token_type == "bearer"
