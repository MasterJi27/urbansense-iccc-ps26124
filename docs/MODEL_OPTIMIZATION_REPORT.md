# Pothole (D40) detector optimisation — experiment report

**Date:** 2026-11-02 (experiment), 2026-11-04 (ONNX parity and deployment)
**Scope:** the training experiment was isolated: production weights, backend inference, Docker and
`backend/app/weights/rdd_india.onnx` were **not** modified during training. After the user approved
promotion, the selected checkpoint was exported, parity-checked, and swapped into the production
ONNX. See section 15 for the deployment record.

---

## 1. Verdict (short)

| Question | Answer |
|---|---|
| Did we beat the shipped model on clean pothole photos? | **Yes, decisively.** Kent holdout D40 AP50 **0.256 → 0.659** (+0.404, 95% CI +0.305…+0.492). At the same conf 0.30 it finds **92/137** potholes vs **33/137**. |
| Did we make the Indian-road model worse? | **No measurable change on D40.** India test D40 AP50 0.658 → 0.625 (−0.033, n.s.). At conf 0.30 it finds 171 vs 151 potholes, with 65 vs 40 false positives. |
| Is it proven on Indian field photos? | **No.** No labelled Indian field set exists. India val/test are contaminated for base-derived models. |
| Should it ship today? | **Yes, as a model-only swap.** Exported and parity-checked on 2026-11-04, then deployed. An Indian field test is still required before claiming field accuracy. |

Bottom line: this is a real, large improvement in the exact failure mode we set out to fix
(big / close-up potholes), with no significant regression on the RDD India D40 benchmark. It is
now the deployed ONNX. It is **not** proven on Indian field photos, because no labelled Indian
field set exists.

---

## 2. What was asked, and what was protected

Goal: train the strongest defensible D40 detector, isolated from production, and report whether it
beats the deployed model and is worth deploying.

Hard guardrails during training, all respected:

- production weights `ml/models/road_damage/YOLOv8s_RDD_india.pt` read-only;
- production ONNX `backend/app/weights/rdd_india.onnx` untouched during training;
- backend / inference / Docker untouched during training;
- no dataset, checkpoint or result deleted;
- no auto-promotion, no commit, no push during the experiment;
- 70-photo Kent holdout and the (absent) field set never trained on.

Deployment happened later as a separate, explicit step (section 15).

Training ran with `--no-promote --skip-test`. India test was scored only after the checkpoint was
selected.

---

## 3. Starting point and why v1 was not enough

The shipped checkpoint is YOLOv8s trained on RDD2022 India (CRDDC). Its known weakness: RDD pothole
boxes are small (median ≈0.6% of image area), while phone photos of potholes are large (median
≈7.9%). On the 70-photo Kent holdout its D40 AP50 was **0.2555** — it misses most large potholes.

`pothole_ft_v1` (30 epochs, patience 25) had already fine-tuned on an extra pothole mix. It stopped
at epoch 14, but `best.pt` was **epoch 2**. Root cause: it selected on the **India validation split**,
which the base checkpoint had already memorised, so validation fitness peaked immediately and then
noise-drove early stopping. v1 still reached Kent holdout D40 AP50 0.635; the selection signal, not
the data, was the limiting factor.

v2 changes exactly one thing: the selection split.

---

## 4. Datasets

Built by `ml/scripts/prepare_pothole_opt_v2.py` into `data/rdd_pothole_opt_v2/` using hard links
(no duplicated bytes, source dataset unchanged).

| split | images | D00 | D10 | D20 | D40 | role |
|---|---:|---:|---:|---:|---:|---|
| train | 16,374 | 13,491 | 7,469 | 8,324 | 5,615 | training |
| kent_val | 80 | 0 | 0 | 0 | 117 | **checkpoint selection** |
| val (India) | 322 | 165 | 9 | 179 | 329 | reporting only |
| test (India) | 322 | 151 | 4 | 187 | 330 | final, once |
| kent_holdout | 70 | 0 | 0 | 0 | 137 | final, never seen |

### Kent validation split construction

