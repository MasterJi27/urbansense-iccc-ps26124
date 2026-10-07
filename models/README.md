Deploy vs train weights — read this on a fresh clone.

RUN (no training needed):
- `backend/app/weights/rdd_india.onnx` is TRACKED in git (YOLOv8s RDD India,
  640, CPU). Backend `/health` shows `rdd: REAL` when it is present.
- `dashboard/public/weights/rdd_web.onnx` is NOT tracked. Vite copies the
  cloud ONNX there automatically at `npm run dev` / `npm run build`.
  `dashboard/public/weights/manifest.json` IS tracked.
- `models/road_damage/metrics.json` + `backend/models/road_damage/metrics.json`
  are TRACKED honesty proofs (real val split on this host — never invent mAP).

TRAIN (optional, gitignored — never pushed):
- road_damage/YOLOv8_Small_RDD.pt  (auto-downloaded from oracl4/RoadDamageDetection)
- road_damage/YOLOv8s_RDD_india.pt (your fine-tune output, gitignored)
- road_damage/runs/                (all training runs, gitignored)
- traffic/yolov8n.pt               (Ultralytics COCO, auto-downloaded on first vehicle detect)
- traffic_sign/best.pt             (optional; Turkish YOLO from TrafficSignRecognition)
- anpr/plate.pt                    (optional dedicated plate detector)

```text
# one-time: official Figshare zip → .data/rdd_india/data.yaml (gitignored)
.\.venv-train\Scripts\python.exe scripts\prepare_rdd_india.py
# RTX GPU fine-tune; writes models/road_damage/metrics.json from THIS val split
.\.venv-train\Scripts\python.exe scripts\train_rdd.py --epochs 20
# publish to deploy paths (cloud ONNX + dashboard web ONNX + manifest)
.\.venv-train\Scripts\python.exe scripts\export_rdd_onnx.py
.\.venv-train\Scripts\python.exe scripts\export_field_onnx.py
```

Fresh clone → run (Windows):
```text
copy .env.example .env
cd backend & .\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ..\dashboard & npm install & npm run dev
```
Fresh clone → AWS (App Service): `scripts\ship-ui.ps1` packages the dashboard
into `backend/static_dash`, then `azd deploy`. No GPU host needed.
