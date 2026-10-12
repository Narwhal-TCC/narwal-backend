import sqlite3
from pathlib import Path

import pytest

from app.core.errors import StoreUnavailableError
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


def test_connect_on_garbage_file_raises_and_leaves_bytes_unchanged(tmp_path: Path):
    db_path = tmp_path / "corrupt.db"
    garbage = b"NOT A SQLITE DATABASE FILE"
    db_path.write_bytes(garbage)

    with pytest.raises(StoreUnavailableError):
        connect(db_path)

    assert db_path.read_bytes() == garbage


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
