from dataclasses import dataclass

from app.core.errors import UnknownModelError

DEFAULT_MODEL_ID = "two-stage-pt"


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    id: str
    label: str
    is_default: bool


REGISTRY: tuple[RegisteredModel, ...] = (
    RegisteredModel(
        id="two-stage-pt",
        label="RetinaNet + fusão (PyTorch)",
        is_default=True,
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