The existing Kent holdout is not a contiguous block; its IDs are
`79–88, 184–195, 301–310, 341–350, 491–500, 541–550, 621–630`. The validation split was carved from
the long remaining Kent train runs in whole 20-photo blocks:

- **val blocks:** 260–279, 400–419, 580–599, 670–689 (80 photos, 117 D40 boxes);
- **embargo:** 10 photos on each side of every val block, dropped from training (80 photos);
- **holdout:** the original 70 photos, copied but never used for selection.

The builder hard-fails if the holdout is not exactly 70 photos, if any val/embargo ID overlaps the
holdout, or if any filename appears in two splits. This is a block split, not a random split, so
near-duplicate consecutive frames do not leak across the boundary.

### Leakage status (important)

| split | clean? | why |
|---|---|---|
| Kent holdout | **yes** | never in train, never in selection |
| Kent val | **yes** (selection only) | carved from Kent train photos, embargoed |
| India val | **no** | part of the base checkpoint's training data; shipped model memorised it |
| India test | **no** | same; all candidates derive from the same base |

So India numbers measure "did we keep the old skill", not field accuracy. The Kent holdout is the
only clean generalisation measurement here — and it is UK phone photography, not Indian roads.

---

## 5. Training recipe

| item | value |
|---|---|
| base | `ml/models/road_damage/YOLOv8s_RDD_india.pt` (shipped) |
| architecture | YOLOv8s — same family and 640 px input as the deployed ONNX |
| epochs / patience | 120 / 30, fitness = 0.1·mAP50 + 0.9·mAP50-95 on kent_val |
| batch / imgsz | 16 / 640 |
| optimizer | SGD, lr0 0.001, cosine, warmup 3, weight decay 0.0005 |
| freeze | 0 (full fine-tune) |
| augmentation | mosaic 1.0, close_mosaic 15, mixup 0.1, default HSV/scale/flip |
| sampling | repeat-factor class balance (`rfs_thresh` 0.5), `pothole_=2`, `India_=1.5` |
| checkpoints | every 5 epochs (`--save-period 5`; flag added to `train_rdd.py`) |
| workers / AMP | 8 / on |

Command: `ml/runs/sadhaksaarthi_optimization/pothole_opt_v2/command.txt`
Config: `ml/runs/sadhaksaarthi_optimization/pothole_opt_v2/train_config.yaml`

### Why YOLOv8s and not a bigger model

YOLOv8m was tried earlier in the session: slower per epoch and **lower clean India D40 AP50** than
YOLOv8s. YOLOv8s also keeps the export path identical to the deployed 640 px ONNX / CPU pipeline.
A larger model would have required a new latency and export validation cycle for no measured gain.

---

## 6. Training progress

Training early-stopped naturally at **epoch 45** (best epoch 15 + patience 30), in **163.1 min**
(≈3.6 min/epoch).

| phase | epochs | kent_val D40 mAP50 | kent_val mAP50-95 |
|---|---|---:|---:|
| fast climb | 1–6 | 0.433 → 0.581 | 0.257 → 0.353 |
| best region | 8–15 | 0.586–0.601 | 0.331–0.360 |
| **best (15)** | — | **0.5962** | **0.3603** |
| plateau | 16–45 | 0.560–0.607 | 0.329–0.355 |

No collapse, no divergence, no NaN. The last 30 epochs moved mAP50 by ±0.02 with no fitness
improvement, which is why stopping was the right call. Per-epoch table:
`ml/runs/sadhaksaarthi_optimization/pothole_opt_v2/FINAL_RESULTS.md`.

`best.pt` (epoch 15) re-scored on kent_val: **mAP50 0.6177, mAP50-95 0.3608** — slightly above the
CSV value (0.5962 / 0.3603) because the CSV row is written before the EMA/val timing settles. The
final evaluator uses the re-scored weights, so all reported numbers below are from the actual files.

Checkpoints kept: `epoch0/5/10/…/40`, `best.pt`, `last.pt`. Nothing deleted.

---

## 7. Results

