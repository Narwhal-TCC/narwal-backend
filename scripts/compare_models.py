#!/usr/bin/env python3
"""Compare detection models on YOLO-labelled images: mine recall and false alarms per image."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.bootstrap.seed_demo_analyses import iter_labeled_samples
from app.core.config import (
    convnext_local_path_list,
    convnext_s3_uri_list,
    g5v2_ensemble_local_path_list,
    g5v2_ensemble_s3_uri_list,
    get_settings,
)
from app.services.gateway_pool import YOLO_BALANCED_ID, YOLO_G5V2_MOBILEVIT_ID, GatewayPool
from app.services.yolo_convnext_math import iou

Box = tuple[float, float, float, float]
MINE_CLASS_ID = 0
DEFAULT_IOU_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class ImageComparisonMetrics:
    stem: str
    gt_mine_count: int
    matched_mines: int
    false_alarms: int

    @property
    def contributes_to_recall(self) -> bool:
        return self.gt_mine_count > 0


@dataclass(frozen=True, slots=True)
class ModelComparisonSummary:
    model_id: str
    recall: float
    false_alarms_per_image: float
    per_image: tuple[ImageComparisonMetrics, ...]


def greedy_match(
    gt_boxes: list[Box],
    pred_boxes: list[Box],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> tuple[int, int]:
    """Return (matched_gt_count, false_alarm_count) with one-to-one IoU matching."""
    if not pred_boxes:
        return 0, 0
    if not gt_boxes:
        return 0, len(pred_boxes)

    pairs: list[tuple[float, int, int]] = []
    for gi, gt in enumerate(gt_boxes):
        for pi, pred in enumerate(pred_boxes):
            score = iou(gt, pred)
            if score >= iou_threshold:
                pairs.append((score, gi, pi))
    pairs.sort(key=lambda t: -t[0])

    used_gt: set[int] = set()
    used_pred: set[int] = set()
    for _, gi, pi in pairs:
        if gi in used_gt or pi in used_pred:
            continue
        used_gt.add(gi)
        used_pred.add(pi)

    matched = len(used_gt)
    false_alarms = len(pred_boxes) - len(used_pred)
    return matched, false_alarms


def metrics_for_image(
    stem: str,
    gt_boxes: list[Box],
    pred_boxes: list[Box],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> ImageComparisonMetrics:
    matched, false_alarms = greedy_match(gt_boxes, pred_boxes, iou_threshold=iou_threshold)
    return ImageComparisonMetrics(
        stem=stem,
        gt_mine_count=len(gt_boxes),
        matched_mines=matched,
        false_alarms=false_alarms,
    )


def aggregate_recall(per_image: list[ImageComparisonMetrics]) -> float:
    gt_total = sum(m.gt_mine_count for m in per_image if m.contributes_to_recall)
    if gt_total == 0:
        return float("nan")
    matched = sum(m.matched_mines for m in per_image if m.contributes_to_recall)
    return matched / gt_total


def mean_false_alarms_per_image(per_image: list[ImageComparisonMetrics]) -> float:
    if not per_image:
        return float("nan")
    return sum(m.false_alarms for m in per_image) / len(per_image)


def summarize_model(
    model_id: str,
    per_image: list[ImageComparisonMetrics],
) -> ModelComparisonSummary:
    return ModelComparisonSummary(
        model_id=model_id,
        recall=aggregate_recall(per_image),
        false_alarms_per_image=mean_false_alarms_per_image(per_image),
        per_image=tuple(per_image),
    )


def load_mine_boxes_from_yolo(txt_path: Path, image_path: Path) -> list[Box]:
    raw = txt_path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in raw if line.strip()]
    if not lines:
        return []
    with Image.open(image_path) as img:
        width, height = img.size
    boxes: list[Box] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        class_id = int(parts[0])
        if class_id != MINE_CLASS_ID:
            continue
        cx, cy, bw, bh = (float(parts[i]) for i in range(1, 5))
        x1 = (cx - bw / 2) * width
        y1 = (cy - bh / 2) * height
        x2 = (cx + bw / 2) * width
        y2 = (cy + bh / 2) * height
        boxes.append((x1, y1, x2, y2))
    return boxes


def predictions_to_boxes(rows: list[dict]) -> list[Box]:
    return [(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])) for r in rows]


def build_local_store(repo_root: Path):
    settings = get_settings()
    v2 = repo_root / "data" / "models" / "v2"
    v3 = repo_root / "data" / "models" / "v3"

    def resolve(path: str | None, fallback: Path) -> Path:
        if path:
            candidate = Path(path)
            if candidate.is_file():
                return candidate
        return fallback

    g5_path = resolve(settings.yolo_g5_local_path, v2 / "G5_best.pt")
    g5v2_path = resolve(settings.yolo_g5v2_local_path, v2 / "G5_best_v2.pt")
    yolo_a_path = resolve(settings.yolo_a_local_path, v2 / "yolo_a_best.pt")
    convnext_paths = [
        resolve(local, v2 / Path(uri).name)
        for local, uri in zip(
            convnext_local_path_list(settings),
            convnext_s3_uri_list(settings),
            strict=True,
        )
    ]
    ensemble_paths = [
        resolve(local, v3 / Path(uri).name)
        for local, uri in zip(
            g5v2_ensemble_local_path_list(settings),
            g5v2_ensemble_s3_uri_list(settings),
            strict=True,
        )
    ]

    class LocalStore:
        def download_model(self, s3_uri: str | None = None) -> bytes:
            mapping = {
                settings.yolo_g5_s3_uri: g5_path,
                settings.yolo_g5v2_s3_uri: g5v2_path,
                settings.yolo_a_s3_uri: yolo_a_path,
            }
            for uri, path in zip(convnext_s3_uri_list(settings), convnext_paths, strict=True):
                mapping[uri] = path
            for uri, path in zip(
                g5v2_ensemble_s3_uri_list(settings),
                ensemble_paths,
                strict=True,
            ):
                mapping[uri] = path
            assert s3_uri in mapping, s3_uri
            return mapping[s3_uri].read_bytes()

    return LocalStore()


def iter_image_label_pairs(
    images_dir: Path,
    labels_dir: Path,
) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    year_subdirs = [p for p in images_dir.iterdir() if p.is_dir() and p.name.isdigit()]
    if year_subdirs:
        for txt_path, image_path in iter_labeled_samples(images_dir):
            if labels_dir == images_dir:
                pairs.append((txt_path, image_path))
            else:
                rel = txt_path.relative_to(images_dir)
                label_path = labels_dir / rel
                pairs.append((label_path, image_path))
        return pairs
    for txt_path in sorted(labels_dir.glob("*.txt")):
        if not txt_path.read_text(encoding="utf-8").strip():
            continue
        image_path = images_dir / f"{txt_path.stem}.jpg"
        if image_path.is_file():
            pairs.append((txt_path, image_path))
    return pairs


def compare_model_on_dataset(
    pool: GatewayPool,
    model_id: str,
    images_dir: Path,
    labels_dir: Path,
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> ModelComparisonSummary:
    gateway = pool.get(model_id)
    per_image: list[ImageComparisonMetrics] = []
    for label_path, img_path in iter_image_label_pairs(images_dir, labels_dir):
        gt_boxes = load_mine_boxes_from_yolo(label_path, img_path)
        array = np.asarray(Image.open(img_path).convert("RGB"))
        pred_boxes = predictions_to_boxes(gateway.predict(array))
        per_image.append(
            metrics_for_image(label_path.stem, gt_boxes, pred_boxes, iou_threshold=iou_threshold)
        )
    return summarize_model(model_id, per_image)


def format_report(summaries: list[ModelComparisonSummary]) -> str:
    lines: list[str] = []
    for summary in summaries:
        lines.append(f"model={summary.model_id}")
        lines.append(f"  recall={summary.recall:.4f}")
        lines.append(f"  false_alarms_per_image={summary.false_alarms_per_image:.4f}")
        for row in summary.per_image:
            lines.append(
                f"  {row.stem}: matched={row.matched_mines}/{row.gt_mine_count} "
                f"false_alarms={row.false_alarms}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="Directory of .jpg images")
    parser.add_argument("--labels", type=Path, required=True, help="Directory of YOLO .txt labels")
    parser.add_argument(
        "--model-a",
        default=YOLO_BALANCED_ID,
        help="First model id (default: balanced)",
    )
    parser.add_argument(
        "--model-b",
        default=YOLO_G5V2_MOBILEVIT_ID,
        help="Second model id (default: G5 v2 ensemble)",
    )
    parser.add_argument("--iou", type=float, default=DEFAULT_IOU_THRESHOLD)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    args = parser.parse_args(argv)

    if not args.images.is_dir() or not args.labels.is_dir():
        print("images and labels must be existing directories", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    pool = GatewayPool(build_local_store(repo_root))
    common = dict(iou_threshold=args.iou)
    summaries = [
        compare_model_on_dataset(pool, args.model_a, args.images, args.labels, **common),
        compare_model_on_dataset(pool, args.model_b, args.images, args.labels, **common),
    ]

    if args.json:
        payload = [
            {
                "model_id": s.model_id,
                "recall": s.recall,
                "false_alarms_per_image": s.false_alarms_per_image,
                "per_image": [asdict(row) for row in s.per_image],
            }
            for s in summaries
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
