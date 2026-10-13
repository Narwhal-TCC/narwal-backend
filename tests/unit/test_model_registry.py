import pytest

from app.core.errors import UnknownModelError
from app.services.model_registry import REGISTRY, list_models, resolve_model_id


def test_registry_has_single_two_stage_entry():
    models = list_models()
    assert len(models) == 1
    entry = models[0]
    assert entry.id == "two-stage-pt"
    assert entry.label == "RetinaNet + fusão (PyTorch)"
    assert entry.is_default is True
    assert REGISTRY[0].id == "two-stage-pt"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "two-stage-pt"),
        ("", "two-stage-pt"),
        ("two-stage-pt", "two-stage-pt"),
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
