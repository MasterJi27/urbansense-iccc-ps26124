# AI integration (boost toolbox → UrbanSense) — VALIDATED

UrbanSense remains the product. Repositories under `boost/` are a **local component library**. UIs, databases, and auth from those repos were **not** merged. Fusion, work orders, GIS and auth are untouched UrbanSense code.

Validation pass ran real inference on CPU (Python 3.14, ultralytics 8.4.138, torch 2.14, opencv 5.0). Numbers below are measured, not claimed.

## Validation summary (measured)

| Component | Model | Input | Latency / FPS | Detections | Status |
| --- | --- | --- | --- | --- | --- |
| Road damage | `YOLOv8_Small_RDD.pt` (89.5 MB, RDD2022) | 400×300 pothole photo | 0.14 s hot (~7 FPS), 1.3–1.5 s cold | Alligator Crack 0.69 | **REAL** |
| Road damage (negative) | same | blank/gray 640×640 | 0.14 s hot | 0 (correct) | **REAL** |
| Vehicles + persons | `yolov8n.pt` COCO (6.5 MB) | 810×1080 street photo | ~1.9 s cold | bus 0.87 + 3 persons | **REAL** |
| Tracking | Ultralytics ByteTrack | same photo ×2 frames | — | IDs 1–4 → 1–4 (persist) | **REAL** |
| Pipeline (both models) | — | 20 mixed frames | 3.8 FPS, p50 0.15 s, p95 1.5 s (warmup) | 10 road obs, vehicle tracks | **REAL** |
| Plate detection | `yolo-v9-t-384` ONNX (7.4 MB, hub) | Indian plate photos | 0.02–0.09 s | KA plate 0.90, Kerala car plate 0.94 | **REAL** |
| Plate OCR | `cct-s-v2-global` ONNX (hub) | plate crops | 0.02–0.06 s/crop | KA19P8488 @1.00, KL6D827 @0.97 | **REAL** |
| Track vote | per-char weighted vote (adapted MIT) | 3–4 reads/track | — | KA19P8488 confirmed at dwell 3 | **RULE_BASED** |
| ANPR end-to-end | detector→OCR→vote→Observation→Event | plate photo + API | ~0.065 s/read | `EVENT-8ADE0A` RASH_DRIVING plate=KA19P8488 sim=False | **PASS** |
| Camera → API → Event | — | `run_camera` on pothole photo | 1 frame, 0.64 FPS cold | `EVENT-8A2C7C` ROAD_DAMAGE 0.68, sim=False | **PASS** |
| WS → dashboard transport | — | POST /observations | <10 s round-trip | `event.created` received | **PASS** |

Classes (verified against `model.names`): `Longitudinal Crack, Transverse Crack, Alligator Crack, Potholes`.

## Component mapping

| UrbanSense adapter | Source repo | Source (idea/files) | Model | Status |
| --- | --- | --- | --- | --- |
| `Yolov8RoadDamageDetector` | RoadDamageDetection | YOLO load + class list from Streamlit pages (not the Streamlit app) | `YOLOv8_Small_RDD.pt` | **REAL** when weights load |
| `Yolov8VehicleDetector` + `ByteTrackAdapter` | Edge-AI-Traffic-Analytics | `deployment/traffic_monitor.py` uses Ultralytics `YOLO.track`; we use the same API | `yolov8n.pt` COCO | **REAL** when ultralytics available |
| `TesseractOCR` + `TemporalVoter` | ANPR YOLO+OCR (architecture) + simple ANPR (Tesseract fallback) | Temporal voting reimplemented; **no** `parse_turkish_plate` | Tesseract / optional plate YOLO | **FALLBACK** (used only if fast-plate-ocr unavailable) |
| `FastALPRPlateDetector` | ANPR YOLO+OCR `detector/fast_alpr.py` idea | `DefaultDetector` YOLOv9-t 384 ONNX, UrbanSense adapter | hub `yolo-v9-t-384` (~7 MB) | **REAL** |
| `FastPlateOCR` | ANPR YOLO+OCR `ocr/fast_plate.py` idea | `LicensePlateRecognizer` cct-s-v2-global, per-char conf | hub `cct-s-v2-global` | **REAL** |
| `TrackPlateVoter` | ANPR YOLO+OCR `postprocess/temporal.py` (MIT) | per-char weighted vote, keyed by UrbanSense track ID; Turkish parse bypassed | none | **RULE_BASED** |
| Indian plate check | — (own regex) | Approximate `XX00XXX0000` pattern | none | **RULE_BASED** (format check ≠ proof of correct OCR) |
| `HomographySpeedEstimator` | Edge-AI SpeedEstimator + Real-Time-Traffic mapper/speedometer | Homography + world displacement | none | **EXPERIMENTAL**, uncalibrated; moving-camera ego-motion NOT compensated; never evidence-grade |
| LOS / congestion | Edge-AI `classify_congestion` idea | HCM-style table reimplemented; needs LOS E/F for **8 consecutive frames** | none | **RULE_BASED** (single crowded frame never emits) |
| Rash driving | — | speed vs 1.35× limit | none | **RULE_BASED** (inherits speed limitations) |
| Pedestrian risk | COCO `person` + vehicle proximity | 0.12 normalized-diagonal threshold | COCO | **RULE_BASED** (not a trained risk model) |
| `TrafficSignDetector` | TrafficSignRecognition | YOLO custom weights if present | `best.pt` (Turkish classes) | **EXPERIMENTAL**, disabled by default (`enabled: false`); **dataset = TR, not Indian MoRTH** |
| Waterlogging | none | — | none | **SIMULATED** (demo seed only) |
| iWatchRoad | reference only | dashcam/GPS/road-health ideas | — | **not copied** (CC-BY-NC-SA) |

