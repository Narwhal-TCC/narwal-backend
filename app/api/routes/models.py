from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.services.model_registry import list_models

router = APIRouter(tags=["models"])


@router.get("/models")
def list_registered_models(
    _current_user: dict[str, str] = Depends(get_current_user),
) -> dict:
    return {
        "models": [
            {"id": entry.id, "label": entry.label, "is_default": entry.is_default}
            for entry in list_models()
        ]
    }
