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
        description=(
            "Recomendado no dia a dia: equilibra achar minas e limitar falsos alarmes."
        ),
        is_default=True,
    ),
    RegisteredModel(
        id="yolo-convnext-recall",
        label="YOLO + ConvNeXt (recall)",
        description=(
            "Prioriza não deixar minas passarem; tende a gerar mais pontos para revisar."
        ),
        is_default=False,
    ),
    RegisteredModel(
        id="two-stage-pt",
        label="RetinaNet + fusão (PyTorch)",
        description=(
            "Versão anterior: menos falsos alarmes, porém localiza menos minas. "
            "Indicado para comparar com análises antigas."
        ),
        is_default=False,
    ),
    RegisteredModel(
        id="yolo-fusion-v3",
        label="YOLO A + fusão ConvNeXt/EdgeNeXt (v3)",
        description=(
            "Variação mais nova do detector: localiza mais minas que o legado, "
            "com mais falsos alarmes que o equilibrado."
        ),
        is_default=False,
    ),
    RegisteredModel(
        id="yolo-fusion-mobilevit",
        label="YOLO A + fusão ConvNeXt/MobileViTv2",
        description=(
            "Mesmo detector da v3, com classificador ConvNeXt + MobileViTv2 nos recortes."
        ),
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
