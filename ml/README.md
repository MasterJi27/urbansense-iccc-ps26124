# ml: road-damage model

Training, evaluation and export for the road-damage detector (RDD2022 classes D00, D10, D20, D40).
Datasets live in `../data` (see `../data/README.md`). Weights and results live in `models/`.

```
ml/
  scripts/   prepare_rdd_india.py  prepare_rdd_hf.py  prepare_pothole_extra.py  train_rdd.py  eval_rdd.py
             export_rdd_onnx.py    export_field_onnx.py  watch_training.py
  models/    base/ (COCO yolov8m.pt)   road_damage/ (weights, metrics.json, EVAL.md, runs/)   anpr/  traffic/  traffic_sign/
```

Run everything from the repo root with the training environment (`.venv-train`, torch + ultralytics, CUDA).

## Where things stand (2026-11-04)

- The model in the app is `pothole_opt_v2` best (epoch 15), exported to
  `backend/app/weights/rdd_india.onnx`. On the clean 70-photo Kent holdout its D40 AP50 is **0.6591**
  against **0.2555** for the previous model. India test D40 AP50 is 0.6250 against 0.6577 (n.s.);
  both models saw the base checkpoint's India training data, so that column is not field accuracy.
- Kent is UK phone photography. The next real step is still a labelled set of your own Indian
  windshield photos (`EVAL.md` section 3).
- Export/parity/deployment details and the remaining caveats are in
  `docs/MODEL_OPTIMIZATION_REPORT.md` section 15. Full experiment tables are in
  `models/road_damage/EVAL.md`.

## Commands

```powershell
# 1. clean split: look-alike images stay together (the random split leaks)
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_india.py --skip-download --skip-extract --split-by-similarity
# 2. add the Japan / US / Czech / China images to train (val and test stay India only)
.\.venv-train\Scripts\python.exe ml\scripts\prepare_rdd_hf.py --india-dir data\rdd_india_simsplit --mix-dir data\rdd_simsplit_mix
# 2b. optional: add public pothole photos (big, close-up, water-filled ones the RDD data lacks). See EVAL.md section 4c
.\.venv-train\Scripts\python.exe ml\scripts\prepare_pothole_extra.py --src kent=data\pothole_kent\raw
# 3. train (about 7 min per epoch on an RTX 4060). --no-promote never touches the shipped weights
.\.venv-train\Scripts\python.exe ml\scripts\train_rdd.py --data data\rdd_simsplit_mix\data.yaml --model ml\models\base\yolov8m.pt --epochs 120 --batch 16 --workers 8 --optimizer SGD --lr0 0.01 --freeze 0 --cos-lr --close-mosaic 15 --patience 40 --class-balanced --domain-weight India_=2 --mixup 0.1 --name my_run --no-promote
# live view while it runs
.\.venv-train\Scripts\python.exe ml\scripts\watch_training.py --name my_run --epochs 120 --patience 40
# 4. score weights, with confidence intervals, on the same test split
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --weights ml\models\road_damage\YOLOv8s_RDD_india.pt --data data\rdd_simsplit_mix\data.yaml --split test
# check the tooling in seconds, no GPU
.\.venv-train\Scripts\python.exe ml\scripts\eval_rdd.py --selftest
```

Notes:

- `channels_last` is switched off in `train_rdd.py`. On the RTX 4060 box it made YOLOv8m about 3.7x slower.
- Scoring can run out of GPU memory (NMS at conf 0.001 asks for blocks of about 3 GB). `train_rdd.py` frees memory
  between splits. If it still fails, score each split in its own process with `eval_rdd.py --split val`, then `--split test`.
- To ship a model: export with `export_rdd_onnx.py`, run `verify_onnx_parity.py` against the clean
  split, and only then replace `backend/app/weights/rdd_india.onnx`. The export scripts prefer the
  `pothole_opt_v2` checkpoint.
