import io

import pytest
import torch

from app.core.errors import ModelUnavailableError
from app.services.yolo_fusion_v3 import build_solo_v3_classifier
from app.services.yolo_fusion_v3_models import (
    FUSION_V3_IMG_SIZE,
    CropFusionClassifier,
)


def _solo_checkpoint_bytes(backbone: str) -> bytes:
    model = CropFusionClassifier((backbone,))
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return buffer.getvalue()


@pytest.fixture
def convnext_solo_bytes() -> bytes:
    return _solo_checkpoint_bytes("convnext_pico")


@pytest.fixture
def mobilevit_solo_bytes() -> bytes:
    return _solo_checkpoint_bytes("mobilevitv2_100")


def test_build_solo_convnext_pico_output_shape(convnext_solo_bytes):
    model = build_solo_v3_classifier(
        convnext_solo_bytes,
        "s3://narwal/models/v3/solo_convnext_pico_s42.pt",
    )
    batch = torch.rand(2, 3, FUSION_V3_IMG_SIZE, FUSION_V3_IMG_SIZE)
    logits = model(batch)
    assert logits.shape == (2, 2)


def test_build_solo_mobilevit_output_shape(mobilevit_solo_bytes):
    model = build_solo_v3_classifier(
        mobilevit_solo_bytes,
        "solo_mobilevitv2_100_s43.pt",
    )
    batch = torch.rand(3, 3, FUSION_V3_IMG_SIZE, FUSION_V3_IMG_SIZE)
    logits = model(batch)
    assert logits.shape == (3, 2)


def test_build_solo_rejects_bad_artifact_name(convnext_solo_bytes):
    with pytest.raises(ModelUnavailableError):
        build_solo_v3_classifier(convnext_solo_bytes, "fusao_edgenext_small_best.pt")


def test_build_solo_rejects_mismatched_state_dict(mobilevit_solo_bytes):
    with pytest.raises(ModelUnavailableError):
        build_solo_v3_classifier(
            mobilevit_solo_bytes,
            "solo_convnext_pico_s42.pt",
        )
