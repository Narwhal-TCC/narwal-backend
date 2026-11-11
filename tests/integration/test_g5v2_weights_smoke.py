from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.config import (
    g5v2_ensemble_local_path_list,
    g5v2_ensemble_s3_uri_list,
    get_settings,
)
from app.services.gateway_pool import YOLO_G5V2_MOBILEVIT_ID, GatewayPool

REPO_ROOT = Path(__file__).resolve().parents[2]
V2_DIR = REPO_ROOT / "data" / "models" / "v2"
V3_DIR = REPO_ROOT / "data" / "models" / "v3"

ENSEMBLE_FILENAMES = (
    "solo_convnext_pico_s42.pt",
    "solo_convnext_pico_s43.pt",
    "solo_convnext_pico_s44.pt",
    "solo_mobilevitv2_100_s42.pt",
    "solo_mobilevitv2_100_s43.pt",
    "solo_mobilevitv2_100_s44.pt",
)


def _weights_ready() -> bool:
    settings = get_settings()
    paths = [
        V2_DIR / "G5_best_v2.pt",
        V2_DIR / "yolo_a_best.pt",
        *[V3_DIR / name for name in ENSEMBLE_FILENAMES],
    ]
    if settings.yolo_g5v2_local_path:
        paths[0] = Path(settings.yolo_g5v2_local_path)
    return all(path.is_file() for path in paths)


@pytest.mark.weights
def test_g5v2_gateway_predicts_on_fixture_without_error():
    if not _weights_ready():
        pytest.skip("G5 v2 ensemble weights not available locally")

    settings = get_settings()

    class LocalStore:
        def download_model(self, s3_uri: str | None = None) -> bytes:
            g5v2_path = settings.yolo_g5v2_local_path or str(V2_DIR / "G5_best_v2.pt")
            mapping = {
                settings.yolo_g5v2_s3_uri: Path(g5v2_path),
                settings.yolo_a_s3_uri: V2_DIR / "yolo_a_best.pt",
            }
            for uri, local in zip(
                g5v2_ensemble_s3_uri_list(settings),
                [Path(p) for p in g5v2_ensemble_local_path_list(settings)],
                strict=True,
            ):
                mapping[uri] = local
            assert s3_uri in mapping
            return mapping[s3_uri].read_bytes()

    image = Image.new("RGB", (640, 480), color=(40, 80, 120))
    array = np.asarray(image)

    rows = GatewayPool(LocalStore()).get(YOLO_G5V2_MOBILEVIT_ID).predict(array)

    assert isinstance(rows, list)
    for row in rows:
        assert set(row.keys()) == {
            "x1",
            "y1",
            "x2",
            "y2",
            "detector_score",
            "label",
            "confidence",
        }
