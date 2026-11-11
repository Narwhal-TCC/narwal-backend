# New G5 detector + ConvNeXt/MobileViT classifier ensemble

> Plan from this document. Each slice below carries its own shape - copy it, do not re-derive it.
> Status: confirmed by Hideki (non-default first, flip after comparison), 2026-11-11

## Situation

- Project: in active construction - local development, TCC defence December 2026; no real users.
- Decision: committed by Hideki - ship the newly trained G5 (received 2026-11-11) with the best-ranked ViT classifier from the v3 notebook; asked for it as default, narrowed to non-default-then-flip after the checkpoint metrics below.
- In flight: copies the `yolo-convnext-balanced` pipeline (two detectors, WBF, averaged classifier softmax) and the single-backbone `CropFusionClassifier` load already used by `yolo-fusion-v3`; retraining or re-evaluating any model in the notebooks stays out.
- At stake: cheap while non-default - one registry entry, removable; flipping the default is the only consequential step and is gated by Slice `Comparison`.

## Problem

Construction. The v3 notebook produced a better-ranked classifier and the data-science side produced a retrained G5, and neither is reachable from the product, so the thesis cannot show or compare them. What the files say, and why this ships non-default: the new G5's own validation metrics are precision 0.880 / recall 0.627 / mAP50-95 0.404 against the current G5's 0.757 / 0.667 / 0.419, on *different* validation sets (embedded `train_metrics` of each checkpoint), so neither "better" nor "worse" is established - and recall is the axis this product weights most. The classifier ensemble's test-AUC gain over the 3-seed ConvNeXt-pico reference is +0.001, 95% CI [-0.023, +0.031] (v3 notebook paired bootstrap) - indistinguishable from noise.

## Success

- Worked if: on the same test images, the new model's mine recall is ≥ `yolo-convnext-balanced`'s and false alarms per image are not higher; then it becomes the default.
- Going wrong: recall below the balanced model's on the comparison run - it stays a non-default option (or is removed), and the default does not move.
- Review: when the comparison run lands - Hideki.

## Boundary

In: the new G5 as a separate artifact; the six-checkpoint ConvNeXt-pico + MobileViTv2 classifier ensemble; one new registered model; one comparison run that decides the default flip.

Out: the early-fusion checkpoints (`b12`, `b32`, `robusta`) - ranked below the ensemble, and two of them have a dead ConvNeXt branch. Retraining or recalibrating thresholds for the new crops - notebook work. A recall-tuned variant of the new model - add only if the comparison argues for it.

Unchanged: `data/models/v2/G5_best.pt` and the `YOLO_G5_*` settings, `yolo-convnext-balanced` and every other registered model, existing analyses' `model_id`, the detection JSON shape.

## Shape

A new registered model runs the default pipeline unchanged - G5 and YOLO A fused by WBF, margin crops, averaged classifier softmax - with only its weights swapped: the new G5 in G5's slot and six classifiers in place of three. Its weights load independently of the default's, so neither model can serve the other's artifacts. The only door is the default flip, a one-line registry change made after the comparison.

The heavier alternative - a generic, config-driven pipeline where every model is a list of detector and classifier artifacts - wins only if a third model of this shape is coming, and nothing in the notebooks is queued.

## Key decisions

1. **The new G5 never replaces the old file.** It lives at `data/models/v2/G5_best_v2.pt` and `s3://narwal/models/v2/G5_best_v2.pt` under its own settings; the default keeps loading the old G5.
2. **"Best-ranked ViT" is the late ensemble of 3× `solo_convnext_pico` + 3× `solo_mobilevitv2_100` (seeds 42/43/44), averaged softmax** - the v3 notebook's winner by validation AUC (0.948 val / 0.935 test). Copied to `data/models/v3/` and `s3://narwal/models/v3/` with their file names.
3. **The pipeline is byte-for-byte the balanced one** - same detector configs, WBF/NMS thresholds, fusion confidence 0.4, crop mode and MILCO threshold. Only weights differ, so the comparison measures the weights and nothing else.
4. **The v3 solo checkpoints are bare state dicts with no `cfg`**; they load through `CropFusionClassifier` with a single backbone named by the checkpoint's sidecar JSON, never through the v2 ConvNeXt builder, which rejects them.
5. **The model id is `yolo-g5v2-convnext-mobilevit`, non-default.** It is the id stored on analyses, so it is never renamed after the first analysis; flipping the default changes `is_default`, not the id.
6. **The default flips only if recall holds** (Success › Worked if). Precision gains do not buy a recall loss.

