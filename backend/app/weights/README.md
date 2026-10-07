Deployment RDD weight (TRACKED in git).

- `rdd_india.onnx` — YOLOv8s RDD India, imgsz 640, ONNX CPU, no NMS.
  Used by `backend/app/services/rdd_cloud.py` for official stills
  (`POST /ingest/phone`). `/health` reports `rdd: REAL` when present.
- Vite copies this file to `dashboard/public/weights/rdd_web.onnx` at
  `npm run dev` / `npm run build` for the `/field` windshield preview.
  The dashboard copy is gitignored; only this file + `manifest.json` are tracked.

Re-export (training host only):
```text
.\.venv-train\Scripts\python.exe scripts\export_rdd_onnx.py
.\.venv-train\Scripts\python.exe scripts\export_field_onnx.py
```
Do NOT commit `models/road_damage/*.pt`, `models/road_damage/runs/`,
root `yolov8*.pt`, or `weights/yolo26*` — those are training waste.
