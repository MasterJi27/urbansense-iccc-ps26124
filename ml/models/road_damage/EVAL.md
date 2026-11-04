# Honest evaluation of the road-damage detector

Everything below runs on the Windows RTX box (`.venv-train`), from the repo root. Nothing here
was run on the Mac that wrote it: there is no torch there. The scripts were checked there with
`py_compile`, a numpy-only self-test, a parity test against the Ultralytics 8.4.182 metric code,
and stubbed end-to-end runs. No model was loaded and no GPU was used.

## Why the shipped 0.6244 is optimistic

- The base checkpoint (`YOLOv8_Small_RDD.pt`, oracl4) was **already trained on RDD2022 Japan and
  India**. India val/test are not unseen for it, nor for anything fine-tuned from it.
- The India split is a per-image random shuffle (seed 42). Neighbouring frames of one drive land
  in train and test, so test images have near-duplicates in train.
- The old `train_rdd.py` promoted weights by comparing **test** mAP with the previous test mAP, so
  test was a selection set, not a held-out one.
- 323 test images: mAP50 has a 95% CI of several points. Differences under about 0.03 are noise;
  `eval_rdd.py` prints the real width.
- Val/test only contain images with at least one D00/D10/D20/D40 box. Clean-road images were
  left out, so false positives on empty road are not measured by any India number.
- D10 train files were duplicated 10x (`d10_train_repeat: 10`), which hides how rare D10 is.

None of this is fixed by re-running the same split. A clean number needs data nobody trained on:
the field set below.

## 0. Check the tooling (no GPU, seconds)

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --selftest
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --data data\rdd_india\data.yaml --split test --dry-run
```

`--dry-run` resolves the yaml, rewrites `path:` to the real folder (a `*.runtime.yaml` copy
beside it; the original is untouched) and counts images and label files.

## 1. Base vs shipped on the current India test split

First weights file is the reference. This gives the table and **paired** CIs for the difference.

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --weights ml\models\road_damage\YOLOv8_Small_RDD.pt ml\models\road_damage\YOLOv8s_RDD_india.pt --labels base tuned --data data\rdd_india\data.yaml --split test --boot 1000
```

Writes, next to the weights: `YOLOv8_Small_RDD_eval_test.json`, `YOLOv8s_RDD_india_eval_test.json`,
`eval_compare_test.json` and `eval_compare_test.md` (the table, ready to paste here).

| metric | base | tuned | Δ tuned − base |
|---|---|---|---|
| mAP50, mAP50-95, AP50 D00/D10/D20/D40, P/R/F1 at F1-optimal conf | not run yet | not run yet | not run yet |

For reference only, `metrics.json` currently records tuned = 0.6244 mAP50 / 0.3196 mAP50-95 on this
split, measured with the old protocol.

How to read it:

- `*` on a delta means its CI excludes 0. `n.s.` means the fine-tune is not distinguishable from
  the base on these images.
- Both columns are inflated: the base was pre-trained on India, and the tuned model also trained on
  neighbours of these test frames. The delta is therefore not a clean measure of what the
  fine-tune added, and neither column is a field estimate.
- P/R/F1 use each model's own F1-optimal confidence **picked on this same split**, so they are
  optimistic. Fix the deployed threshold on val, then report it on test.
- `model.val()` and the script's own pipeline are both printed. They should agree within about
  0.01 mAP50; the script warns otherwise. The CI comes from the own pipeline, because the
  bootstrap needs per-image detections that `model.val()` does not expose.

## 2. A split that cannot leak neighbouring frames

First check that neighbouring filename ids really are neighbouring frames:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_india.py --skip-download --skip-extract --audit-neighbours
```

If it says they are, build the new dataset. This writes `data\rdd_india_grouped` and never
touches `data\rdd_india`:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_india.py --skip-download --skip-extract --split-by-group --group-size 30 --embargo 2
```

Whole blocks of 30 consecutive ids go to one split, and images within 2 ids of a val/test image are
dropped from train (and val images near test), so block edges leak nothing. Counts, class
instances and the settings land in `split_info.json`. Image files are hard-linked, add `--copy`
to copy.

