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
        "label_stats",
    }
)
DETECTION_PAYLOAD_KEYS = frozenset(
    {
        "index",
        "number",
        "x1",
        "y1",
        "x2",
        "y2",
        "region",
        "area_pct",
        "label",
        "confidence_pct",
    }
)

DISCLAIMER = "Esta análise é apoio à decisão e não substitui a avaliação do operador."

SYSTEM_PROMPT = (
    "Você é um assistente técnico de apoio à decisão para operadores de detecção "
    "de minas em imagens de sonar.\n"
    "Responda SOMENTE com um objeto JSON válido (sem markdown) no formato:\n"
    '{"summary": str, "detections": [{"index": int, "note": str}], '
    '"recommendation": str, "caveats": [str]}\n\n'
    "COMO A RESPOSTA É EXIBIDA (importante para evitar repetição):\n"
    "- A interface já mostra, acima de cada nota, o cabeçalho "
    "'Detecção {number} · {label} · {confidence_pct}% de confiança'.\n"
    "- O aviso de apoio à decisão é adicionado automaticamente ao summary; "
    "não o escreva.\n\n"
    "REGRAS DE NUMERAÇÃO:\n"
    "- Cada detecção de entrada traz `index` (técnico) e `number` (para humanos).\n"
    "- Em `detections[].index`, copie EXATAMENTE o `index` da detecção descrita.\n"
    "- Em qualquer texto, use apenas 'Detecção {number}', copiando o campo "
    "`number`. Nunca calcule números; nunca use `index` no texto.\n"
    "- Gere no máximo uma nota por detecção, na mesma ordem da entrada.\n\n"
    "REGRAS DE CONTEÚDO:\n"
    "1. Português do Brasil, tom factual e direto. Use apenas dados da entrada.\n"
    "2. `summary`: no máximo 2 frases. Visão geral (totais por rótulo em "
    "`label_stats`, faixa de confiança). NÃO liste detecções individualmente.\n"
    "3. `detections[].note`: NÃO repita número, rótulo nem confiança (já estão "
    "no cabeçalho). Acrescente só informação nova: posição (`region`), tamanho "
    "relativo (`area_pct`), comparação com as demais (ex: 'a menor confiança "
    "entre as MILCO') e o que o operador deve observar. Máximo 1 frase.\n"
    "4. `recommendation`: priorize ações concretas. Para afirmações como "
    "'maior/menor confiança', use SOMENTE os valores de `label_stats` "
    "(`lowest_number`, `highest_number`), nunca deduza.\n"
    "5. `caveats`: no máximo 3, específicos para esta imagem (ex: detecções "
    "abaixo de 80%, detecções muito pequenas ou próximas da borda). NÃO "
    "repita o aviso de apoio à decisão nem frases já usadas em outros campos.\n"
    "6. Nenhuma frase deve aparecer, com o mesmo sentido, em dois campos.\n"
)


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


def _region(det: Detection, width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "desconhecida"
    cx = (det.x1 + det.x2) / 2 / width
    cy = (det.y1 + det.y2) / 2 / height
    vertical = "superior" if cy < 1 / 3 else "inferior" if cy > 2 / 3 else "central"
    horizontal = "esquerda" if cx < 1 / 3 else "direita" if cx > 2 / 3 else "centro"
    if vertical == "central" and horizontal == "centro":
        return "centro"
    return f"{vertical}-{horizontal}"


def _area_pct(det: Detection, width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    area = max(det.x2 - det.x1, 0) * max(det.y2 - det.y1, 0)
    return round(100 * area / (width * height), 2)


def _label_stats(detections: list[Detection]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for i, det in enumerate(detections):
        pct = round(det.confidence * 100)
        entry = stats.setdefault(
            det.label,
            {"count": 0, "numbers": [], "lowest_number": i + 1, "lowest_pct": pct,
             "highest_number": i + 1, "highest_pct": pct},
        )
        entry["count"] += 1
        entry["numbers"].append(i + 1)
        if pct < entry["lowest_pct"]:
            entry["lowest_number"], entry["lowest_pct"] = i + 1, pct
        if pct > entry["highest_pct"]:
            entry["highest_number"], entry["highest_pct"] = i + 1, pct
    return stats


def build_payload(context: AnalystContext) -> dict[str, Any]:
    entry = _registry_entry(context.model_id)
    model_label = entry.label if entry is not None else context.model_id
    model_description = entry.description if entry is not None else ""
    w, h = context.image_width, context.image_height
    detection_rows = [
        {
            "index": i,
            "number": i + 1,
            "x1": det.x1,
            "y1": det.y1,
            "x2": det.x2,
            "y2": det.y2,
            "region": _region(det, w, h),
            "area_pct": _area_pct(det, w, h),
            "label": det.label,
            "confidence_pct": round(det.confidence * 100),
        }
        for i, det in enumerate(context.detections)
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
        "label_stats": _label_stats(context.detections),
    }
    assert set(payload.keys()) == PAYLOAD_TOP_LEVEL_KEYS
    for row in detection_rows:
        assert set(row.keys()) == DETECTION_PAYLOAD_KEYS
    return payload


def postprocess(content: LlmAnalysisContent, *, detection_count: int) -> LlmAnalysisContent:
    kept_notes: list[AiDetectionNote] = []
    seen_indexes: set[int] = set()
    for note in content.detections:
        if note.index < 0 or note.index >= detection_count or note.index in seen_indexes:
            continue
        seen_indexes.add(note.index)
        kept_notes.append(
            AiDetectionNote(index=note.index, note=_truncate(note.note, NOTE_MAX_LEN))
        )
    kept_notes.sort(key=lambda n: n.index)
    disclaimer_key = DISCLAIMER.lower().rstrip(".")
    caveats = [
        _truncate(c, CAVEAT_MAX_LEN)
        for c in content.caveats
        if disclaimer_key not in c.lower()
    ][:MAX_CAVEATS]
    summary = content.summary.strip()
    if disclaimer_key not in summary.lower():
        summary = f"{summary} {DISCLAIMER}".strip()
    return LlmAnalysisContent(
        summary=_truncate(summary, SUMMARY_MAX_LEN),
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
