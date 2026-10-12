from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_uses_sqlite_without_dynamodb():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "dynamodb:" not in compose
    assert "./db:/app/db" in compose
    assert "SQLITE_PATH=/app/db/narwal.db" in compose or "SQLITE_PATH: /app/db/narwal.db" in compose
