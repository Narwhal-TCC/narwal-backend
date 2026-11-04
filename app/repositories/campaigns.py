import sqlite3
from pathlib import Path

from ulid import ULID

from app.core.config import get_settings
from app.core.errors import StoreUnavailableError
from app.repositories.metadata_db import connect


def new_campaign_id() -> str:
    return str(ULID())


def _to_record(row: sqlite3.Row) -> dict:
    keys = row.keys()
    record = {
        "campaign_id": row["campaign_id"],
        "org_id": row["org_id"],
        "name": row["name"],
        "min_lat": float(row["min_lat"]),
        "max_lat": float(row["max_lat"]),
        "min_lon": float(row["min_lon"]),
        "max_lon": float(row["max_lon"]),
        "simulated": bool(row["simulated"]),
        "created_at": row["created_at"],
    }
    if "analyses_count" in keys:
        record["analyses_count"] = int(row["analyses_count"])
    return record


class CampaignRepository:
    def __init__(self, path: str | None = None) -> None:
        self._path = path

    def _db_path(self) -> Path:
        if self._path is not None:
            return Path(self._path)
        return Path(get_settings().sqlite_path)

    def _with_connection(self):
        return connect(self._db_path())

    def put_campaign(
        self,
        *,
        campaign_id: str,
        org_id: str,
        name: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        simulated: bool,
        created_at: str,
    ) -> None:
        conn = self._with_connection()
        try:
            conn.execute(
                """
                INSERT INTO campaigns (
                  campaign_id, org_id, name,
                  min_lat, max_lat, min_lon, max_lon,
                  simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(org_id, campaign_id) DO UPDATE SET
                  name = excluded.name,
                  min_lat = excluded.min_lat,
                  max_lat = excluded.max_lat,
                  min_lon = excluded.min_lon,
                  max_lon = excluded.max_lon,
                  simulated = excluded.simulated,
                  created_at = excluded.created_at
                """,
                (
                    campaign_id,
                    org_id,
                    name,
                    min_lat,
                    max_lat,
                    min_lon,
                    max_lon,
                    1 if simulated else 0,
                    created_at,
                ),
            )
            conn.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            conn.rollback()
            raise StoreUnavailableError() from exc
        finally:
            conn.close()

    def get_campaign(self, org_id: str, campaign_id: str) -> dict | None:
        conn = self._with_connection()
        try:
            row = conn.execute(
                """
                SELECT c.campaign_id, c.org_id, c.name,
                       c.min_lat, c.max_lat, c.min_lon, c.max_lon,
                       c.simulated, c.created_at,
                       COUNT(a.analysis_id) AS analyses_count
                FROM campaigns c
                LEFT JOIN analyses a
                  ON a.org_id = c.org_id AND a.campaign_id = c.campaign_id
                WHERE c.org_id = ? AND c.campaign_id = ?
                GROUP BY c.campaign_id, c.org_id, c.name,
                         c.min_lat, c.max_lat, c.min_lon, c.max_lon,
                         c.simulated, c.created_at
                """,
                (org_id, campaign_id),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if row is None:
            return None
        return _to_record(row)

    def get_by_name(self, org_id: str, name: str) -> dict | None:
        conn = self._with_connection()
        try:
            row = conn.execute(
                """
                SELECT campaign_id, org_id, name,
                       min_lat, max_lat, min_lon, max_lon,
                       simulated, created_at
                FROM campaigns
                WHERE org_id = ? AND name = ?
                """,
                (org_id, name),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if row is None:
            return None
        return _to_record(row)

    def list_by_org(self, org_id: str) -> list[dict]:
        conn = self._with_connection()
        try:
            rows = conn.execute(
                """
                SELECT c.campaign_id, c.org_id, c.name,
                       c.min_lat, c.max_lat, c.min_lon, c.max_lon,
                       c.simulated, c.created_at,
                       COUNT(a.analysis_id) AS analyses_count
                FROM campaigns c
                LEFT JOIN analyses a
                  ON a.org_id = c.org_id AND a.campaign_id = c.campaign_id
                WHERE c.org_id = ?
                GROUP BY c.campaign_id, c.org_id, c.name,
                         c.min_lat, c.max_lat, c.min_lon, c.max_lon,
                         c.simulated, c.created_at
                ORDER BY c.created_at DESC, c.campaign_id DESC
                """,
                (org_id,),
            ).fetchall()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        return [_to_record(row) for row in rows]