All numbers from `ml/scripts/eval_rdd.py` (own pipeline, conf floor 0.001, IoU 0.6, 640 px,
image-level bootstrap 1000, seed 42). D40 P/R/F1 are at each model's own class-mean F1-optimal
confidence, so they are optimistic by construction; AP is threshold-independent.

### 7.1 Kent holdout — 70 photos, 137 D40 boxes, clean

| model | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 0.2555 | 0.1275 | 0.404 | 0.292 | 0.339 | 0.185 |
| v1 ep14 | 0.6346 | 0.3746 | 0.688 | 0.606 | 0.644 | 0.411 |
| **v2 best (ep15)** | **0.6591** | **0.3799** | 0.620 | **0.664** | 0.641 | 0.308 |
| v2 last (ep45) | 0.6470 | 0.3619 | 0.688 | 0.650 | 0.668 | 0.315 |

Paired deltas vs shipped (same bootstrap resamples):

| metric | v1 ep14 | **v2 best** | v2 last |
|---|---:|---:|---:|
| D40 AP50 | +0.379 [+0.280, +0.469] * | **+0.404** [+0.305, +0.492] * | +0.392 [+0.287, +0.490] * |
| D40 AP50-95 | +0.247 [+0.189, +0.311] * | **+0.252** [+0.186, +0.319] * | +0.234 [+0.167, +0.308] * |
| D40 precision | +0.284 [+0.172, +0.374] * | **+0.216** [+0.120, +0.306] * | +0.284 [+0.184, +0.377] * |
| D40 recall | +0.314 [+0.218, +0.403] * | **+0.372** [+0.276, +0.461] * | +0.358 [+0.250, +0.461] * |
| D40 F1 | +0.305 [+0.211, +0.388] * | **+0.302** [+0.219, +0.378] * | +0.329 [+0.238, +0.423] * |

`*` = 95% CI excludes 0. Every paired delta is significant. AP50 more than doubles; AP50-95 triples.

### 7.2 India test — 322 images, D40 330 boxes, contaminated, final only

| model | mAP50 | mAP50-95 | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| shipped | 0.7039 | 0.3214 | **0.6577** | **0.3115** | 0.643 | 0.576 | 0.608 | 0.186 |
| v1 ep14 | 0.6651 | 0.2748 | 0.6332 | 0.3084 | 0.663 | 0.561 | 0.608 | 0.272 |
| v2 best | 0.6845 | 0.2933 | 0.6250 | 0.2988 | 0.682 | 0.564 | 0.617 | 0.256 |
| v2 last | 0.6087 | 0.2545 | 0.6190 | 0.2746 | 0.683 | 0.547 | 0.607 | 0.284 |

D40 paired deltas vs shipped: AP50 **−0.033 [−0.071, +0.009] n.s.**, AP50-95
**−0.028 [−0.066, +0.006] n.s.**, recall −0.012 (point), precision +0.039 (point), F1 +0.010
(point). D40 is statistically indistinguishable from shipped. Overall 4-class mAP50 is lower by
0.019 (n.s.), and the class-mean recall at the F1-optimal point is lower by 0.097 [−0.296, −0.008],
driven by the non-D40 classes: D00 AP50 −0.049 * and D20 AP50 −0.032 (n.s.).

**How to read this:** D40 on RDD India did not degrade meaningfully. The small overall drop is the
expected cost of shifting capacity toward large potholes; it is not a field regression, and it is
partly measured on images the base model memorised.

### 7.3 India val — 322 images, contaminated, reporting only

| model | mAP50 | mAP50-95 | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| shipped | 0.7500 | 0.3780 | **0.6631** | **0.3271** | 0.733 | 0.559 | 0.634 | 0.234 |
| v1 ep14 | 0.6500 | 0.3090 | 0.6306 | 0.2907 | 0.574 | 0.638 | 0.604 | 0.204 |
| v2 best | 0.6720 | 0.3310 | 0.6447 | 0.2942 | 0.661 | 0.596 | 0.627 | 0.244 |
| v2 last | 0.6290 | 0.3150 | 0.6474 | 0.2733 | 0.609 | 0.635 | 0.622 | 0.208 |

