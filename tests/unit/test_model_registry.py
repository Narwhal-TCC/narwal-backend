import pytest

from app.core.errors import UnknownModelError
from app.services.model_registry import (
    DEFAULT_MODEL_ID,
    REGISTRY,
    list_models,
    resolve_model_id,
)


def test_registry_lists_four_models_in_catalog_order():
    models = list_models()
    assert len(models) == 4
    assert [entry.id for entry in models] == [
        "yolo-convnext-balanced",
        "yolo-convnext-recall",
        "two-stage-pt",
        "yolo-fusion-v3",
    ]
    balanced = models[0]
    assert balanced.label == "YOLO + ConvNeXt (equilibrado)"
    assert balanced.description == (
        "Recomendado no dia a dia: equilibra achar minas e limitar falsos alarmes."
    )
    assert balanced.is_default is True
    assert sum(1 for entry in models if entry.is_default) == 1
    assert REGISTRY[0].id == "yolo-convnext-balanced"
    fusion_v3 = models[3]
    assert fusion_v3.id == "yolo-fusion-v3"
    assert fusion_v3.label == "YOLO A + fusão ConvNeXt/EdgeNeXt (v3)"


def test_default_model_id_is_balanced_pipeline():
    assert DEFAULT_MODEL_ID == "yolo-convnext-balanced"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "yolo-convnext-balanced"),
        ("", "yolo-convnext-balanced"),
        ("yolo-convnext-balanced", "yolo-convnext-balanced"),
        ("yolo-convnext-recall", "yolo-convnext-recall"),
        ("two-stage-pt", "two-stage-pt"),
        ("yolo-fusion-v3", "yolo-fusion-v3"),
    ],
)
def test_resolve_model_id_accepts_default_and_exact_id(raw, expected):
    assert resolve_model_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "two-stage-pt ",
        "Two-Stage-Pt",
        " two-stage-pt",
        "not-a-model",
    ],
)
def test_resolve_model_id_rejects_unknown_without_trimming(raw):
    with pytest.raises(UnknownModelError):
        resolve_model_id(raw)
