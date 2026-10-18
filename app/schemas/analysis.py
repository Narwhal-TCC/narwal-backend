from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DetectionLabel = Literal["MILCO", "NOMBO"]
PrimaryClass = Literal["MILCO", "NOMBO"]
ReviewStatus = Literal["pending", "confirmed", "false_positive"]
AiStatus = Literal["ready", "unavailable"]
AiReason = Literal[
    "disabled",
    "timeout",
    "provider_error",
    "rate_limited",
    "invalid_response",
]


class AiDetectionNote(BaseModel):
    index: int
    note: str


class AiAnalysis(BaseModel):
    status: AiStatus
    reason: AiReason | None = None
    summary: str | None = None
    detections: list[AiDetectionNote] = Field(default_factory=list)
    recommendation: str | None = None
    caveats: list[str] = Field(default_factory=list)
    model: str | None = None
    generated_at: datetime | None = None


class Detection(BaseModel):
    """Axis-aligned box in uploaded-image pixels: half-open ``[x1, x2)`` × ``[y1, y2)``."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = Field(ge=0.0, le=1.0)
    label: DetectionLabel
    detector_score: float = Field(ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    id: str
    org_id: str
    user_id: str
    status: Literal["succeeded"]
    review_status: ReviewStatus = "pending"
    primary_class: PrimaryClass | None = None
    campaign_name: str | None = Field(default=None, max_length=256)
    coordinates: str | None = Field(default=None, max_length=256)
    collected_at: datetime | None = None
    milco_detection_count: int = 0
    detections: list[Detection]
    image_content_type: str
    image_s3_key: str
    image_url: str | None = None
    created_at: datetime
    inference_ms: int | None = None
    model_id: str = "two-stage-pt"
    ai_analysis: AiAnalysis | None = None


class AnalysisSummary(BaseModel):
    id: str
    org_id: str
    user_id: str
    status: Literal["succeeded"]
    review_status: ReviewStatus = "pending"
    primary_class: PrimaryClass | None = None
    campaign_name: str | None = Field(default=None, max_length=256)
    coordinates: str | None = Field(default=None, max_length=256)
    collected_at: datetime | None = None
    milco_detection_count: int = 0
    created_at: datetime
    inference_ms: int | None = None
    detection_count: int
    model_id: str = "two-stage-pt"


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    limit: int
    offset: int


class ReviewStatusUpdate(BaseModel):
    review_status: str


class OrgStatsResponse(BaseModel):
    analyses_count: int
    milco_detections_count: int
    last_analysis: AnalysisSummary | None
    active_campaign: str | None
