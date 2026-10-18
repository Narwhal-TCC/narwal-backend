import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.schemas.analysis import AiDetectionNote, Detection
from app.services.ai_analyst import (
    CAVEAT_MAX_LEN,
    DETECTION_PAYLOAD_KEYS,
    NOTE_MAX_LEN,
    PAYLOAD_TOP_LEVEL_KEYS,
    RECOMMENDATION_MAX_LEN,
    SUMMARY_MAX_LEN,
    SYSTEM_PROMPT,
    AiAnalyst,
    AnalystContext,
    LlmAnalysisContent,
    build_payload,
    postprocess,
)


def _detection(**overrides) -> Detection:
    base = {
        "x1": 1.0,
        "y1": 2.0,
        "x2": 3.0,
        "y2": 4.0,
        "confidence": 0.9,
        "label": "MILCO",
        "detector_score": 0.8,
    }
    base.update(overrides)
    return Detection(**base)


def _context(**overrides) -> AnalystContext:
    defaults = {
        "model_id": "yolo-convnext-balanced",
        "image_width": 640,
        "image_height": 480,
        "detections": [_detection()],
        "primary_class": "MILCO",
        "milco_detection_count": 1,
    }
    defaults.update(overrides)
    return AnalystContext(**defaults)


def test_build_payload_keys_match_whitelist_and_omit_sensitive_fields():
    payload = build_payload(_context())
    assert set(payload.keys()) == PAYLOAD_TOP_LEVEL_KEYS
    assert payload["model_id"] == "yolo-convnext-balanced"
    assert payload["model_label"] == "YOLO + ConvNeXt (equilibrado)"
    assert "model_description" in payload
    assert payload["image_width"] == 640
    assert payload["image_height"] == 480
    assert payload["primary_class"] == "MILCO"
    assert payload["milco_detection_count"] == 1
    forbidden = {
        "org_id",
        "user_id",
        "campaign_name",
        "coordinates",
        "image_bytes",
        "filename",
    }
    assert forbidden.isdisjoint(payload.keys())
    serialized = json.dumps(payload)
    assert "org_id" not in serialized
    assert "user_id" not in serialized
    assert "campaign_name" not in serialized
    assert "coordinates" not in serialized
    row = payload["detections"][0]
    assert set(row.keys()) == DETECTION_PAYLOAD_KEYS


def test_build_payload_zero_detections_is_valid():
    payload = build_payload(
        _context(detections=[], primary_class=None, milco_detection_count=0)
    )
    assert payload["detections"] == []
    assert payload["milco_detection_count"] == 0


def test_postprocess_truncates_summary_at_600_chars():
    content = LlmAnalysisContent(
        summary="a" * 601,
        recommendation="r",
        caveats=[],
    )
    processed = postprocess(content, detection_count=1)
    assert len(processed.summary) == SUMMARY_MAX_LEN
    assert processed.summary == "a" * 600


def test_postprocess_truncates_at_boundary_600_keeps_length():
    content = LlmAnalysisContent(
        summary="b" * 600,
        recommendation="r",
        caveats=[],
    )
    processed = postprocess(content, detection_count=1)
    assert len(processed.summary) == 600


def test_postprocess_drops_out_of_range_detection_notes():
    content = LlmAnalysisContent(
        summary="s",
        recommendation="r",
        detections=[
            AiDetectionNote(index=-1, note="bad low"),
            AiDetectionNote(index=0, note="ok"),
            AiDetectionNote(index=1, note="bad high"),
        ],
        caveats=[],
    )
    processed = postprocess(content, detection_count=1)
    assert [n.index for n in processed.detections] == [0]
    assert processed.detections[0].note == "ok"


def test_postprocess_caps_caveats_and_truncates_note():
    content = LlmAnalysisContent(
        summary="s",
        recommendation="r",
        detections=[AiDetectionNote(index=0, note="n" * (NOTE_MAX_LEN + 5))],
        caveats=["c" * (CAVEAT_MAX_LEN + 1) for _ in range(7)],
    )
    processed = postprocess(content, detection_count=1)
    assert len(processed.caveats) == 5
    assert len(processed.caveats[0]) == CAVEAT_MAX_LEN
    assert len(processed.detections[0].note) == NOTE_MAX_LEN
    assert len(processed.recommendation) <= RECOMMENDATION_MAX_LEN


def _llm_settings(**overrides) -> Settings:
    base = {
        "llm_base_url": "http://llm.test/v1",
        "llm_model": "openai/gpt-oss-120b",
        "llm_api_key": "test-key",
        "llm_timeout_seconds": 10.0,
    }
    base.update(overrides)
    return Settings(**base, _env_file=None)


def _ready_llm_json() -> dict:
    return {
        "summary": "Resumo.",
        "detections": [{"index": 0, "note": "Nota."}],
        "recommendation": "Recomendar.",
        "caveats": ["Cuidado."],
    }


def _transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_analyze_ready_parses_valid_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_ready_llm_json())}}
                ]
            },
        )

    analyst = AiAnalyst(
        settings=_llm_settings(),
        client=_transport(handler),
    )
    result = analyst.analyze(_context())
    assert result.status == "ready"
    assert result.reason is None
    assert result.summary == "Resumo."
    assert result.detections[0].note == "Nota."
    assert result.model == "openai/gpt-oss-120b"
    assert result.generated_at is not None
    assert captured["url"] == "http://llm.test/v1/chat/completions"
    assert captured["body"]["model"] == "openai/gpt-oss-120b"


def test_analyze_disabled_when_api_key_empty_makes_no_http_call():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    analyst = AiAnalyst(
        settings=_llm_settings(llm_api_key=""),
        client=_transport(handler),
    )
    result = analyst.analyze(_context())
    assert result.status == "unavailable"
    assert result.reason == "disabled"
    assert called is False


@pytest.mark.parametrize(
    ("status_code", "expected_reason"),
    [
        (429, "rate_limited"),
        (500, "provider_error"),
    ],
)
def test_analyze_maps_http_errors(status_code, expected_reason):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "x"})

    analyst = AiAnalyst(settings=_llm_settings(), client=_transport(handler))
    result = analyst.analyze(_context())
    assert result.status == "unavailable"
    assert result.reason == expected_reason


def test_analyze_timeout_maps_to_timeout_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    analyst = AiAnalyst(settings=_llm_settings(), client=_transport(handler))
    result = analyst.analyze(_context())
    assert result.reason == "timeout"


def test_analyze_invalid_json_maps_to_invalid_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    analyst = AiAnalyst(settings=_llm_settings(), client=_transport(handler))
    result = analyst.analyze(_context())
    assert result.reason == "invalid_response"


def test_analyze_logs_exclude_api_key_and_prompt(caplog):
    secret = "super-secret-llm-key"
    prompt_marker = "whitelist-marker-xyz"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(_ready_llm_json()),
                        }
                    }
                ]
            },
        )

    caplog.set_level(logging.INFO)
    analyst = AiAnalyst(
        settings=_llm_settings(llm_api_key=secret),
        client=_transport(handler),
    )
    import app.services.ai_analyst as ai_mod

    original_prompt = ai_mod.SYSTEM_PROMPT
    ai_mod.SYSTEM_PROMPT = prompt_marker
    try:
        analyst.analyze(_context())
    finally:
        ai_mod.SYSTEM_PROMPT = original_prompt

    log_text = caplog.text
    assert secret not in log_text
    assert prompt_marker not in log_text
    assert "ai_analysis status=ready" in log_text
