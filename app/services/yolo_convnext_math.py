"""Pure geometry helpers ported from pipeline_inferencia.py (notebook parity)."""

from __future__ import annotations

import numpy as np


def caixa_recorte(box: tuple[float, float, float, float], w: int, h: int, modo: str) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    if modo.startswith("m"):
        m = float(modo[1:])
        x1, y1, x2, y2 = x1 - m * bw, y1 - m * bh, x2 + m * bw, y2 + m * bh
    else:
        k = float(modo[1:])
        s = max(k * max(bw, bh), 32)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        x1, y1, x2, y2 = cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2
    return (max(0, x1), max(0, y1), min(w, x2), min(h, y2))


def iou(a: tuple[float, float, float, float] | np.ndarray, b: tuple[float, float, float, float] | np.ndarray) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    x1, y1, x2, y2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / ((ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter + 1e-9)


def nms(boxes: np.ndarray, iou_threshold: float) -> np.ndarray:
    import torch
    import torchvision

    if len(boxes) == 0:
        return boxes
    keep = torchvision.ops.nms(
        torch.tensor(boxes[:, :4], dtype=torch.float32),
        torch.tensor(boxes[:, 4], dtype=torch.float32),
        iou_threshold,
    ).numpy()
    return boxes[keep]


def wbf(listas: list[np.ndarray], iou_thr: float = 0.55) -> np.ndarray:
    """Weighted Boxes Fusion (Solovyev et al., 2021)."""
    m = len(listas)
    caixas = sorted([(b, k) for k, lista in enumerate(listas) for b in lista], key=lambda t: -t[0][4])
    clusters: list[dict] = []
    for b, k in caixas:
        alvo = next((c for c in clusters if iou(b[:4], c["f"][:4]) > iou_thr), None)
        if alvo is None:
            clusters.append({"m": [(b, k)], "f": b.copy()})
        else:
            alvo["m"].append((b, k))
            stacked = np.array([x for x, _ in alvo["m"]])
            weights = stacked[:, 4:5]
            alvo["f"] = np.r_[(stacked[:, :4] * weights).sum(0) / weights.sum(), stacked[:, 4].mean()]
    out: list[np.ndarray] = []
    for cluster in clusters:
        fused = cluster["f"].copy()
        fused[4] = fused[4] * min(len({k for _, k in cluster["m"]}), m) / m
        out.append(fused)
    return np.array(out) if out else np.zeros((0, 5))
