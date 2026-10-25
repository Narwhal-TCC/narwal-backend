import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "aws"

BOOTSTRAP = SCRIPTS_DIR / "ec2-api-bootstrap.sh"
SMOKE = SCRIPTS_DIR / "smoke_app.sh"
CREATE_BUCKET = SCRIPTS_DIR / "create-app-bucket.sh"

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"aws[_-]?secret[_-]?access[_-]?key\s*=\s*['\"]?[A-Za-z0-9/+=]{20,}", re.I),
]


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_aws_deploy_scripts_exist_under_scripts_aws():
    assert BOOTSTRAP.is_file()
    assert SMOKE.is_file()
    assert CREATE_BUCKET.is_file()


def test_aws_deploy_scripts_use_bash_shebang():
    for path in (BOOTSTRAP, SMOKE):
        first = _read(path).splitlines()[0]
        assert first.startswith("#!/usr/bin/env bash"), path.name


def test_bootstrap_documents_required_env_vars():
    text = _read(BOOTSTRAP)
    for var in ("AWS_REGION", "ECR_REPOSITORY_URL", "IMAGE_TAG", "NARWAL_ENV_FILE"):
        assert var in text


def test_bootstrap_uses_instance_profile_not_static_keys():
    text = _read(BOOTSTRAP)
    assert "get-login-password" in text
    assert "aws ecr get-login-password" in text
    assert "AKIA" not in text
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)


def test_smoke_app_documents_public_url_and_seed_credentials():
    text = _read(SMOKE)
    assert "APP_PUBLIC_URL" in text
    assert "/api/health" in text
    assert "/api/auth/login" in text
    assert "SEED_DEMO" in text or "seed" in text.lower()
    assert "demo" in text


def test_smoke_script_does_not_embed_secrets():
    text = _read(SMOKE)
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)


def test_bootstrap_binds_api_to_localhost_only():
    text = _read(BOOTSTRAP)
    assert "127.0.0.1:8080:8080" in text
