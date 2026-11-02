import sqlite3
from pathlib import Path

import pytest

from app.core.errors import StoreUnavailableError
from app.repositories import metadata_db
from app.repositories.metadata_db import connect


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def test_connect_creates_parent_directory_and_schema(tmp_path: Path):
    db_path = tmp_path / "nested" / "narwal.db"
    assert not db_path.parent.exists()

    conn = connect(db_path)
    try:
        assert db_path.is_file()
        assert _table_names(conn) == {"orgs", "users", "campaigns", "analyses"}
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert foreign_keys == 1
    finally:
        conn.close()


def test_connect_probes_existing_file_before_opening_for_write(tmp_path: Path):
    db_path = tmp_path / "corrupt.db"
    garbage = b"NOT A SQLITE DATABASE FILE"
    db_path.write_bytes(garbage)
    probe_calls: list[bytes] = []
    real_probe = metadata_db._probe_existing_file

    def tracking_probe(path: Path) -> None:
        probe_calls.append(path.read_bytes())
        real_probe(path)

    metadata_db._probe_existing_file = tracking_probe  # type: ignore[method-assign]
    try:
        with pytest.raises(StoreUnavailableError):
            connect(db_path)
    finally:
        metadata_db._probe_existing_file = real_probe  # type: ignore[method-assign]

    assert probe_calls == [garbage]
    assert db_path.read_bytes() == garbage


def test_connect_on_garbage_file_raises_and_leaves_bytes_unchanged(tmp_path: Path):
    db_path = tmp_path / "corrupt.db"
    garbage = b"NOT A SQLITE DATABASE FILE"
    db_path.write_bytes(garbage)

    with pytest.raises(StoreUnavailableError):
        connect(db_path)

    assert db_path.read_bytes() == garbage


def _legacy_analyses_schema_without_model_id() -> str:
    return """
CREATE TABLE IF NOT EXISTS analyses (
  analysis_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  primary_class TEXT,
  campaign_name TEXT,
  coordinates TEXT,
  collected_at TEXT,
  milco_detection_count INTEGER NOT NULL DEFAULT 0,
  detections TEXT NOT NULL,
  image_s3_key TEXT NOT NULL,
  image_content_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  inference_ms INTEGER,
  PRIMARY KEY (org_id, analysis_id)
);
"""


def test_fresh_database_includes_model_id_without_alter(tmp_path: Path):
    db_path = tmp_path / "fresh-model-id.db"
    conn = connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
        assert "model_id" in columns
        default_row = conn.execute(
            "SELECT dflt_value FROM pragma_table_info('analyses') WHERE name = 'model_id'"
        ).fetchone()
        assert default_row[0] == "'two-stage-pt'"
    finally:
        conn.close()


def test_legacy_database_gains_model_id_default_on_existing_rows(tmp_path: Path):
    db_path = tmp_path / "legacy-model-id.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_legacy_analyses_schema_without_model_id())
    conn.execute(
        """
        INSERT INTO analyses (
          analysis_id, org_id, user_id, status, review_status,
          milco_detection_count, detections, image_s3_key,
          image_content_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "an-legacy",
            "org-1",
            "user-1",
            "succeeded",
            "pending",
            0,
            "[]",
            "analyses/org-1/an-legacy/original.png",
            "image/png",
            "2026-09-13T12:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    migrated = connect(db_path)
    try:
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(analyses)").fetchall()}
        assert "model_id" in columns
        model_id = migrated.execute(
            "SELECT model_id FROM analyses WHERE analysis_id = 'an-legacy'"
        ).fetchone()[0]
        assert model_id == "two-stage-pt"
    finally:
        migrated.close()


def test_fresh_database_has_campaigns_table_and_analysis_location_columns(tmp_path: Path):
    db_path = tmp_path / "fresh-campaign-map.db"
    conn = connect(db_path)
    try:
        assert "campaigns" in _table_names(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
        assert {"campaign_id", "latitude", "longitude", "location_source"} <= columns
        index_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index' AND name IS NOT NULL"
            ).fetchall()
        }
        assert "analyses_org_campaign" in index_names
    finally:
        conn.close()


def _legacy_analyses_schema_without_location_columns() -> str:
    return """
CREATE TABLE IF NOT EXISTS orgs (
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id)
);
CREATE TABLE IF NOT EXISTS analyses (
  analysis_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  primary_class TEXT,
  campaign_name TEXT,
  coordinates TEXT,
  collected_at TEXT,
  milco_detection_count INTEGER NOT NULL DEFAULT 0,
  detections TEXT NOT NULL,
  image_s3_key TEXT NOT NULL,
  image_content_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  inference_ms INTEGER,
  model_id TEXT NOT NULL DEFAULT 'two-stage-pt',
  PRIMARY KEY (org_id, analysis_id)
);
"""


def test_legacy_database_gains_location_columns_and_preserves_rows(tmp_path: Path):
    db_path = tmp_path / "legacy-location.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_legacy_analyses_schema_without_location_columns())
    conn.execute(
        """
        INSERT INTO analyses (
          analysis_id, org_id, user_id, status, review_status,
          campaign_name, milco_detection_count, detections, image_s3_key,
          image_content_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "an-legacy-loc",
            "org-1",
            "user-1",
            "succeeded",
            "pending",
            "Santos 2021",
            0,
            "[]",
            "analyses/org-1/an-legacy-loc/original.png",
            "image/png",
            "2026-09-13T12:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    migrated = connect(db_path)
    try:
        assert "campaigns" in _table_names(migrated)
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(analyses)").fetchall()}
        assert {"campaign_id", "latitude", "longitude", "location_source"} <= columns
        row = migrated.execute(
            """
            SELECT analysis_id, campaign_name, campaign_id, latitude, longitude, location_source
            FROM analyses WHERE analysis_id = 'an-legacy-loc'
            """
        ).fetchone()
        assert row["analysis_id"] == "an-legacy-loc"
        assert row["campaign_name"] == "Santos 2021"
        assert row["campaign_id"] is None
        assert row["latitude"] is None
        assert row["longitude"] is None
        assert row["location_source"] is None
    finally:
        migrated.close()


def test_connect_on_valid_existing_file_applies_wal(tmp_path: Path):
    db_path = tmp_path / "existing.db"
    first = connect(db_path)
    first.close()

    second = connect(db_path)
    try:
        journal_mode = second.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert _table_names(second) == {"orgs", "users", "campaigns", "analyses"}
    finally:
        second.close()