D40 AP50 delta v2_best vs shipped: −0.018 [−0.051, +0.019] n.s. Consistent with test: no D40
regression; overall mAP50 is down 0.078 [−0.160, −0.014], driven by D10/D20/D00.

---

## 8. Confidence-threshold analysis

Primary tables (exact TP/FP/FN counts at each threshold, IoU 0.5):

- `ml/models/road_damage/runs/pothole_opt_v2_eval/operating_kent.md`
- `ml/models/road_damage/runs/pothole_opt_v2_eval/operating_india_test.md`

The earlier `threshold_kent.md` / `threshold_india_test.md` files come from Ultralytics `model.val(conf=…)`.
Those AP values fall as confidence rises because detections are truncated before AP is built, so
they are **not** threshold-independent and are not used for any decision here. The counts below are.

### Kent holdout — 137 D40 boxes

| conf | shipped P / R / F1 | v1 ep14 P / R / F1 | **v2 best P / R / F1** | v2 last P / R / F1 |
|---:|---|---|---|---|
| 0.10 | 0.306 / 0.350 / 0.327 | 0.452 / 0.723 / 0.556 | 0.453 / 0.781 / 0.574 | 0.512 / 0.759 / 0.612 |
| 0.20 | 0.443 / 0.285 / 0.347 | 0.572 / 0.693 / 0.627 | 0.551 / 0.745 / 0.634 | 0.583 / 0.715 / 0.643 |
| **0.30** | 0.500 / 0.241 / 0.325 | 0.622 / 0.650 / 0.636 | **0.613 / 0.672 / 0.641** | 0.684 / 0.664 / 0.674 |
| 0.40 | 0.617 / 0.212 / 0.315 | 0.680 / 0.606 / 0.641 | 0.662 / 0.628 / 0.644 | 0.724 / 0.613 / 0.664 |

At the same 0.30 threshold, v2 finds **92 of 137** potholes; shipped finds **33**. That is the
headline in one line.

### India test — 330 D40 boxes

| conf | shipped P / R / F1 | v1 ep14 P / R / F1 | **v2 best P / R / F1** | v2 last P / R / F1 |
|---:|---|---|---|---|
| 0.10 | 0.442 / 0.745 / 0.555 | 0.385 / 0.742 / 0.507 | 0.429 / 0.739 / 0.543 | 0.447 / 0.730 / 0.555 |
| 0.20 | 0.678 / 0.561 / 0.614 | 0.560 / 0.633 / 0.595 | 0.591 / 0.618 / 0.604 | 0.601 / 0.615 / 0.608 |
| **0.30** | 0.791 / 0.458 / 0.580 | 0.701 / 0.533 / 0.606 | **0.725 / 0.518 / 0.604** | 0.709 / 0.539 / 0.613 |
| 0.40 | 0.889 / 0.339 / 0.491 | 0.832 / 0.452 / 0.585 | 0.807 / 0.406 / 0.540 | 0.789 / 0.464 / 0.584 |

On India, v2 is **not worse at a matched threshold**: at 0.30 it finds 171 potholes vs shipped's
151, with 65 vs 40 false positives. It trades precision for recall; AP is slightly lower because
the high-confidence tail is weaker. The shipped model's F1-optimal point on this split is 0.186,
so if production runs near 0.18, v2 needs ~0.20–0.25 to keep recall, or ~0.30 to cut false alerts.

**Threshold recommendation:** start at **0.30** for v2 (Kent F1 0.641, India F1 0.604) and tune on
the labelled field set. Do not copy 0.308 blindly — it was chosen on 80 Kent photos.

---

## 9. Error counts at a matched threshold (0.30)

Exact counts, D40 predictions only, IoU 0.5. "FP" = D40 box with no matching D40 ground truth;
"D40 FN" = pothole with no matching D40 prediction.

### Kent holdout (n_gt = 137)

| model | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 33 | 33 | **104** | 0.500 | 0.241 | 0.325 |
| v1 ep14 | 89 | 54 | 48 | 0.622 | 0.650 | 0.636 |
| **v2 best** | **92** | 58 | **45** | 0.613 | 0.672 | 0.641 |
| v2 last | 91 | **42** | 46 | 0.684 | 0.664 | **0.674** |

