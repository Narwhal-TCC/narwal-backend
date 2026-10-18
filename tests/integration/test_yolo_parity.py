from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services.yolo_convnext import YoloConvnextGateway, YoloConvnextWeights
from app.services.yolo_convnext_math import iou

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PIPELINE = (
    REPO_ROOT.parent
    / "data-science-notebooks"
    / "MODELS"
    / "TESTES_RECORTES_YOLO_CONVNEXT"
    / "pipeline_inferencia.py"
)
WEIGHTS_DIR = REPO_ROOT / "data" / "models" / "v2"
WEIGHT_FILES = (
    "G5_best.pt",
    "yolo_a_best.pt",
    "convnext_pico_224_s42.pt",
    "convnext_pico_224_s43.pt",
    "convnext_pico_224_s44.pt",
)
BALANCED_CONFIG = (
    NOTEBOOK_PIPELINE.parent
    / "modelos"
    / "pipeline_config_fusao_equilibrado.json"
)


def _weights_ready() -> bool:
    if not NOTEBOOK_PIPELINE.is_file():
        return False
    return all((WEIGHTS_DIR / name).is_file() for name in WEIGHT_FILES)


def _load_notebook_pipeline():
    spec = importlib.util.spec_from_file_location("notebook_pipeline", NOTEBOOK_PIPELINE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["notebook_pipeline"] = module
    spec.loader.exec_module(module)
    return module.Pipeline(BALANCED_CONFIG)


@pytest.mark.weights
def test_api_gateway_matches_notebook_pipeline_on_fixture(tmp_path):
    if not _weights_ready():
        pytest.skip("v2 weights or notebook pipeline path not available")

    image = Image.new("RGB", (640, 480), color=(40, 80, 120))
    image_path = tmp_path / "fixture.png"
    image.save(image_path)
    array = np.asarray(image)

    notebook = _load_notebook_pipeline()
    notebook_rows = notebook.analisar(image_path)

    class LocalStore:
        def download_model(self, s3_uri: str | None = None) -> bytes:
            mapping = {
                "s3://narwal/models/v2/G5_best.pt": WEIGHTS_DIR / "G5_best.pt",
                "s3://narwal/models/v2/yolo_a_best.pt": WEIGHTS_DIR / "yolo_a_best.pt",
                "s3://narwal/models/v2/convnext_pico_224_s42.pt": (
                    WEIGHTS_DIR / "convnext_pico_224_s42.pt"
                ),
                "s3://narwal/models/v2/convnext_pico_224_s43.pt": (
                    WEIGHTS_DIR / "convnext_pico_224_s43.pt"
                ),
                "s3://narwal/models/v2/convnext_pico_224_s44.pt": (
                    WEIGHTS_DIR / "convnext_pico_224_s44.pt"
                ),
            }
            assert s3_uri in mapping
            return mapping[s3_uri].read_bytes()

    weights = YoloConvnextWeights(LocalStore())
    gateway = YoloConvnextGateway(weights, fusion_conf=0.4)
    api_rows = gateway.predict(array)

    assert len(api_rows) == len(notebook_rows)
    for api_row in api_rows:
        api_box = (api_row["x1"], api_row["y1"], api_row["x2"], api_row["y2"])
        best_iou = 0.0
        matched_label = None
        for nb in notebook_rows:
            nb_box = tuple(nb["caixa"])
            score = iou(api_box, nb_box)
            if score > best_iou:
                best_iou = score
                matched_label = nb["classe"]
        assert best_iou >= 0.99
        assert api_row["label"] == matched_label
