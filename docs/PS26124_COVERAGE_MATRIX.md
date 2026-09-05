# BEL PS 26124 — Coverage Matrix (audited, honest)

Mechanism legend: `DIRECT_PERCEPTION` = neural model on pixels · `DERIVED_ANALYTICS` = deterministic rule over real signals · `GIS/BASELINE` = asset/GIS/state comparison · `WORKFLOW` = human-in-the-loop state machine · `SIMULATED` = mock/demo data, UI-flagged · `NOT_IMPLEMENTED` = absent, documented.

Status legend: `REAL` / `RULE_BASED` / `EXPERIMENTAL` / `SIMULATED` / `DISABLED` / `NOT_IMPLEMENTED`.

| BEL requirement | Mechanism | Implementation | Status | Evidence | Remaining work | Demo method |
|---|---|---|---|---|---|---|
| Potholes | DIRECT_PERCEPTION | YOLOv8_Small_RDD (RDD2022) → POTHOLE | REAL | `ai/urbansense_ai/road_damage.py`; pothole photo → det; `test_rdd_real_photo_detection` | Field-accuracy validation | Webcam/road video → live map event |
| Damaged roads (cracks) | DIRECT_PERCEPTION | Same model: longitudinal/transverse/alligator crack → ROAD_DAMAGE | REAL | `mapping.rdd_event`; fine-grained classes approximate (documented) | Same as above | Same demo |
| Missing dividers | GIS/BASELINE | Expected DIVIDER asset + ≥3 non-confirming passes/60 m → MISSING_DIVIDER | RULE_BASED | `services/asset_watch.py`, `POST /assets/{code}/passes`, `test_asset_watch.py` | Tune passes/radius per corridor | Post 3 passes for DIV-101 → event |
| Missing zebra crossings | GIS/BASELINE | Same pattern → MISSING_ZEBRA | RULE_BASED | Same files | Same | Same for ZEBRA-101 |
| Damaged/missing traffic signboards | GIS/BASELINE + DIRECT_PERCEPTION | Asset-watch → DAMAGED_SIGN; sign detector adapter exists but disabled (Turkish weights) | RULE_BASED / DISABLED | `asset_watch.ASSET_TO_EVENT`; `signs.py` (`enabled: false`) | Indian MoRTH sign model | Passes for SIGN-183 → event |
| Waterlogging | SIMULATED | Event type + seed/demo path; no model in boost/ | SIMULATED | `GET /ai/capabilities` → waterlogging SIMULATED | Acquire/train a model | Show capabilities honesty |
| Other road hazards | DIRECT_PERCEPTION + WORKFLOW | ROAD_OBSTRUCTION type via detector/inspector + work-order loop | REAL/WORKFLOW | EventType + fusion + WO lifecycle tests | — | Emit obstruction → WO → resolve |
| Vehicle detection | DIRECT_PERCEPTION | yolov8n COCO + ByteTrack | REAL | bus 0.87 + persons; `test_vehicle_track_ids_persist` | Indian fleet taxonomy | bus.jpg / traffic video |
| Vehicle classification | DIRECT_PERCEPTION | COCO taxonomy (car/bus/truck/motorcycle/bicycle) stored in track metadata | REAL (COCO) | `vehicles.py`, `mapping.vehicle_event` | State explicitly: NOT Indian-specific | Settings/capabilities note |
| Vehicle counting | DERIVED_ANALYTICS | Count of live ByteTrack IDs per frame | REAL-derived | `pipeline` vehicle loop; congestion LOS input | — | Traffic frame → count in congestion extra |
| Vehicle density | DERIVED_ANALYTICS | Count per ROI area in LOS table | RULE_BASED | `analytics.classify_los` | Calibrate ROI area per camera | Same |
| Bottlenecks/congestion | DERIVED_ANALYTICS | LOS E/F + 8-frame persistence → TRAFFIC_CONGESTION | RULE_BASED | `congestion_should_emit`; single frame never emits (tested) | Calibrate thresholds per site | Congested clip → event after persistence |
| Vulnerable pedestrian situations | DERIVED_ANALYTICS | Person+vehicle bbox proximity → PEDESTRIAN_RISK, `method=bbox-proximity` | RULE_BASED | `analytics.pedestrian_risk`; EventDetail "How determined" block | True risk model (future research) | Person+vehicle frame → risk event |
| Hit-and-run | WORKFLOW + DIRECT_PERCEPTION | HIT_AND_RUN type; tracking + rash trigger + plate OCR + vote + GPS/ts + evidence (no accident classifier claimed) | REAL pieces / RULE_BASED trigger | `EventType.HIT_AND_RUN`, ANPR incident path, `test_incident_observation_with_plate` | Accident-recognition model (out of scope) | Rash → plate → incident event |
| Rash driving | DERIVED_ANALYTICS | Speed > 1.35× limit → RASH_DRIVING with track/speed/threshold/ts/GPS | RULE_BASED | `analytics.rash_driving`; event carries `speed_calibrated` flag | Calibrated speed source | Speeding track → event |
| Offending vehicle tracking | DIRECT_PERCEPTION | ByteTrack persistent IDs attached to incident (`track_id`) | REAL | Track persistence test; incident extra | — | Same incident demo |
| Registration extraction | DIRECT_PERCEPTION | fast-alpr detect + fast-plate-ocr read, track-associated | REAL | KA19P8488 @1.00; car scene KL6D827 @0.97 | Indian-tuned OCR (future) | Plate photo → read |
| Registration confidence | DIRECT_PERCEPTION | Mean per-character probability from recognizer | REAL | `anpr._mean_conf`; vote weights | — | Shown beside plate |
| Timestamp | GIS/BASELINE | UTC everywhere (backend + pipeline ISO-8601) | IMPLEMENTED | `Observation.timestamp`, engineering rule 10 | — | Every event shows time |
| GPS | GIS/BASELINE | lat/lon + accuracy on every observation; phone GPS or --lat/--lon | IMPLEMENTED | `validate_coords`, haversine fusion | Phone GPS on device | Map pin per event |
| Secure central alert | WORKFLOW | JWT + roles; incident events via existing WS/event system; plates only in authed views; no plate values in logs (verified) | IMPLEMENTED | WS `event.created`; log grep clean | Role-scoped retention policy | Login → live incident alert |
| Fleet aggregation | GIS/BASELINE | Buses/routes/sensor-nodes/trips; fleet + live endpoints | IMPLEMENTED | `/fleet/live`, `/buses`, seed 10 buses | Real AVL feed | Fleet page |
| GIS map | GIS/BASELINE | Leaflet live map: buses, events, segments, assets, severity colors | IMPLEMENTED | `LiveMap.jsx` | — | Open Live Map |
| Congestion heatmap | DERIVED_ANALYTICS | `/analytics/heatmap` weighted points from fused events | IMPLEMENTED | `analytics.heatmap` | Density-weighted tiles | Analytics/heat view |
| Infrastructure deficiencies | GIS/BASELINE | Asset passports + conditions + linked events + road-health scores | IMPLEMENTED | Assets API, road-health, asset-watch | — | Asset passport page |
| OD patterns | DERIVED_ANALYTICS | `/analytics/od` from trip + route polyline endpoints; seeded trips flagged; empty when no trips | IMPLEMENTED (demo data) | `analytics.origin_destination` + test | Real trip GPS trails | Analytics OD table |
| Route delays | DERIVED_ANALYTICS | Planned vs actual trip duration; simulated flagged; honest empty fallback | IMPLEMENTED (demo data) | `analytics.route_delay` + UI SIMULATED tags | Real AVL timestamps | Analytics delay table |
| Actionable insights | WORKFLOW | Prioritized events → work orders → repair → re-verification → resolved/reopened | IMPLEMENTED | WO lifecycle + repair verify tests | Auto-prioritization | Event → WO → repair → verify |
| Defect absence / stale first sighting | GIS/BASELINE + WORKFLOW | N later *independent* buses in the same 40 m cell with no compatible trigger → `EXPIRED`. After repair, M clear passes → `REPAIR_VERIFIED`. Same bus / cabin never count. | RULE_BASED | `fusion.record_clear_passes`; heartbeat; ConfirmationStrip third cell; `test_fusion.py` expire/repair/reopen | Not a neural “pothole gone” model | Jury run steps 3–5 |
| Multi-cam (front/rear/side/cabin) | WORKFLOW | Five bays on BUS-042/017; cabin cannot emit road defects; `POST /ingest/bus/stream-frame` | REAL (bays) | `ps26124.py`, `GET /ai/ps26124` | Hardware four-cam NVR | Phone FRONT stand-in + seeded bays |
| Edge processing | DIRECT_PERCEPTION | All inference runs locally (CPU/ONNX); adaptive HIGH/MED/LOW modes | REAL | `run_camera.py`, processing modes | On-device TFLite (future) | Run camera with backend offline → queue |
| Bandwidth minimization | GIS/BASELINE | ~1 KB Observation JSON per detection; no video upload; evidence on demand | IMPLEMENTED | `docs/AI_INTEGRATION.md` edge section | — | Show POST payload size |
| Incident reports | WORKFLOW | Event investigation view: observations, fusion reason, evidence, GPS/ts, verify/reject, WO creation | IMPLEMENTED | `EventDetail.jsx` + "How determined" block | PDF/export (future) | Open any incident event |

## Deliberately NOT claimed

- Neural absence detection (missing infra is GIS-derived, not a model).
- Evidence-grade speed (EXPERIMENTAL, UI-labeled; phone GPS speed labeled "GPS").
- Trained rash/pedestrian/collision classifiers (documented heuristics with exact thresholds).
- Indian sign model (adapter DISABLED rather than wrongly classified).
- Waterlogging AI (SIMULATED).
- Real passenger OD / real AVL (demo rows flagged SIMULATED; endpoints go honestly empty).

## Clean jury-demo database

Validation events (`EVENT-8A2C7C`, `EVENT-8ADE0A`, …) live in the dev DB. Safest reset (SQLite dev only):

```bat
cd C:\Users\Shikhar\OneDrive\Desktop\sih_winner_2026_prototype\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
REM stop it (Ctrl+C), then:
del urbansense.db
REM start again -> DEMO_SEED_ON_START reseeds buses, SIGN-183/DIV-101/ZEBRA-101, trips, fusion pair
```

Never delete code, `models/`, or `boost/`. Postgres users: drop/recreate the `urbansense` database instead.
