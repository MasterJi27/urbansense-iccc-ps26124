# UrbanSense — PRODUCT.md (Impeccable init)

Platform: web (React + Vite command center) + Android phone edge (Flutter, phone-only, 2GB-safe)
Users:
- City ops officers triaging defects on desktop, scanning fast, often on projector in review meetings.
- Bus-mounted phone drivers / field inspectors on low-end Android, sunlight, one-hand use, Hindi + English.
- BEL jury: needs 60-second comprehension, honest AI claims, live map wow.

Positioning: Public-transport fleet as mobile sensing infrastructure. Phone IMU + GPS trigger (~1KB JSON) → fused UrbanEvents → GIS command center → closed-loop work orders. Structural Pulse screens bridges (flag for inspection, never collapse prediction).

Evidence on hand:
- Real backend: FastAPI fusion (40m/6h), PostGIS, 41 pytest passing, /bridge/health live.
- Real AI on backend: YOLO RDD road damage, yolov8n + ByteTrack, fast-alpr + fast-plate-ocr (KA19P8488 @1.00). Phone does RULE_BASED triggers only.
- Live dashboard: /map clustering, /bridge SHM history, /events fusion view. No customer logos yet.

What product can honestly claim:
- RULE_BASED phone triggers + REAL backend neural on demand stills. Every payload carries extra.ai_status.
- Screening layer for bridges, not certified inspection. No collapse countdown.
- No video upload, offline queue survives reboot, DPDP-aware restricted evidence.

What it must NOT claim: multi-camera live YOLO on 2GB phone, collapse prediction, Indian sign model (Turkish weights disabled), waterlogging AI (simulated).
