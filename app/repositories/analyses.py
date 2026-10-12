import json
import sqlite3
from pathlib import Path

from ulid import ULID

from app.core.config import get_settings
from app.core.errors import StoreUnavailableError
from app.repositories.metadata_db import connect

DEFAULT_LIST_LIMIT = 50


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
    ) -> dict:
        conn = self._with_connection()
        try:
            conn.execute(
                """
                INSERT INTO analyses (
                  analysis_id, org_id, user_id, status, review_status,
                  primary_class, campaign_name, coordinates, collected_at,
                  milco_detection_count, detections, image_s3_key,
                  image_content_type, created_at, inference_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                """
                SELECT analysis_id, org_id, user_id, status, review_status,
                       primary_class, campaign_name, coordinates, collected_at,
                       milco_detection_count, detections, image_s3_key,
                       image_content_type, created_at, inference_ms
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
                """
                SELECT analysis_id, org_id, user_id, status, review_status,
                       primary_class, campaign_name, coordinates, collected_at,
                       milco_detection_count, detections, image_s3_key,
                       image_content_type, created_at, inference_ms
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