Do **not** score the shipped `YOLOv8s_RDD_india.pt` on the grouped test as a clean number: it was
trained on the old random train split, which overlaps the new test. Only models trained on the
grouped train split get a fair grouped-test score, and even those inherit the base checkpoint's
India exposure.

### Result on the RTX box (2026-10-18): ids are shuffled, split by look-alike instead

The audit said no: id-neighbours have a dHash median distance of 27 against 25 for random pairs.
RDD2022 India ids carry no drive order, so `--split-by-group` removes nothing. The random split
still leaks, though: of the closest val/test-to-train pairs (32x32 grey thumbnail cosine ≥ 0.98),
most are the same spot of the same drive a few frames apart. Around 0.95 some pairs are still the
same spot; at 0.93 they are different places. So:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_india.py --skip-download --skip-extract --split-by-similarity
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_hf.py --india-dir data\rdd_india_simsplit --mix-dir data\rdd_simsplit_mix
```

Images with cosine ≥ `--sim-thresh` (0.95) are linked, connected components stay in one split,
components above 2% of the images go to train (one, 386 images), and test then val are filled to
10% each. Result: train 2579 / val 322 / test 322, and the largest val→train, test→train and
test→val cosine is below 0.95 by construction (`split_info.json` records it). Test holds only 4
D10 boxes, so its D10 AP is noise. The mix adds the 13362 Japan/US/Czech/China MotorBike
images to train; val/test stay India only.

The base checkpoint saw all of these images, and the shipped weights trained on the old random
split, so neither gets a clean score here. Only a model that starts from COCO weights does.

## 3. Field set (the only clean test)

Hand-label phone/bus-windshield frames in YOLO format and keep them out of every training run.
Layout: `<dir>\images\*.jpg` + `<dir>\labels\*.txt` (or both in one flat folder). Class ids
0-3 = D00 D10 D20 D40, normalised `class xc yc w h`. Write an **empty** `.txt` for clean-road
images (they measure false positives); a missing label file is refused unless you pass
`--field-missing-as-background`. Label on the image as displayed (EXIF rotation applied).
More images means a narrower CI; the script warns when a class has under 30 instances.

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_india.py --skip-download --skip-extract --split-by-group --field-test-dir D:\field_windshield_set
```

This adds `images\field` + `labels\field` and `data_field.yaml` (same train/val, but
`test: images/field`). It refuses a field image that is byte-identical to any India image. Score any
weights on it:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --weights ml\models\road_damage\YOLOv8_Small_RDD.pt ml\models\road_damage\YOLOv8s_RDD_india.pt --labels base tuned --data data\rdd_india_grouped\data_field.yaml --split test --tag field
```

This writes `*_eval_field.json` and `eval_compare_field.md`, so the India results above are not overwritten. Both models are valid here: neither trained on the field set. Run this before anything else if
you have the labels, it is the number to quote.

## 4. Training with the new gate

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\train_rdd.py --data data\rdd_india_grouped\data.yaml --epochs 25 --lr0 0.0001 --freeze 10 --class-balanced --field-data data\rdd_india_grouped\data_field.yaml --name grouped_v1
```

- Promotion is decided on **val**: candidate val mAP50 must reach the shipped weights' val mAP50,
  re-measured on the same val images, plus `--promote-margin` (default 0). Val is also what
  Ultralytics uses to pick `best.pt` and stop early, so it is a selection set too. A margin of
  about the CI half-width stops noise from promoting.
- **Test is evaluated once**, on the promoted weights, after the decision. A rejected candidate is
  never scored on test; it writes `ml\models\road_damage\runs\<name>_gate.json` instead.
  `--skip-test` keeps the run off test entirely; `metrics.json` then says it is val-only.
- `--field-data` scores the promoted weights once on the field set, stored as `field_test`.
- `metrics.json` keeps its old keys (`map50`, `map50_95`, per-class `map50`) and gains `ci95`,
  `operating_point`, `promotion`, `field_test` and `split.mode`. Its note now says the base
  checkpoint saw India.
