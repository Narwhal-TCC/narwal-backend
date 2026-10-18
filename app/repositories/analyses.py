import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ulid import ULID

from app.core.config import get_settings
from app.core.errors import StoreUnavailableError
from app.repositories.metadata_db import connect
from app.schemas.analysis import AiAnalysis, AiDetectionNote
from app.services.model_registry import DEFAULT_MODEL_ID, LEGACY_DEFAULT_MODEL_ID

DEFAULT_LIST_LIMIT = 50

_ANALYSIS_COLUMNS = """
    analysis_id, org_id, user_id, status, review_status,
    primary_class, campaign_name, coordinates, collected_at,
    milco_detection_count, detections, image_s3_key,
    image_content_type, created_at, inference_ms, model_id,
    ai_analysis_json, ai_status, ai_reason
"""


def _empty_unavailable_disabled() -> AiAnalysis:
    return AiAnalysis(status="unavailable", reason="disabled")


def _serialize_ai_analysis(ai: AiAnalysis | None) -> tuple[str | None, str | None, str | None]:
    if ai is None:
        return None, None, None
    if ai.status == "ready":
        payload = {
            "summary": ai.summary,
            "detections": [note.model_dump() for note in ai.detections],
            "recommendation": ai.recommendation,
            "caveats": ai.caveats,
            "model": ai.model,
            "generated_at": ai.generated_at.isoformat() if ai.generated_at else None,
        }
        return json.dumps(payload, ensure_ascii=False), ai.status, ai.reason
    return None, ai.status, ai.reason


def load_ai_analysis_from_row(row: sqlite3.Row) -> AiAnalysis:
    keys = row.keys()
    ai_status = row["ai_status"] if "ai_status" in keys else None
    if ai_status is None:
        return _empty_unavailable_disabled()
    if ai_status == "unavailable":
        reason = row["ai_reason"] if "ai_reason" in keys else None
        return AiAnalysis(
            status="unavailable",
            reason=reason,  # type: ignore[arg-type]
            summary=None,
            detections=[],
            recommendation=None,
            caveats=[],
            model=None,
            generated_at=None,
        )
    raw_json = row["ai_analysis_json"] if "ai_analysis_json" in keys else None
    if not raw_json:
        return AiAnalysis(
            status="unavailable",
            reason="invalid_response",
            summary=None,
            detections=[],
            recommendation=None,
            caveats=[],
            model=None,
            generated_at=None,
        )
    payload = json.loads(raw_json)
    generated_raw = payload.get("generated_at")
    generated_at = datetime.fromisoformat(generated_raw) if generated_raw else None
    notes = [
        AiDetectionNote.model_validate(item) for item in payload.get("detections") or []
    ]
    return AiAnalysis(
        status="ready",
        reason=None,
        summary=payload.get("summary"),
        detections=notes,
        recommendation=payload.get("recommendation"),
        caveats=list(payload.get("caveats") or []),
        model=payload.get("model"),
        generated_at=generated_at,
    )


def new_analysis_id() -> str:
    return str(ULID())


def _to_record(row: sqlite3.Row) -> dict:
    detections = json.loads(row["detections"])
    inference_ms = row["inference_ms"]
    return {
        "id": row["analysis_id"],
        "org_id": row["org_id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "review_status": row["review_status"],
        "primary_class": row["primary_class"],
        "campaign_name": row["campaign_name"],
        "coordinates": row["coordinates"],
        "collected_at": row["collected_at"],
        "milco_detection_count": int(row["milco_detection_count"]),
        "detections": detections,
        "image_s3_key": row["image_s3_key"],
        "image_content_type": row["image_content_type"],
        "created_at": row["created_at"],
        "inference_ms": int(inference_ms) if inference_ms is not None else None,
        "model_id": row["model_id"] or LEGACY_DEFAULT_MODEL_ID,
        "ai_analysis": load_ai_analysis_from_row(row),
    }


class AnalysisRepository:
    def __init__(self, path: str | None = None) -> None:
        self._path = path

    def _db_path(self) -> Path:
        if self._path is not None:
            return Path(self._path)
        return Path(get_settings().sqlite_path)

    def _with_connection(self):
        return connect(self._db_path())

    def put_analysis(
        self,
        analysis_id: str,
        org_id: str,
        user_id: str,
        detections: list[dict],
        image_s3_key: str,
        image_content_type: str,
        created_at: str,
        inference_ms: int | None = None,
        status: str = "succeeded",
        review_status: str = "pending",
        primary_class: str | None = None,
        campaign_name: str | None = None,
        coordinates: str | None = None,
        collected_at: str | None = None,
        milco_detection_count: int = 0,
        model_id: str = DEFAULT_MODEL_ID,
        ai_analysis: AiAnalysis | None = None,
    ) -> dict:
        ai_json, ai_status, ai_reason = _serialize_ai_analysis(ai_analysis)
        conn = self._with_connection()
        try:
            conn.execute(
                """
                INSERT INTO analyses (
                  analysis_id, org_id, user_id, status, review_status,
                  primary_class, campaign_name, coordinates, collected_at,
                  milco_detection_count, detections, image_s3_key,
                  image_content_type, created_at, inference_ms, model_id,
                  ai_analysis_json, ai_status, ai_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    org_id,
                    user_id,
                    status,
                    review_status,
                    primary_class,
                    campaign_name,
                    coordinates,
                    collected_at,
                    milco_detection_count,
                    json.dumps(detections),
                    image_s3_key,
                    image_content_type,
                    created_at,
                    inference_ms,
                    model_id,
                    ai_json,
                    ai_status,
                    ai_reason,
                ),
            )
            conn.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            conn.rollback()
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        row = self._fetch_row(org_id, analysis_id)
        assert row is not None
        return _to_record(row)

    def update_review_status(
        self,
        org_id: str,
        analysis_id: str,
        review_status: str,
    ) -> dict | None:
        conn = self._with_connection()
        rowcount = 0
        try:
            cursor = conn.execute(
                """
                UPDATE analyses SET review_status = ?
                WHERE org_id = ? AND analysis_id = ?
                """,
                (review_status, org_id, analysis_id),
            )
            rowcount = cursor.rowcount
            conn.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            conn.rollback()
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if rowcount == 0:
            return None
        row = self._fetch_row(org_id, analysis_id)
        return _to_record(row) if row else None

    def _fetch_row(self, org_id: str, analysis_id: str) -> sqlite3.Row | None:
        conn = self._with_connection()
        try:
            return conn.execute(
                f"""
                SELECT {_ANALYSIS_COLUMNS}
                FROM analyses WHERE org_id = ? AND analysis_id = ?
                """,
                (org_id, analysis_id),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()

    def get_analysis(self, org_id: str, analysis_id: str) -> dict | None:
        row = self._fetch_row(org_id, analysis_id)
        return _to_record(row) if row else None

    def list_by_org(
        self,
        org_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[dict]:
        conn = self._with_connection()
        try:
            rows = conn.execute(
                f"""
                SELECT {_ANALYSIS_COLUMNS}
                FROM analyses
                WHERE org_id = ?
                ORDER BY created_at DESC, analysis_id DESC
                LIMIT ? OFFSET ?
                """,
                (org_id, limit, offset),
            ).fetchall()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        return [_to_record(row) for row in rows]
