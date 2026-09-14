from typing import Any

from botocore.exceptions import ClientError

from app.core.aws import dynamodb_resource
from app.core.config import get_settings
from app.core.security import Role


def ensure_table(dynamodb: Any | None = None, table_name: str | None = None):
    resource = dynamodb or dynamodb_resource()
    name = table_name or get_settings().ddb_table
    table = resource.Table(name)
    try:
        table.load()
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        table = resource.create_table(
            TableName=name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
    return table


class UserRepository:
    def __init__(self, table: Any | None = None) -> None:
        self.table = table or ensure_table()

    def put_org(self, org_id: str, name: str) -> None:
        self.table.put_item(
            Item={"PK": f"ORG#{org_id}", "SK": "META", "org_id": org_id, "name": name}
        )

    def get_org(self, org_id: str) -> dict | None:
        response = self.table.get_item(Key={"PK": f"ORG#{org_id}", "SK": "META"})
        return response.get("Item")

    def put_user(
        self,
        user_id: str,
        org_id: str,
        username: str,
        password_hash: str,
        role: Role = "member",
    ) -> None:
        self.table.put_item(
            Item={
                "PK": f"ORG#{org_id}",
                "SK": f"USER#{user_id}",
                "user_id": user_id,
                "org_id": org_id,
                "username": username,
                "password_hash": password_hash,
                "role": role,
            }
        )
        self.table.put_item(
            Item={
                "PK": f"USERNAME#{username}",
                "SK": "USER",
                "username": username,
                "user_id": user_id,
                "org_id": org_id,
            }
        )

    def get_user(self, org_id: str, user_id: str) -> dict | None:
        response = self.table.get_item(
            Key={"PK": f"ORG#{org_id}", "SK": f"USER#{user_id}"}
        )
        return response.get("Item")

    def get_username_lookup(self, username: str) -> dict | None:
        response = self.table.get_item(Key={"PK": f"USERNAME#{username}", "SK": "USER"})
        return response.get("Item")

    def get_by_username(self, username: str) -> dict | None:
        lookup = self.get_username_lookup(username)
        if lookup is None:
            return None
        return self.get_user(lookup["org_id"], lookup["user_id"])