- `--class-balanced` replaces D10 file duplication with repeat-factor sampling in the train
  loader (rare classes drawn more often, no copies on disk; `--rfs-thresh` sets the strength).
  D10 duplication is off in `prepare_rdd_india.py` by default (`--d10-repeat 10` reproduces the old
  build). `--class-balanced` could not be run on the Mac; check for the "[class-balanced]" line it
  prints at start-up.

### 4b. From COCO on the look-alike split (the first clean India number)

Every fine-tune from the base peaked at epoch 1-3 on India val and then fell: the base had already
seen val, so moving away from it only loses memorised images. Training from COCO weights on the
section 2 split avoids that:

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\train_rdd.py --data data\rdd_simsplit_mix\data.yaml --model yolov8m.pt --epochs 120 --batch 16 --workers 8 --optimizer SGD --lr0 0.01 --freeze 0 --cos-lr --close-mosaic 15 --patience 40 --class-balanced --domain-weight India_=2 --mixup 0.1 --name simsplit_v8m_coco --no-promote
```

- `--no-promote` skips the gate (comparing a clean model against the base's memorised val score
  means nothing), scores the candidate on val and once on test with CIs, and writes
  `runs\<name>_candidate.json`. Shipped weights and `metrics.json` are not touched; shipping is a
  separate step.
- `--domain-weight India_=2` draws India images twice as often (30% of draws instead of 16%);
  with `--class-balanced` potholes go from 17% to 29% of drawn images.
- `train_rdd.py` now sets `channels_last=False`. Ultralytics 8.4 turns it on by default on CUDA,
  and on this RTX 4060 (torch 2.6 cu124) it made YOLOv8m forward+backward 3.7x slower (12 vs 46
  img/s). With it off, an epoch of the mix takes about 7 minutes.
- `--workers` defaults to 2 as before; 8 keeps the 6-core Ryzen ahead of the GPU.

**Result (2026-10-19, `simsplit_v8m_coco`).** Early stopping ended the run at epoch 78 of 120 (best epoch 38,
8.7 h). `best.pt` on the similarity split, `model.val()` headline, bootstrap CI over images from the own pipeline:

| split | n | mAP50 | mAP50-95 | AP50 D00 / D10 / D20 / D40 |
|---|---|---|---|---|
| val (picked `best.pt`, a selection set) | 322 | 0.448 [0.37, 0.53] | 0.195 | 0.41 / 0.18 / 0.71 / 0.49 |
| test (scored once) | 322 | 0.443 [0.36, 0.55] | 0.177 | 0.48 / 0.17 / 0.61 / 0.51 |

- The own pipeline reads 0.03-0.04 lower than `model.val()` (the script warns above 0.01 and says to trust
  `model.val()` for the headline). The CI half-width is about 0.1, so the gap is inside the noise.
- Test has 4 D10 boxes and val 9: the D10 numbers mean nothing.
- Same test, own pipeline: new 0.411, shipped `YOLOv8s_RDD_india.pt` 0.704, base `YOLOv8_Small_RDD.pt` 0.718. That
  is not a contest. The base saw every India image and the shipped model trained on a random split that overlaps this
  test. The 0.3 gap is roughly how much memorised frames were worth. It does not show the shipped model is better in
  the field either. Only a labelled windshield set can say that (section 3).
- Not shipped. A clean 0.44 is not evidence of beating the shipped weights, and YOLOv8m is about 2.7x the compute of
  YOLOv8s on the Azure CPU. `metrics.json` and `YOLOv8s_RDD_india.pt` were not touched (`--no-promote`).
- The in-run scoring ran out of GPU memory right after training, before any test image was scored. Rerun it in a fresh
  process: `train_rdd.py --data data\rdd_simsplit_mix\data.yaml --model <best.pt> --eval-only --no-promote --name <run>`.
  Correction (2026-10-19): a fresh process is not enough on its own. For the India fine-tune's `best.pt` val scored and
  the test split then ran out of memory in the fresh process too. PyTorch's allocator grows across evaluations (NMS at
  conf=0.001 asks for ~3 GB blocks; Windows shared GPU memory lets it pass 16 GB before failing). `report_candidate`
  now frees memory between splits. If it still fails, score each split in its own process:
  `eval_rdd.py --weights <best.pt> --data <yaml> --split val` and then `--split test`. The fix was checked on that same
  `best.pt`: val and test both scored without running out of memory.
- India-only fine-tune (`simsplit_v8m_india_ft`): run 1's `best.pt` as the start, India train only (2579 images),
  SGD lr0 0.002, freeze 10, `--class-balanced`. Early stopping ended it at epoch 13, best epoch 1. Val 0.450, test
  0.421 [0.36, 0.56] against run 1's 0.448 / 0.443: no gain. Val fell from 0.452 at epoch 1 to about 0.40-0.42 while the
  training loss kept dropping, so it memorises the 2.6k Indian training images. Not shipped.

### 4c. Pothole photos the RDD data lacks (2026-10-20, data prepared, not trained)

The deployed model finds 58% of the labelled India test potholes at conf 0.18 (precision 68%; this is the best case, it saw
those images), and on a clear close-up water-filled pothole it answers "alligator crack" 0.44 with a pothole score of 0.06.
Shrinking the same photo raised the pothole score (0.06, 0.12, 0.18, 0.26 at 100%, 70%, 50%, 35% size). The cause is the
training data: an RDD2022 pothole box covers a median **0.6%** of the image (4,945 boxes in the clean train split), the
University of Kent photos **7.9%**. It was not the decode: class-agnostic against per-class NMS found 146 against 145 potholes.

`prepare_pothole_extra.py` adds those photos to a copy of the mix (`data/rdd_simsplit_pothole_mix`, the base mix is not changed):

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\prepare_pothole_extra.py --src kent=data\pothole_kent\raw --dry-run
.\.venv-train\Scripts\python.exe ml\scripts\prepare_pothole_extra.py --src kent=data\pothole_kent\raw
```

