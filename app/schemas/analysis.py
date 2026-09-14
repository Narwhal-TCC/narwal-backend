from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Detection(BaseModel):
    """Axis-aligned box in uploaded-image pixels: half-open ``[x1, x2)`` × ``[y1, y2)``."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = Field(ge=0.0, le=1.0)
    label: str = "mine"


class AnalysisResult(BaseModel):
    id: str
    org_id: str
    user_id: str
    status: Literal["succeeded"]
    detections: list[Detection]
    image_content_type: str
    image_s3_key: str
    image_url: str | None = None
    created_at: datetime
    inference_ms: int | None = None


class AnalysisSummary(BaseModel):
    id: str
    org_id: str
    user_id: str
    status: Literal["succeeded"]
    created_at: datetime
    inference_ms: int | None = None
    detection_count: int


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    limit: int
    offset: int
