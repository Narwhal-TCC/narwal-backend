import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import StoreUnavailableError

_ORGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);
"""

_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id)
);
"""

_ANALYSES_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS analyses_org_created
  ON analyses (org_id, created_at);
"""


def _analyses_column_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(analyses)").fetchall()
    return {row[1] for row in rows}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_ORGS_SCHEMA + _USERS_SCHEMA + _ANALYSES_SCHEMA)
    if "model_id" not in _analyses_column_names(conn):
        conn.execute(
            """
            ALTER TABLE analyses
              ADD COLUMN model_id TEXT NOT NULL DEFAULT 'two-stage-pt'
            """
        )
    columns = _analyses_column_names(conn)
    if "ai_analysis_json" not in columns:
        conn.execute("ALTER TABLE analyses ADD COLUMN ai_analysis_json TEXT")
    if "ai_status" not in columns:
        conn.execute("ALTER TABLE analyses ADD COLUMN ai_status TEXT")
    if "ai_reason" not in columns:
        conn.execute("ALTER TABLE analyses ADD COLUMN ai_reason TEXT")


def _probe_existing_file(db_path: Path) -> None:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    probe: sqlite3.Connection | None = None
    try:
        probe = sqlite3.connect(uri, uri=True)
        probe.execute("SELECT 1 FROM sqlite_schema LIMIT 1")
    except sqlite3.DatabaseError as exc:
        raise StoreUnavailableError() from exc
    except sqlite3.OperationalError as exc:
        raise StoreUnavailableError() from exc
    finally:
        if probe is not None:
            probe.close()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    if path is None:
        db_path = Path(get_settings().sqlite_path)
    else:
        db_path = Path(path)

    if db_path.exists():
        _probe_existing_file(db_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
    except sqlite3.OperationalError as exc:
        raise StoreUnavailableError() from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        conn.commit()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
        conn.close()
        raise StoreUnavailableError() from exc
    return conn