- Kent (CC BY 4.0, UK roads): 713 photos, 50 exact duplicates dropped, 4 broken boxes (outside the image) dropped, leaving
  663 photos: 593 in train (933 boxes) and 70 in `data_kent_holdout.yaml` (137 boxes, blocks of 10 consecutive photos, never
  trained on). All map to D40. No photo equals a val or test image (checked by hash).
- The holdout checks that the model learned this kind of photo. It is UK photos, so it is not field evidence; only your own
  labelled phone photos (section 3) say how it does on Indian roads.
- These photos label potholes only, so cracks in them count as background. Keep the RDD images in training and watch D00/D10/D20
  on the same test before and after (paired), or the model may learn to ignore cracks.
- Run `pothole_ft_v1` (2026-10-20): from `YOLOv8s_RDD_india.pt` (not the default `--model`, which is the oracl4 base), `--data data\rdd_simsplit_pothole_mix\data.yaml
  --domain-weight pothole_=2 --class-balanced --lr0 0.002 --freeze 10 --epochs 30 --batch 16 --workers 8 --cos-lr --close-mosaic 5
  --patience 12 --no-promote`. Early stopping watches India val, which the shipped model has memorised, so val fell from epoch 1 and
  the run stopped at epoch 14 (33 min). `best.pt` is therefore epoch 1, barely trained on the new photos; `last.pt` is epoch 14. Score
  `last.pt`, not `best.pt`. Only these two were saved.
- Result, paired bootstrap over images (`eval_compare_pothole_kent.md`, `eval_compare_pothole_india.md`):

  | split | model | AP50 D40 | mAP50 |
  |---|---|---|---|
  | Kent holdout, 70 photos never trained on | shipped | 0.256 [0.16, 0.37] | |
  | | epoch 1 | 0.525 [0.40, 0.64] | |
  | | epoch 14 | **0.635** [0.51, 0.75] (+0.379, CI excludes 0) | |
  | India test (the shipped model has seen it) | shipped | 0.658 | 0.704 |
  | | epoch 14 | 0.633 (-0.025, n.s.) | 0.665 (-0.039, n.s.) |

  D00 -0.011 and D20 -0.014 on the India test are also inside the noise (D10 has 4 boxes). mAP50-95 fell by 0.047 (CI excludes 0): its
  boxes are a little looser. The close-up photo `pothole_big.jpg` (not byte-identical to any Kent photo) went from "D20 0.67" to "D40 0.52".
