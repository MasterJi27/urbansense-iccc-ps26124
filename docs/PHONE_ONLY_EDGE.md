# Phone-Only Edge — PS 26124 Without Extra Hardware

> Constraint: edge device = ONLY mobile phone (low-end 2GB also must work).
> Principle: NO heavy GUI, NO continuous video, NO YOLO on phone. Phone = sensor + trigger, backend = intelligence.
> Problem Statement 26124 is the source of truth — every PS clause maps below.

## 1. PS 26124 → Phone Resource Map (honest)

| PS clause (BEL) | Phone resource used | What phone actually does | Backend does | Status label |
|---|---|---|---|---|
| Road defects: potholes, damaged roads | accel + gyro + GPS + trigger photo | IMU spike (>1.8g RMS jump) + speed 10-60 km/h → POTHOLE candidate ~1KB JSON | Fusion across buses → UrbanEvent, YOLO on uploaded still on demand | RULE_BASED on phone, REAL on backend photo |
| Missing divider / zebra / sign | GPS + trigger photo + asset geofence | Near DIV-101/ZEBRA-101/SIGN-183 (70m) + photo → `POST /assets/{code}/passes observed:false` | asset_watch 3 passes → MISSING_* event | RULE_BASED/GIS |
| Waterlogging / hazards | GPS + photo + manual 1-tap | 1-tap + GPS → WATERLOGGING obs | Fusion + map | RULE_BASED |
| Vehicle density / count / bottleneck | GPS speed + stop-go IMU (NO YOLO on phone) | speed <10 km/h for 60s + stop-go → TRAFFIC_CONGESTION candidate | Backend YOLO on demand photo + multi-bus fusion = real count | RULE_BASED proxy, REAL when photo |
| Pedestrian / school children | GPS + school geofence + speed drop | Near school asset + decel → PEDESTRIAN_RISK candidate | Fusion, human verify | RULE_BASED |
| Hit-and-run / rash + plate + conf + ts + GPS | GPS speed + trigger photo | speed >1.35× limit → RASH_DRIVING + single photo; plate NOT OCRed on phone | Backend fast-alpr + fast-plate-ocr → plate + conf, track vote | RULE_BASED trigger, REAL OCR backend |
| Timestamp + GPS + secure share | GPS + UTC + JWT | Every obs has ISO-8601 UTC + lat/lon + acc + speed/heading | Auth, audit, restricted evidence | IMPLEMENTED |
| GIS map / heatmap / infra / OD / delays / insights | — (backend) | Phone sends only JSON, never video | Leaflet map, /analytics/*, road-health, WO loop | IMPLEMENTED |
| Minimize bandwidth via edge | battery + net + CPU governor | Trigger-only POST (~1KB), batch 40/80/200, offline queue, photo on demand only | — | IMPLEMENTED |

Multi-camera note: PS says front/rear/side/cabin. Single phone = front windshield surrogate. Architecture supports 2nd/3rd phone per bus with same Observation model (`source_id=BUS-042-FRONT`, `BUS-042-CABIN`), no code change. Jury demo uses 1 phone.

## 2. Phone Resources Utilized (no GUI needed)

```
ACCEL 50Hz → RMS/peak/crest window 1s → pothole / bridge joint trigger
GYRO 50Hz → turn vs bump disambiguation (bump = accel spike WITHOUT gyro turn)
MAGNETOMETER → heading when GPS heading stale (low speed)
GPS 1Hz moving / 0.2Hz idle → lat/lon/acc/speed/heading + geofence (bridge/divider/school 70m)
CAMERA → NEVER stream. Single still ONLY on trigger (IMU spike / geofence / 30s heartbeat if moving). ResolutionPreset.low on <2GB.
BATTERY → <20%: accel downsample 1/5, batch 40, GPS low accuracy; 20-50%: 1/2, batch 80; >50%: full, batch 200
NET → connectivity_plus: offline → file queue (cap 500), sync with backoff when back
CPU → phone does RMS only (O(n)), FFT/basemline/EMA on backend (bridge_shm.py)
STORAGE → path_provider JSON queue, survives reboot
```

## 3. Headless Design (GUI = 1 screen)

`mobile/lib/edge/` has zero `BuildContext` inside service:
- `resource_inventory.dart` — capability probe, no UI
- `edge_service.dart` — singleton, start()/stop(), timers + streams, log callback
- `edge_console.dart` — minimal GUI: Start/Stop + 6 status lines + scrolling log (no CameraPreview, no map, no animation)

Old SensorHome/SensorLive kept for compatibility but Edge console is default tab 0.

## 4. Why No YOLO on Phone

2GB Redmi 9A cannot run yolov8n + ByteTrack at >1 FPS without thermal kill + 400MB RAM. Honest split:
- Phone: RULE_BASED triggers (IMU/GPS/geofence) — cheap, always on
- Backend: REAL neural (YOLO RDD, yolov8n, fast-alpr) on uploaded still on demand
Every payload carries `extra.ai_status` so jury sees honesty.

## 5. Field Run (phone only)

1. Mount phone windshield, open app → Edge tab → START
2. Drive: IMU+GPS auto → pothole/bridge batches → offline if no net
3. Dashboard Live Map shows dots via WS, Bridge SHM shows RMS/freq
4. No QR scan on bridge (GPS auto), one-time bus bind only
