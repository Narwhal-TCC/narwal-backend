from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.analysis import AiAnalysis, AiDetectionNote, AnalysisResult, AnalysisSummary


def test_ai_analysis_ready_requires_fields_and_null_reason():
    generated = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    analysis = AiAnalysis(
        status="ready",
        reason=None,
        summary="Resumo curto.",
        detections=[AiDetectionNote(index=0, note="Nota.")],
        recommendation="Verificar.",
        caveats=["Limitação."],
        model="openai/gpt-oss-120b",
        generated_at=generated,
    )
    assert analysis.status == "ready"
    assert analysis.reason is None
    assert analysis.summary == "Resumo curto."
    assert analysis.detections[0].index == 0
    assert analysis.model == "openai/gpt-oss-120b"
    assert analysis.generated_at == generated


def test_ai_analysis_unavailable_accepts_known_reasons():
    for reason in (
        "disabled",
        "timeout",
        "provider_error",
        "rate_limited",
        "invalid_response",
    ):
        analysis = AiAnalysis(status="unavailable", reason=reason)
        assert analysis.reason == reason


def test_ai_analysis_rejects_invalid_status():
    with pytest.raises(ValidationError):
        AiAnalysis(status="pending", reason="disabled")  # type: ignore[arg-type]


def test_ai_analysis_rejects_invalid_reason():
    with pytest.raises(ValidationError):
        AiAnalysis(status="unavailable", reason="unknown")  # type: ignore[arg-type]


def test_analysis_result_includes_optional_ai_analysis():
    generated = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    ai = AiAnalysis(
        status="ready",
        summary="Ok",
        recommendation="Ok",
        model="m",
        generated_at=generated,
    )
    result = AnalysisResult(
        id="01JABCDEF",
        org_id="org-1",
        user_id="user-1",
        status="succeeded",
        detections=[],
        image_content_type="image/png",
        image_s3_key="k",
        created_at=generated,
        ai_analysis=ai,
    )
    assert result.ai_analysis is ai


def test_analysis_summary_has_no_ai_analysis_field():
    assert "ai_analysis" not in AnalysisSummary.model_fields
    AnalysisSummary(
        id="01JABCDEF",
        org_id="org-1",
        user_id="user-1",
        status="succeeded",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        detection_count=0,
    )