## Edge / bandwidth design (measured behavior)

```text
camera (webcam / video / RTSP)
  ↓  local inference (ultralytics YOLO, fast-alpr, fast-plate-ocr — all on-device/CPU)
compact Observation JSON (~0.5–2 KB: type, confidence, lat/lon, timestamp,
source IDs, ai_status, optional plate + evidence URL)
  ↓  POST /observations — only when a detector fires or a rule triggers
central FastAPI → Fusion → UrbanEvent → WebSocket → dashboard
```

- Raw continuous video is **never** uploaded. `run_camera.py` posts compact JSON per detection; per-frame road observations fuse into one event server-side.
- Evidence (frame crops/clips) uploads only via explicit paths (`POST /evidence/upload`, `POST /ai/analyze-frame`), flagged `restricted` with blur intent in the privacy model.
- Measured: full pipeline ~0.15 s/frame p50 CPU; ANPR read ~0.065 s; throttled (1.5 s/track OCR, 8 s rash re-emit, 15 s congestion re-emit, 8-frame congestion persistence).

## ANPR pipeline (REAL)

```text
frame → vehicle track (ByteTrack) → plate detect (fast-alpr, throttled 1.5 s/track)
  → plate crop → OCR (fast-plate-ocr, per-char conf) → track vote (dwell 3)
  → Indian regex check (RULE_BASED) → incident Observation (plate_text,
  plate_confidence, track_id, plate_ai_status, plate_format_valid) → Fusion → UrbanEvent
```

Measured on Indian imagery: clear KA-19-P-8488 → det 0.90, OCR `KA19P8488` @1.00, valid; 15° rotated → same read @0.98; half-size+blur (motion proxy) → same @1.00; Kerala car scene → det 0.94, `KL6D827` @0.97, regex-invalid (old 3-digit Kerala format — regex limitation, read itself genuine). Noisy-char vote test: `DL8CAF503Z` @0.59 outvoted by two `DL8CAF5032` reads → confirmed `DL8CAF5032`. Turkish `parse_turkish_plate`/confusion correction never enter the runtime path.

## Bugs found and fixed in this pass

1. **numpy float32 broke the API.** YOLO bbox values (`np.float32`) flowed into `extra` JSON → `TypeError: Object of type float32 is not JSON serializable` on `POST /ai/analyze-frame`. Fixed with `engines.to_plain()` at the pipeline boundary (`_obs` also float-casts confidence/speed/plate confidence). Covered by `test_to_plain_sanitizes_numpy` + `test_analyze_frame_endpoint_creates_event`.
2. **Backend suite did not collect.** Mixed `from test_auth` / `from tests.test_auth` imports with no `tests/__init__.py`. Standardized + added `__init__.py`. Suite now collects from `backend/`.
3. **COCO weights landed in repo root.** `YOLO("yolov8n.pt")` downloads into CWD. `resolve_coco()` now migrates a stray root download into `models/traffic/`; file moved.
4. **Missing ByteTrack solver dep.** Ultralytics auto-installed `lap` at runtime; pinned `lap>=0.5.12` in `ai/requirements-ai.txt`.

## Status vocabulary (every payload carries `extra.ai_status`)

`REAL` = neural forward pass executed · `RULE_BASED` = deterministic rule on real signals · `EXPERIMENTAL` = runs but not trustworthy (uncalibrated speed, Turkish signs) · `SIMULATED` = mock/demo, UI must flag.

## How to run

```bat
cd C:\Users\Shikhar\OneDrive\Desktop\sih_winner_2026_prototype
backend\.venv\Scripts\python.exe -m pip install -r ai\requirements-ai.txt
set PYTHONPATH=ai
backend\.venv\Scripts\python.exe -m urbansense_ai.run_camera --source 0 --lat 28.6328 --lon 77.2195
```

Video file:

```bat
backend\.venv\Scripts\python.exe -m urbansense_ai.run_camera --source path\to\video.mp4
```

RTSP (same flag): `--source rtsp://...`

Backend must be on `http://127.0.0.1:8000`. Dashboard map updates via existing WebSocket after observations post.

Single image: `POST /ai/analyze-frame` (multipart `file` + lat/lon).

Capabilities: `GET /ai/capabilities`

Tests: `cd backend && .\.venv\Scripts\python.exe -m pytest -q` (27 passed) · AI unit: `PYTHONPATH=ai pytest ai/tests -q` (11 passed).

## Limitations (do not oversell)

- RDD model is trained on RDD2022 (multi-country including India) — still not a guarantee of field accuracy. A large pothole photo classified as **Alligator Crack 0.69**, not `Potholes`: the detector fires on real damage but fine-grained classes are approximate.
- COCO vehicle model is general, not Indian fleet-tuned.
- Uncalibrated homography + moving dashcam ⇒ speed is **not** court-grade; UI labels it experimental.
- Turkish signs if `best.pt` used; disabled without weights.
- No waterlogging model in `boost/`.
- ANPR is Tesseract-fallback only; `fast-alpr`/`fast-plate-ocr` deliberately deferred (extra onnx stack + model downloads for uncertain gain in this window).
- `fast-plate-ocr` / FastALPR not added as a hard dependency (heavy). Tesseract fallback instead.
- CPU YOLO is a few FPS; acceptable for this MVP. Road observations emit per frame (no throttle) — fusion groups them, but a busy camera posts often.
- GPS is still whatever you pass (`--lat/--lon` or phone); the AI layer does not own GPS.
