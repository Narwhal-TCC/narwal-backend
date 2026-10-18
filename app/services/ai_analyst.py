from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings, get_settings
from app.schemas.analysis import AiAnalysis, AiDetectionNote, Detection
from app.services.model_registry import REGISTRY

logger = logging.getLogger(__name__)

SUMMARY_MAX_LEN = 600
NOTE_MAX_LEN = 300
RECOMMENDATION_MAX_LEN = 400
CAVEAT_MAX_LEN = 200
MAX_CAVEATS = 5

PAYLOAD_TOP_LEVEL_KEYS = frozenset(
    {
        "model_id",
        "model_label",
        "model_description",
        "image_width",
        "image_height",
        "detections",
        "primary_class",
        "milco_detection_count",
    }
)
DETECTION_PAYLOAD_KEYS = frozenset(
    {"x1", "y1", "x2", "y2", "label", "confidence", "detector_score"}
)

SYSTEM_PROMPT = """Você é um assistente técnico para operadores de detecção de minas em imagens de sonar.
Responda SOMENTE com um objeto JSON válido (sem markdown) no formato:
{"summary": str, "detections": [{"index": int, "note": str}], "recommendation": str, "caveats": [str]}
Use português do Brasil, tom factual e objetivo. Não invente detecções que não estejam no JSON de entrada.
Mencione que a análise é apoio à decisão e não substitui a avaliação do operador.
Para cada item em detections, index é o índice 0-based da caixa correspondente na lista de detecções fornecida.
"""


class LlmAnalysisContent(BaseModel):
    summary: str
    detections: list[AiDetectionNote] = Field(default_factory=list)
    recommendation: str
    caveats: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AnalystContext:
    model_id: str
    image_width: int
    image_height: int
    detections: list[Detection]
    primary_class: str | None
    milco_detection_count: int


def _registry_entry(model_id: str):
    for entry in REGISTRY:
        if entry.id == model_id:
            return entry
    return None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def build_payload(context: AnalystContext) -> dict[str, Any]:
    entry = _registry_entry(context.model_id)
    model_label = entry.label if entry is not None else context.model_id
    model_description = entry.description if entry is not None else ""
    detection_rows = [
        {
            "x1": det.x1,
            "y1": det.y1,
            "x2": det.x2,
            "y2": det.y2,
            "label": det.label,
            "confidence": det.confidence,
            "detector_score": det.detector_score,
        }
        for det in context.detections
    ]
    payload = {
        "model_id": context.model_id,
        "model_label": model_label,
        "model_description": model_description,
        "image_width": context.image_width,
        "image_height": context.image_height,
        "detections": detection_rows,
        "primary_class": context.primary_class,
        "milco_detection_count": context.milco_detection_count,
    }
    assert set(payload.keys()) == PAYLOAD_TOP_LEVEL_KEYS
    for row in detection_rows:
        assert set(row.keys()) == DETECTION_PAYLOAD_KEYS
    return payload


def postprocess(content: LlmAnalysisContent, *, detection_count: int) -> LlmAnalysisContent:
    kept_notes: list[AiDetectionNote] = []
    for note in content.detections:
        if note.index < 0 or note.index >= detection_count:
            continue
        kept_notes.append(
            AiDetectionNote(index=note.index, note=_truncate(note.note, NOTE_MAX_LEN))
        )
    caveats = [_truncate(c, CAVEAT_MAX_LEN) for c in content.caveats[:MAX_CAVEATS]]
    return LlmAnalysisContent(
        summary=_truncate(content.summary, SUMMARY_MAX_LEN),
        detections=kept_notes,
        recommendation=_truncate(content.recommendation, RECOMMENDATION_MAX_LEN),
        caveats=caveats,
    )


def _unavailable(reason: str, *, model: str | None = None) -> AiAnalysis:
    return AiAnalysis(
        status="unavailable",
        reason=reason,  # type: ignore[arg-type]
        summary=None,
        detections=[],
        recommendation=None,
        caveats=[],
        model=model,
        generated_at=None,
    )


class AiAnalyst:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    def analyze(self, context: AnalystContext) -> AiAnalysis:
        settings = self._settings
        model_name = settings.llm_model
        if not (settings.llm_api_key or "").strip():
            result = _unavailable("disabled", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                0,
                model_name,
            )
            return result

        payload = build_payload(context)
        user_message = json.dumps(payload, ensure_ascii=False)
        request_body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    json=request_body,
                    headers=headers,
                    timeout=settings.llm_timeout_seconds,
                )
            else:
                with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                    response = client.post(url, json=request_body, headers=headers)
        except httpx.TimeoutException:
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = _unavailable("timeout", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                latency_ms,
                model_name,
            )
            return result
        except httpx.HTTPError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = _unavailable("provider_error", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                latency_ms,
                model_name,
            )
            return result

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            result = _unavailable("rate_limited", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                latency_ms,
                model_name,
            )
            return result
        if response.status_code < 200 or response.status_code >= 300:
            result = _unavailable("provider_error", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                latency_ms,
                model_name,
            )
            return result

        try:
            body = response.json()
            content_str = body["choices"][0]["message"]["content"]
            parsed = json.loads(content_str)
            llm_content = LlmAnalysisContent.model_validate(parsed)
        except (KeyError, TypeError, json.JSONDecodeError, ValidationError):
            result = _unavailable("invalid_response", model=model_name)
            logger.info(
                "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
                result.status,
                result.reason,
                latency_ms,
                model_name,
            )
            return result

        processed = postprocess(llm_content, detection_count=len(context.detections))
        generated_at = datetime.now(UTC)
        result = AiAnalysis(
            status="ready",
            reason=None,
            summary=processed.summary,
            detections=processed.detections,
            recommendation=processed.recommendation,
            caveats=processed.caveats,
            model=model_name,
            generated_at=generated_at,
        )
        logger.info(
            "ai_analysis status=%s reason=%s latency_ms=%s model=%s",
            result.status,
            result.reason,
            latency_ms,
            model_name,
        )
        return result