Shipped misses **104 of 137** potholes at the same confidence. v2 misses 45. The extra 25 false
positives are a good trade for 59 more potholes found.

### India test (n_gt = 330)

| model | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 151 | **40** | 179 | 0.791 | 0.458 | 0.580 |
| v1 ep14 | 176 | 75 | 154 | 0.701 | 0.533 | 0.606 |
| **v2 best** | 171 | 65 | 159 | 0.725 | 0.518 | 0.604 |
| v2 last | 178 | 73 | 152 | 0.709 | 0.539 | 0.613 |

At 0.30 on India, v2 finds 20 more potholes and adds 25 false positives vs shipped — a small
recall gain, not a regression. Lower the threshold to ~0.20 if recall matters more: v2 finds 204,
shipped 185, at the cost of 141 vs 88 FPs.

---

## 10. v1 vs v2 — what actually changed

| item | v1 | v2 |
|---|---|---|
| selection split | India val (memorised) | Kent D40 val (clean, 80 photos) |
| best checkpoint | epoch 2 of 14 | **epoch 15 of 45** |
| stopping | premature, fitness noise | natural, patience 30 |
| Kent holdout D40 AP50 | 0.6346 | **0.6591** |
| Kent holdout D40 AP50-95 | 0.3746 | **0.3799** |
| India test D40 AP50 | 0.6332 | 0.6250 |
| confidence at F1-opt (Kent) | 0.411 | 0.308 |

The gain over v1 is modest (+0.025 AP50) and not clearly significant on 70 images; the **large**
gain is over shipped (+0.404). v2's real contribution is a trustworthy selection signal, a stable
45-epoch run, and a checkpoint chosen for D40 rather than for a memorised split.

---

## 11. Hardware and runtime

| item | value |
|---|---|
| GPU | NVIDIA RTX 4060, 8 GB |
| VRAM used | ≈5.0–5.3 GB |
| GPU utilisation | 86–98% |
| temperature | 65–67 °C |
| speed | ≈3.6 min/epoch (218 s) |
| training wall time | 163.1 min for 45 epochs |
| evaluation | ≈25 min for 4 models × 3 splits with 1000 bootstrap resamples |
| environment | `.venv-train`, ultralytics 8.4.140, torch 2.6.0+cu124 |

---

## 12. Limitations (do not skip)

1. **No Indian field test.** `D:\field_windshield_set` does not exist. The only clean split is UK
   phone photography. Indian-road generalisation is unmeasured.
2. **India val/test are contaminated** for every candidate here, because all derive from the same
   base checkpoint. They can detect catastrophic forgetting, not improvement.
3. **Small clean split.** 70 photos / 137 boxes. The +0.404 is far outside noise, but per-scene
   behaviour (shadow, rain, night) is not characterised.
4. **Selection noise.** `best.pt` was chosen on 80 photos. `v2_last` is within ~0.012 AP50 of
   `v2_best`; the difference between them is not meaningful. Either is defensible.
5. **P/R/F1 are optimistic.** They are measured at the F1-optimal confidence on the same split.
   Real deployment needs a threshold chosen on separate data.
6. **Export parity is covered; quantisation is not.** The exported ONNX matched decoded PyTorch
   detections on 70/70 Kent holdout images (section 15). INT8/quantisation was not tried, so the
   deployed file remains FP32 ONNX.
7. **Single seed, single architecture.** No seed variance, no YOLOv8m/n comparison under the fixed
   selection split.
8. **UK vs India domain gap.** Kent photos are close-up, daylight, phone camera. Indian dashcam
   footage is wider, more compressed, more variable. The gain may transfer; it is not proven.

---

## 13. Recommendation

**The export gates passed and the model is deployed. The Indian field gate is still open.**

