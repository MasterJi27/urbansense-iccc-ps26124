Deployment RDD weight (TRACKED in git).

- `rdd_india.onnx` - YOLOv8s, 640 px, ONNX CPU, no NMS. Exported from the selected
  `pothole_opt_v2` checkpoint (epoch 15), not from the older India fine-tune.
- SHA-256: `649BBBDE79F75ED5E5CCB22AB5FFAA66E3B52A976A4094538B20CAD4EF0C305D`
  (44,750,735 bytes)
- Source checkpoint (local only, not in git):
  `ml/models/road_damage/runs/pothole_opt_v2/weights/best.pt`
- Used by `backend/app/services/rdd_cloud.py` for official stills
  (`POST /ingest/phone`). `/health` reports `rdd: REAL` when present.
- Vite copies this file to `dashboard/public/weights/rdd_web.onnx` at
  `npm run dev` / `npm run build` for the `/field` windshield preview.
  The dashboard copy is gitignored; only this file + `manifest.json` are tracked.

## Measured quality (not field accuracy)

| split | model | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---|---:|---:|---:|---:|---:|---:|
| Kent holdout, 70 photos | shipped | 0.2555 | 0.1275 | 0.404 | 0.292 | 0.339 | 0.185 |
| Kent holdout, 70 photos | **deployed v2** | **0.6591** | **0.3799** | **0.620** | **0.664** | **0.641** | **0.308** |
| India test, 322 images | shipped | 0.6577 | 0.3115 | 0.643 | 0.576 | 0.608 | 0.186 |
| India test, 322 images | **deployed v2** | 0.6250 | 0.2988 | 0.682 | 0.564 | 0.617 | 0.256 |

The Kent holdout is clean but is UK phone photography, not Indian roads. India val/test
overlap the base checkpoint's training data for both models, so they are in-distribution
benchmarks. There is still no labelled Indian field set. Do not quote these as field accuracy.

## Production parity (2026-11-04)

- PyTorch `best.pt` vs exported ONNX: decoded detections matched exactly on all 70 Kent
  holdout images (187/187 detections, worst matched IoU 1.0000, confidence delta 0.0000;
  raw tensor max abs diff 0.0205, normal for CPU kernels).
- Backend `detect_rdd` on Kent at conf 0.30: TP 92 / FP 58 / FN 45, identical to the
  PyTorch exact operating point. At the deployed conf 0.18: TP 99 / FP 82 / FN 38.
- Backend `detect_rdd` on India test at conf 0.30: TP 173 / FP 53 / FN 157, against
  PyTorch TP 171 / FP 65 / FN 159. The small difference is the production decode/NMS path.
- `backend/tests/test_rdd_cloud.py` and `test_phone_still.py`: 23 passed.

`rdd_cloud.py` keeps `CONF = 0.18` for this model-only swap. At conf 0.30 the new model
trades about 7 Kent true positives for 24 fewer false positives; tune on a labelled field
set before changing the production constant.

## Rollback

The previous ONNX is kept locally at
`ml/models/road_damage/rdd_india_v1_20261005.onnx` (SHA-256
`5A1D6BEC66FDA05E89572FDEC73F0979CD80FB627961FFD52CC6FB41F70D45E9`). The old file is
also in git history. To roll back, copy the backup over `rdd_india.onnx`, then restart
the App Service.

## Re-export (training host only)

The SHA-256 above is for this committed file. Ultralytics embeds an export date in the ONNX
metadata, so a re-export changes the checksum even when the graph weights are unchanged. Use the
parity check below, not the checksum alone, to decide whether a re-export is equivalent.

```text
.\.venv-train\Scripts\python.exe ml\scripts\export_rdd_onnx.py
.\.venv-train\Scripts\python.exe ml\scripts\verify_onnx_parity.py ^
  --pt ml\models\road_damage\runs\pothole_opt_v2\weights\best.pt ^
  --onnx ml\models\road_damage\runs\pothole_opt_v2\weights\best.onnx ^
  --data data\rdd_pothole_opt_v2\data_kent_holdout.yaml --split test --limit 70
.\.venv-train\Scripts\python.exe ml\scripts\export_field_onnx.py
```

Do NOT commit `ml/models/road_damage/*.pt`, `ml/models/road_damage/runs/`,
root `yolov8*.pt`, or `weights/yolo26*` - those are training waste.
