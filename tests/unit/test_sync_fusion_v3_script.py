import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "sync_fusion_v3_from_notebooks",
    _REPO / "scripts" / "sync_fusion_v3_from_notebooks.py",
)
assert _spec and _spec.loader
_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sync)
main = _sync.main


def test_sync_copies_classifier_and_optional_yolo(tmp_path):
    notebook = tmp_path / "notebooks"
    backend = tmp_path / "backend"
    yolo_src = (
        notebook
        / "MODELS/TESTE_BOX_YOLO/runs/detect/work/runs/modelA_yolo_p2/weights/best.pt"
    )
    classifier_src = (
        notebook
        / "MODELS/TESTE_CONNEXT_FUSAO/checkpoints/melhores/fusao_edgenext_small/best.pt"
    )
    yolo_src.parent.mkdir(parents=True)
    classifier_src.parent.mkdir(parents=True)
    yolo_src.write_bytes(b"yolo-bytes")
    classifier_src.write_bytes(b"classifier-bytes")

    exit_code = main(
        [
            "--notebook-root",
            str(notebook),
            "--backend-root",
            str(backend),
        ]
    )
    assert exit_code == 0
    classifier_path = backend / "data/models/v3/fusao_edgenext_small_best.pt"
    assert classifier_path.read_bytes() == b"classifier-bytes"
    assert (backend / "data/models/v2/yolo_a_best.pt").read_bytes() == b"yolo-bytes"


def test_sync_missing_notebook_root_returns_nonzero(tmp_path):
    assert (
        main(
            [
                "--notebook-root",
                str(tmp_path / "missing"),
                "--backend-root",
                str(tmp_path / "backend"),
            ]
        )
        == 1
    )
