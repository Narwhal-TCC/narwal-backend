import json

from app.schemas.analysis import AiDetectionNote, Detection
from app.services.ai_analyst import (
    CAVEAT_MAX_LEN,
    DETECTION_PAYLOAD_KEYS,
    NOTE_MAX_LEN,
    PAYLOAD_TOP_LEVEL_KEYS,
    RECOMMENDATION_MAX_LEN,
    SUMMARY_MAX_LEN,
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
