from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.analysis import AiDetectionNote, Detection
from app.services.model_registry import REGISTRY

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