- Read it carefully: the Kent holdout is the same dataset and country as the training photos, blocks of consecutive photos may still look
  like a training neighbour, so +0.38 is a best case. The India drop is measured against a model that memorised those images. Neither is
  a field number. `last.pt` also wants a higher confidence (F1-optimal 0.27 on India test, 0.41 on Kent, against 0.19 for the shipped
  model), so the deployed 0.18 would raise false alarms. Pick the new threshold on val, not test.
- Not shipped. Next: export `last.pt` to ONNX, run it through the backend decode, choose the threshold on val, then score the field set.

## 5. `copy_paste` does nothing here

`train_rdd.py` passes `copy_paste=0.2`. Ultralytics' `CopyPaste` pastes instance **masks**, and its
`__call__` returns the labels untouched when `len(labels["instances"].segments) == 0 or self.p == 0`
(`ultralytics/data/augment.py`, checked in 8.4.182). RDD labels are boxes only, so `segments`
is always empty and the transform never fires. The value is just recorded in `args.yaml`.
Treat it as off: do not credit it for any result and do not tune it. Check on your install:

```powershell
.\.venv-train\Scripts\python.exe -c "import inspect, ultralytics.data.augment as a; print(inspect.getsource(a.CopyPaste.__call__))"
```

## 6. `pothole_opt_v2` — selection on a clean Kent split (2026-11-02)

v1 failed because it selected on India val, which the base checkpoint had memorised (`best.pt` was
epoch 2 of 14). v2 keeps the same data but carves an 80-photo D40 validation split out of the Kent
training photos in whole 20-photo blocks, with a 10-photo embargo, and selects on that.

| model | Kent holdout D40 AP50 | India test D40 AP50 | India val D40 AP50 |
|---|---:|---:|---:|
| shipped | 0.256 [0.16, 0.37] | 0.658 [0.60, 0.71] | 0.663 [0.61, 0.72] |
| v1 epoch 14 | 0.635 [0.51, 0.75] | 0.633 [0.57, 0.69] | 0.631 [0.57, 0.69] |
| **v2 best (epoch 15)** | **0.659 [0.53, 0.77]** | 0.625 [0.57, 0.69] | 0.645 [0.59, 0.71] |
| v2 last (epoch 45) | 0.647 [0.52, 0.76] | 0.619 [0.56, 0.69] | 0.647 [0.59, 0.71] |

v2 vs shipped, paired bootstrap: Kent D40 AP50 **+0.404 [+0.305, +0.492]**; India test D40 AP50
−0.033 [−0.071, +0.009] (n.s.). Training early-stopped at epoch 45 (best 15 + patience 30), 163 min
on an RTX 4060. Exported and deployed as a model-only ONNX swap on 2026-11-04 after 70/70 decoded
detections matched PyTorch; backend tests passed. Threshold stayed at 0.18, and there is still no
labelled Indian field set. See `docs/MODEL_OPTIMIZATION_REPORT.md` section 15.

Full report: `docs/MODEL_OPTIMIZATION_REPORT.md`.

## Known gaps

- `prepare_rdd_hf.py --india-dir` mixes the extras into any India split, so a candidate on the
  look-alike split trains on the same 16k-image mix as the shipped model.
- Grouping by filename id does not hold for RDD2022 India (ids are shuffled, see section 2). The
  look-alike split is a proxy too: two frames of one road that look different enough (< 0.95)
  can still sit in train and test.
- Val and test hold only images with boxes (clean-road images were never written). Only the
  field set, with empty labels for clean road, measures false positives on empty road.
