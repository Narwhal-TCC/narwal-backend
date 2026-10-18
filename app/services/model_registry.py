from dataclasses import dataclass

from app.core.errors import UnknownModelError

DEFAULT_MODEL_ID = "yolo-convnext-balanced"
LEGACY_DEFAULT_MODEL_ID = "two-stage-pt"


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    id: str
    label: str
    description: str
    is_default: bool


REGISTRY: tuple[RegisteredModel, ...] = (
    RegisteredModel(
        id="yolo-convnext-balanced",
        label="YOLO + ConvNeXt (equilibrado)",
        description="53 de 75 minas no teste, 11 falsos alarmes",
        is_default=True,
    ),
    RegisteredModel(
        id="yolo-convnext-recall",
        label="YOLO + ConvNeXt (recall)",
        description="58 de 75 minas no teste, 25 falsos alarmes",
        is_default=False,
    ),
    RegisteredModel(
        id="two-stage-pt",
        label="RetinaNet + fusão (PyTorch)",
        description="36 de 75 minas no teste, 7 falsos alarmes",
        is_default=False,
    ),
)


def list_models() -> list[RegisteredModel]:
    return list(REGISTRY)


def resolve_model_id(raw: str | None) -> str:
    if raw is None or raw == "":
        return DEFAULT_MODEL_ID
    for entry in REGISTRY:
        if raw == entry.id:
            return entry.id
    raise UnknownModelError()
