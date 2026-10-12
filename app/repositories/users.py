import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import StoreUnavailableError
from app.core.security import Role
from app.repositories.metadata_db import connect


class UserRepository:
    def __init__(self, path: str | None = None) -> None:
        self._path = path

    def _db_path(self) -> Path:
        if self._path is not None:
            return Path(self._path)
        return Path(get_settings().sqlite_path)

    def _with_connection(self):
        return connect(self._db_path())

    def put_org(self, org_id: str, name: str) -> None:
        conn = self._with_connection()
        try:
            conn.execute(
                "INSERT INTO orgs (org_id, name) VALUES (?, ?) "
                "ON CONFLICT(org_id) DO UPDATE SET name = excluded.name",
                (org_id, name),
            )
            conn.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            conn.rollback()
            raise StoreUnavailableError() from exc
        finally:
            conn.close()

    def get_org(self, org_id: str) -> dict | None:
        conn = self._with_connection()
        try:
            row = conn.execute(
                "SELECT org_id, name FROM orgs WHERE org_id = ?",
                (org_id,),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if row is None:
            return None
        return {"org_id": row["org_id"], "name": row["name"]}

    def put_user(
        self,
        user_id: str,
        org_id: str,
        username: str,
        password_hash: str,
        role: Role = "member",
    ) -> None:
        conn = self._with_connection()
        try:
            conn.execute(
                """
                INSERT INTO users (user_id, org_id, username, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(org_id, user_id) DO UPDATE SET
                  username = excluded.username,
                  password_hash = excluded.password_hash,
                  role = excluded.role
                """,
                (user_id, org_id, username, password_hash, role),
            )
            conn.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            conn.rollback()
            raise StoreUnavailableError() from exc
        finally:
            conn.close()

    def get_user(self, org_id: str, user_id: str) -> dict | None:
        conn = self._with_connection()
        try:
            row = conn.execute(
                """
                SELECT user_id, org_id, username, password_hash, role
                FROM users WHERE org_id = ? AND user_id = ?
                """,
                (org_id, user_id),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "org_id": row["org_id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
        }

    def get_by_username(self, username: str) -> dict | None:
        conn = self._with_connection()
        try:
            row = conn.execute(
                """
                SELECT user_id, org_id, username, password_hash, role
                FROM users WHERE username = ?
                """,
                (username,),
            ).fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise StoreUnavailableError() from exc
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "org_id": row["org_id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
        }
