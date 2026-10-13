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
        assert _table_names(conn) == {"orgs", "users", "analyses"}
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


def test_connect_on_valid_existing_file_applies_wal(tmp_path: Path):
    db_path = tmp_path / "existing.db"
    first = connect(db_path)
    first.close()

    second = connect(db_path)
    try:
        journal_mode = second.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert _table_names(second) == {"orgs", "users", "analyses"}
    finally:
        second.close()