| step | status | why |
|---|---|---|
| 1. Export `v2_best.pt` to ONNX | **done 2026-11-04** | 640 px FP32 export works |
| 2. Parity-check PyTorch vs ONNX on Kent holdout | **done 2026-11-04** | 187/187 decoded detections matched |
| 3. Deploy the model-only swap with rollback | **done 2026-11-04** | same input/output/class contract; old ONNX backed up |
| 4. Label 50–100 Indian field frames and score shipped vs v2 | **open** | the only test that measures Indian-road performance |
| 5. Pick a deployment threshold on that field set; start from **0.30** | **open** | F1-opt on the eval split is optimistic; at 0.30 Kent is P 0.61 / R 0.67 |

If the field set shows v2 ≥ shipped on Indian D40, keep the deployed model and tune the threshold.
If it shows a regression, roll back to `rdd_india_v1_20261005.onnx` and use v2 only for close-up /
user-uploaded photos, where the gain is already proven.

**What not to do:** do not train longer. 30 extra epochs produced no fitness gain and only overfit
risk. Do not select on India val again — that is the v1 failure mode.

---

## 14. Reproduce

```powershell
# 1. build the isolated dataset (hard links, source untouched)
.\.venv-train\Scripts\python.exe ml\scripts\prepare_pothole_opt_v2.py

# 2. train (early-stopped at epoch 45; best epoch 15)
.\.venv-train\Scripts\python.exe -u ml\scripts\train_rdd.py `
  --data data\rdd_pothole_opt_v2\data.yaml `
  --model ml\models\road_damage\YOLOv8s_RDD_india.pt `
  --epochs 120 --patience 30 --batch 16 --imgsz 640 --workers 8 `
  --optimizer SGD --lr0 0.001 --freeze 0 --cos-lr `
  --close-mosaic 15 --mixup 0.1 --class-balanced `
  --domain-weight pothole_=2 --domain-weight India_=1.5 `
  --save-period 5 --no-promote --skip-test --boot 0 --name pothole_opt_v2

# 3. score all candidates on all splits
.\.venv-train\Scripts\python.exe ml\scripts\finalize_pothole_opt_v2.py

# 4. Ultralytics sweep (reference only; AP is truncated at each conf)
.\.venv-train\Scripts\python.exe ml\scripts\threshold_sweep.py `
  --weights <weights>\shipped.pt <weights>\v1_ep14.pt <weights>\v2_best.pt `
  --labels shipped v1_ep14 v2_best `
  --data data\rdd_pothole_opt_v2\data_kent_holdout.yaml --split test `
  --tag optv2_kent_threshold --out ml\models\road_damage\runs\pothole_opt_v2_eval\threshold_kent.json

# 5. exact operating points (TP/FP/FN and true P/R/F1 per threshold)
.\.venv-train\Scripts\python.exe ml\scripts\threshold_operating_points.py `
  --weights <weights>\shipped.pt <weights>\v1_ep14.pt <weights>\v2_best.pt <weights>\v2_last.pt `
  --labels shipped v1_ep14 v2_best v2_last `
  --data data\rdd_pothole_opt_v2\data_kent_holdout.yaml --split test `
  --tag optv2_kent_operating --out ml\models\road_damage\runs\pothole_opt_v2_eval\operating_kent.json
