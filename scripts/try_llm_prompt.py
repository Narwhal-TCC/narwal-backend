"""Send the sample analyst payload to the configured LLM.

Reads SYSTEM_PROMPT from app.services.ai_analyst and credentials from .env.
Run from the narwal-backend directory:

    .\\.venv\\Scripts\\python scripts\\try_llm_prompt.py
"""

from __future__ import annotations

import json
import sys

import httpx

from app.core.config import get_settings
from app.services.ai_analyst import SYSTEM_PROMPT

PAYLOAD = {
    "model_id": "yolo-convnext-balanced",
    "model_label": "YOLO + ConvNeXt (equilibrado)",
    "model_description": (
        "Recomendado no dia a dia: equilibra achar minas e limitar falsos alarmes."
    ),
    "image_width": 640,
    "image_height": 480,
    "detections": [
        {
            "x1": 82.0,
            "y1": 140.0,
            "x2": 168.0,
            "y2": 226.0,
            "label": "MILCO",
            "confidence": 0.91,
            "detector_score": 0.74,
        },
        {
            "x1": 310.0,
            "y1": 188.0,
            "x2": 372.0,
            "y2": 251.0,
            "label": "NOMBO",
            "confidence": 0.63,
            "detector_score": 0.41,
        },
        {
            "x1": 90.0,
            "y1": 155.0,
            "x2": 160.0,
            "y2": 220.0,
            "label": "MILCO",
            "confidence": 0.67,
            "detector_score": 0.55,
        },
    ],
    "primary_class": "MILCO",
    "milco_detection_count": 2,
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    response = httpx.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(PAYLOAD, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
