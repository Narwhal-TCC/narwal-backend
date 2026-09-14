import boto3
from moto import mock_aws

from app.repositories.users import UserRepository, ensure_table


@mock_aws
def test_create_org_and_user_then_fetch_by_username():
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ensure_table(dynamodb, "users-test")
    repository = UserRepository(table)

    repository.put_org(org_id="org-1", name="Sonar Team")
    repository.put_user(
        user_id="user-1",
        org_id="org-1",
        username="operator",
        password_hash="hashed-password",
        role="member",
    )

    assert repository.get_org("org-1") == {
        "PK": "ORG#org-1",
        "SK": "META",
        "org_id": "org-1",
        "name": "Sonar Team",
    }
    assert repository.get_by_username("operator") == {
        "PK": "ORG#org-1",
        "SK": "USER#user-1",
        "user_id": "user-1",
        "org_id": "org-1",
        "username": "operator",
        "password_hash": "hashed-password",
        "role": "member",
    }


@mock_aws
def test_username_lookup_contains_user_and_org_ids():
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ensure_table(dynamodb, "users-test")
    repository = UserRepository(table)
    repository.put_user(
        user_id="admin-1",
        org_id="platform",
        username="admin",
        password_hash="hashed-password",
        role="platform_admin",
    )

    lookup = repository.get_username_lookup("admin")

    assert lookup == {
        "PK": "USERNAME#admin",
        "SK": "USER",
        "username": "admin",
        "user_id": "admin-1",
        "org_id": "platform",
    }
