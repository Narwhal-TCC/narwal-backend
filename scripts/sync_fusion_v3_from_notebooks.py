#!/usr/bin/env python3
"""Copy main-branch fusion v3 weights from data-science-notebooks into narwal-backend data/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_NOTEBOOK_ROOT = Path(__file__).resolve().parents[2] / "data-science-notebooks"
BACKEND_ROOT = Path(__file__).resolve().parents[1]

YOLO_REL = (
    "MODELS/TESTE_BOX_YOLO/runs/detect/work/runs/modelA_yolo_p2/weights/best.pt"
)
CLASSIFIER_REL = (
    "MODELS/TESTE_CONNEXT_FUSAO/checkpoints/melhores/fusao_edgenext_small/best.pt"
)


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook-root",
        type=Path,
        default=DEFAULT_NOTEBOOK_ROOT,
        help="Path to data-science-notebooks checkout",
    )
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=BACKEND_ROOT,
        help="Path to narwal-backend checkout",
    )
    args = parser.parse_args(argv)

    if not args.notebook_root.is_dir():
        print(f"notebook root not found: {args.notebook_root}", file=sys.stderr)
        return 1

    yolo_src = args.notebook_root / YOLO_REL
    classifier_src = args.notebook_root / CLASSIFIER_REL
    yolo_dest = args.backend_root / "data/models/v2/yolo_a_best.pt"
    classifier_dest = args.backend_root / "data/models/v3/fusao_edgenext_small_best.pt"

    if yolo_src.is_file():
        _copy(yolo_src, yolo_dest)
        print(f"copied YOLO A -> {yolo_dest}")
    else:
        print(
            f"skipped YOLO A (missing {yolo_src}); place weights at {yolo_dest} manually",
            file=sys.stderr,
        )

    if not classifier_src.is_file():
        print(f"classifier source missing: {classifier_src}", file=sys.stderr)
        return 1

    _copy(classifier_src, classifier_dest)
    print(f"copied fusion v3 classifier -> {classifier_dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
