from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_uses_sqlite_without_dynamodb():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "dynamodb:" not in compose
    assert "./db:/app/db" in compose
    assert "SQLITE_PATH=/app/db/narwal.db" in compose or "SQLITE_PATH: /app/db/narwal.db" in compose


def test_gitignore_ignores_db_directory():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "/db/" in gitignore


def test_readme_documents_sqlite_metadata_file():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "./db/narwal.db" in readme
    assert "DynamoDB Local" not in readme
    assert "DYNAMODB_ENDPOINT_URL" not in readme


def test_env_example_documents_sqlite_path():
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "SQLITE_PATH=db/narwal.db" in env_example
    assert "DYNAMODB_ENDPOINT_URL" not in env_example
    assert "DDB_TABLE" not in env_example


def test_pyproject_does_not_request_dynamodb_moto_extra():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "moto[s3,dynamodb]" not in pyproject
    assert "moto[s3]" in pyproject