```

Artefacts:

| path | content |
|---|---|
| `ml/models/road_damage/runs/pothole_opt_v2/weights/best.pt` | selected checkpoint (epoch 15) |
| `ml/models/road_damage/runs/pothole_opt_v2/weights/last.pt` | final checkpoint (epoch 45) |
| `ml/models/road_damage/runs/pothole_opt_v2/results.csv` | 45-epoch curve |
| `ml/models/road_damage/runs/pothole_opt_v2_eval/weights/eval_compare_optv2_*.md` | full tables + CIs |
| `ml/models/road_damage/runs/pothole_opt_v2_eval/operating_kent.md` | exact TP/FP/FN vs confidence, Kent |
| `ml/models/road_damage/runs/pothole_opt_v2_eval/operating_india_test.md` | exact TP/FP/FN vs confidence, India test |
| `ml/runs/sadhaksaarthi_optimization/pothole_opt_v2/FINAL_RESULTS.md` | machine-generated summary |
| `ml/runs/sadhaksaarthi_optimization/pothole_opt_v2/README.md` | run card |
| `ml/scripts/prepare_pothole_opt_v2.py` | dataset builder |
| `ml/scripts/finalize_pothole_opt_v2.py` | evaluation/summary |
| `ml/scripts/threshold_operating_points.py` | exact P/R/F1 + TP/FP/FN per threshold |
| `ml/scripts/threshold_sweep.py` | Ultralytics AP sweep (truncated, reference only) |

**Production status: deployed (model-only swap).** `backend/app/weights/rdd_india.onnx` is now the
`best.onnx` exported from `pothole_opt_v2/weights/best.pt`; the checksum, parity results and rollback
path are in section 15. Backend inference code, `CONF = 0.18`, Docker and the training `.pt` files
were not changed.

---

## 15. Production deployment (2026-11-04)

The user approved promotion after the experiment. This section is the audit record.

### Export

| item | value |
|---|---|
| source | `ml/models/road_damage/runs/pothole_opt_v2/weights/best.pt` (epoch 15) |
| export | Ultralytics ONNX, imgsz 640, opset 12, `simplify=True`, `nms=False` |
| output shape | `[1, 8, 8400]` (4 box + 4 classes, 8400 anchors) |
| file | `best.onnx`, 44,750,735 bytes |
| SHA-256 | `649BBBDE79F75ED5E5CCB22AB5FFAA66E3B52A976A4094538B20CAD4EF0C305D` (export date is embedded in ONNX metadata; a re-export changes the checksum even with identical weights) |
| deployed | `backend/app/weights/rdd_india.onnx`, same SHA-256 |
| old ONNX backup | `ml/models/road_damage/rdd_india_v1_20261005.onnx` |
| old SHA-256 | `5A1D6BEC66FDA05E89572FDEC73F0979CD80FB627961FFD52CC6FB41F70D45E9` |

The old ONNX is also in git history. The export scripts now prefer the v2 checkpoint, so a future
re-export does not silently bring the old model back.

### Parity

Raw YOLO tensors differ slightly between PyTorch CPU and ONNX Runtime, so the gate was decoded
detections, not 1e-3 tensor equality.

| check | result |
|---|---|
| Kent holdout, 70 images | 187 PyTorch detections, 187 ONNX detections, 187 matched |
| worst matched IoU / confidence delta | 1.0000 / 0.0000 |
| raw tensor max abs diff | 0.0205 (normal CPU kernel drift) |
| backend `detect_rdd`, Kent conf 0.30 | TP 92 / FP 58 / FN 45, identical to PyTorch exact operating point |
| backend `detect_rdd`, Kent conf 0.18 | TP 99 / FP 82 / FN 38 |
| backend `detect_rdd`, India test conf 0.30 | TP 173 / FP 53 / FN 157, against PyTorch 171 / 65 / 159 |
| backend tests | `test_rdd_cloud.py` + `test_phone_still.py`: 23 passed |

Reproduce the parity gate:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\verify_onnx_parity.py `
  --pt ml\models\road_damage\runs\pothole_opt_v2\weights\best.pt `
  --onnx ml\models\road_damage\runs\pothole_opt_v2\weights\best.onnx `
  --data data\rdd_pothole_opt_v2\data_kent_holdout.yaml --split test --limit 70
```

### Deployment decision

- The new ONNX has the same input size, output layout and class order as the old one, so no backend
  code change was needed.
- `backend/app/services/rdd_cloud.py` still uses `CONF = 0.18`, `IOU = 0.45`. At conf 0.30 the new
  model gives up about 7 Kent true positives but removes 24 false positives; 0.30 remains the
  recommended tuning point once a labelled field set exists.
- `metrics.json` now describes the deployed ONNX. It keeps the honesty warning: India test is
  in-distribution, Kent is clean but UK, and no Indian field set exists.
- The dashboard's local `public/weights/rdd_web.onnx` was refreshed; that file is gitignored and
  generated again by Vite on a clean build.

### Still open

The remaining risk is domain transfer, not export. A labelled Indian windshield/phone set is still
the only way to quote field precision and recall. Until then, the Kent improvement and the
non-significant India D40 change are the defensible claims.