## Work

| Slice | Delivers | Status |
|---|---|---|
| [Artifacts](#artifacts) | New G5 and the six classifiers present locally and on S3 under their own settings, seeded on boot | clear |
| [yolo-g5v2-convnext-mobilevit](#yolo-g5v2-convnext-mobilevit) | Selectable model in `GET /models`, runs analyses | open - 1 default taken |
| [Comparison](#comparison) | Recall and false alarms of both models on one test set; default flipped or not | clear |

Order: Artifacts → yolo-g5v2-convnext-mobilevit → Comparison.

Already handled by existing code: unknown model id → `UnknownModelError`; artifact missing or unloadable → `ModelUnavailableError`; model selection UI lists whatever `GET /models` returns.

Derivable from the repository, left to the plan: settings naming, the local-path-or-S3 seeding, label/description copy in Portuguese - all as `yolo-fusion-mobilevit` does them.

### Artifacts

**Delivers** the seven new weight files where the backend can load them. **Status: clear.**

| State | What should happen |
|---|---|
| Fresh checkout / container boot | Seeding uploads the seven files from their local paths to their S3 URIs, as for every other model |
| Old G5 already on S3 | Untouched (Key decision 1) |
| A file missing locally and on S3 | Only the new model fails to load; others are unaffected |

### yolo-g5v2-convnext-mobilevit

**Delivers** the new model selectable and producing detections. **Status: open - 1 default taken.**

| State | What should happen | Caller sees |
|---|---|---|
| Listed | Appears after the default, `is_default: false` | label "YOLO G5 v2 + ConvNeXt/MobileViT", description says it's under evaluation |
| Analysis with this model | Detections from the new pipeline; `model_id` stored | same response shape as every model |
| Default model used before | Loads only the default's weights; the new model's load lazily on first use | no change |
| New weights fail to load | That analysis fails as model-unavailable | the existing model-unavailable error |

Alternatives considered: share YOLO A between both weight loaders to save memory - wins if the container runs short of RAM with both loaded.

Open, default taken:
1. Crop margin and size the v3 solo classifiers were trained on - default: the balanced pipeline's `m0.15` at 224 px (the v3 notebook uses 224 px; margin not confirmed in its code).

### Comparison

**Delivers** the evidence for the default flip. **Status: clear (2026-11-11).**

**Image set:** local YOLO-labelled sonar images used by `seed_demo_analyses` — `data/2018` and `data/2021`, 139 non-empty `.txt` paired with `.jpg` (script `scripts/compare_models.py --images data --labels data`, IoU ≥ 0.5, MILCO class only in GT).

| Model | Mine recall | False alarms / image |
| --- | --- | --- |
| `yolo-convnext-balanced` | 0.841 | 0.331 |
| `yolo-g5v2-convnext-mobilevit` | 0.834 | 0.317 |

**Decision (G5V2-09):** no default flip — new recall is below balanced (0.834 < 0.841) even though false alarms per image are slightly lower (0.317 ≤ 0.331). `yolo-convnext-balanced` stays default; `yolo-g5v2-convnext-mobilevit` description records the recall vs false-alarm trade-off.

## Sources

- `data-science-notebooks/MODELS/TESTE_CONVNEXT/classificacao_convnext_parceiros_v3.ipynb` - classifier ranking, the bootstrap ΔAUC, the early-fusion branch ablation.
- Embedded `train_args` / `train_metrics` of both `G5_best.pt` checkpoints - architecture parity (yolov8s-p2, 1 class, 1024 px) and the non-comparable validation metrics.
- `.design/campaign-map.md` - project situation and deadline.
