import boto3
from boto3.dynamodb.conditions import Key
from moto import mock_aws

from app.bootstrap.seed import run_seed
from app.core.config import get_settings
from app.core.security import verify_password
from app.repositories.users import UserRepository, ensure_table


@mock_aws
def test_run_seed_creates_env_platform_admin_idempotently(monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_USERNAME", "root-admin")
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "strong-test-password")
    monkeypatch.setenv("PLATFORM_ADMIN_ORG_ID", "platform-org")
    monkeypatch.setenv("SEED_DEMO_USERNAME", "frontend-user")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "frontend-password")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "frontend-org")
    get_settings.cache_clear()
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ensure_table(dynamodb, "seed-test")
    repository = UserRepository(table)

    run_seed(repository)
    first_user = repository.get_by_username("root-admin")
    run_seed(repository)
    second_user = repository.get_by_username("root-admin")
    users = table.query(
        KeyConditionExpression=Key("PK").eq("ORG#platform-org")
        & Key("SK").begins_with("USER#")
    )["Items"]

    assert first_user is not None
    assert first_user["org_id"] == "platform-org"
    assert first_user["role"] == "platform_admin"
    assert verify_password("strong-test-password", first_user["password_hash"]) is True
    assert second_user == first_user
    assert len(users) == 1


@mock_aws
def test_run_seed_creates_demo_member_idempotently(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERNAME", "frontend-user")
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "frontend-password")
    monkeypatch.setenv("SEED_DEMO_ORG_ID", "frontend-org")
    get_settings.cache_clear()
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ensure_table(dynamodb, "seed-test-demo")
    repository = UserRepository(table)

    run_seed(repository)
    first_user = repository.get_by_username("frontend-user")
    run_seed(repository)
    second_user = repository.get_by_username("frontend-user")
    demo_org = repository.get_org("frontend-org")
    users = table.query(
        KeyConditionExpression=Key("PK").eq("ORG#frontend-org")
        & Key("SK").begins_with("USER#")
    )["Items"]

    assert demo_org is not None
    assert demo_org["name"] == "Demo"
    assert first_user is not None
    assert first_user["org_id"] == "frontend-org"
    assert first_user["role"] == "member"
    assert verify_password("frontend-password", first_user["password_hash"]) is True
    assert second_user == first_user
    assert len(users) == 1
