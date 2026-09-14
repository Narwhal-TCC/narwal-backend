import json
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.repositories.users import ensure_table

DEFAULT_LIST_LIMIT = 50


def new_analysis_id() -> str:
    return str(ULID())


def _encode(value: Any) -> Any:
    """DynamoDB rejects floats, so route payloads through Decimal."""
    return json.loads(json.dumps(value), parse_float=Decimal)


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_record(item: dict) -> dict:
    inference_ms = item.get("inference_ms")
    return {
        "id": item["analysis_id"],
        "org_id": item["org_id"],
        "user_id": item["user_id"],
        "status": item["status"],
        "detections": _decode(item.get("detections", [])),
        "image_s3_key": item["image_s3_key"],
        "image_content_type": item["image_content_type"],
        "created_at": item["created_at"],
        "inference_ms": int(inference_ms) if inference_ms is not None else None,
    }


class AnalysisRepository:
    def __init__(self, table: Any | None = None) -> None:
        self.table = table or ensure_table()

    def put_analysis(
        self,
        analysis_id: str,
        org_id: str,
        user_id: str,
        detections: list[dict],
        image_s3_key: str,
        image_content_type: str,
        created_at: str,
        inference_ms: int | None = None,
        status: str = "succeeded",
    ) -> dict:
        item = {
            "PK": f"ORG#{org_id}",
            "SK": f"ANALYSIS#{analysis_id}",
            "analysis_id": analysis_id,
            "org_id": org_id,
            "user_id": user_id,
            "status": status,
            "detections": _encode(detections),
            "image_s3_key": image_s3_key,
            "image_content_type": image_content_type,
            "created_at": created_at,
            "inference_ms": inference_ms,
        }
        self.table.put_item(Item=item)
        return _to_record(item)

    def get_analysis(self, org_id: str, analysis_id: str) -> dict | None:
        response = self.table.get_item(
            Key={"PK": f"ORG#{org_id}", "SK": f"ANALYSIS#{analysis_id}"}
        )
        item = response.get("Item")
        return _to_record(item) if item else None

    def list_by_org(
        self,
        org_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[dict]:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(f"ORG#{org_id}")
            & Key("SK").begins_with("ANALYSIS#"),
            ScanIndexForward=False,
            Limit=offset + limit,
        )
        items = response.get("Items", [])[offset : offset + limit]
        return [_to_record(item) for item in items]
