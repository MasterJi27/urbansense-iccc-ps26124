# pothole_opt_v2 — D40-focused fine-tune

Started: 2026-11-02 (Windows RTX 4060 box, `.venv-train`)
Status: completed — early-stopped at epoch 45 (best epoch 15), evaluated; exported and deployed as a model-only ONNX swap on 2026-11-04

## Why this run exists

`pothole_ft_v1` early-stopped at epoch 14 of 30 because it watched the India validation split, which
the shipped base checkpoint had already memorised. `best.pt` was epoch 2 by fitness, not the epoch the
D40 work needed. This run replaces the selection signal with a **D40-only Kent validation split**
carved out of the Kent training photos in whole 20-photo blocks, with a 10-photo embargo. The
70-photo Kent holdout (`Pothole-079..088`, `184..195`, `301..310`, `341..350`, `491..500`,
`541..550`, `621..630`) is copied unchanged and is never used for selection.

## Isolation

- Starts from `ml/models/road_damage/YOLOv8s_RDD_india.pt` (shipped weights), read-only.
- `--no-promote --skip-test`: shipped weights, `metrics.json`, backend and ONNX are not touched; the
  India test split is not evaluated during training.
- New dataset: `data/rdd_pothole_opt_v2` (hard links only; `data/rdd_simsplit_pothole_mix` unchanged).
- Run artefacts: `ml/models/road_damage/runs/pothole_opt_v2/`.
- Console log: `logs/pothole_opt_v2_console.log` and `.err.log`.

## Dataset

| split | images | D00 | D10 | D20 | D40 |
|---|---:|---:|---:|---:|---:|
| train | 16,374 | 13,491 | 7,469 | 8,324 | 5,615 |
| kent_val (selection) | 80 | 0 | 0 | 0 | 117 |
| val (India, reporting) | 322 | 165 | 9 | 179 | 329 |
| test (India, final only) | 322 | 151 | 4 | 187 | 330 |
| kent_holdout (final only) | 70 | 0 | 0 | 0 | 137 |

## Recipe

| item | value |
|---|---|
| model | YOLOv8s (deployment-compatible with the existing ONNX/640 pipeline) |
| epochs / patience | 120 / 30 (on kent_val D40 mAP50-95 fitness) |
| batch / imgsz | 16 / 640 |
| optimizer | SGD, lr0 0.001, cosine, warmup 3, weight decay 0.0005 |
| freeze | 0 |
| augmentation | mosaic 1.0, close_mosaic 15, mixup 0.1, default HSV/scale/flip |
| sampling | repeat-factor class balance + `pothole_=2`, `India_=1.5` |
| checkpoints | every 5 epochs |
| workers / AMP | 8 / on |

## Selection plan

1. `best.pt` is chosen on `kent_val` (D40 only).
2. After training, score `best.pt` and `last.pt` on India val, India test and the untouched Kent
   holdout with `eval_rdd.py`.
3. Compare against shipped, `pothole_ft_v1/best.pt` (epoch 2) and `pothole_ft_v1/last.pt` (epoch 14).
4. No promotion or export during training. Deployment happened later, after the user approved it;
   see `docs/MODEL_OPTIMIZATION_REPORT.md` section 15.

## Outcome

Training early-stopped at epoch 45 (best epoch 15 + patience 30) in 163.1 min. `best.pt` (epoch 15)
scored D40 AP50 **0.6591** on the 70-photo Kent holdout vs **0.2555** for the shipped model
(paired +0.404 [+0.305, +0.492]). India test D40 AP50 was 0.6250 vs 0.6577 (paired −0.033,
n.s.); India val 0.6447 vs 0.6631 (n.s.). Exported to ONNX and deployed on 2026-11-04 after
70/70 Kent holdout decoded detections matched PyTorch. See `FINAL_RESULTS.md` and
`docs/MODEL_OPTIMIZATION_REPORT.md` section 15.
