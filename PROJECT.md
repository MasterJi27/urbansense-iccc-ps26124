# UrbanSense — Full Project Document

**SIH 2026 · Problem Statement 26124**  
**Product:** Distributed Urban Intelligence Platform  
**Stage:** Working barebone MVP / vertical slice (local demo)  
**Repo:** `sih_winner_2026_prototype`

**AI perception (boost adapters):** [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) · [boost/INTEGRATION_NOTES.md](boost/INTEGRATION_NOTES.md)

This file is the single overview of **what the problem is, what we built, how it works, which technologies are used, what is real vs simulated, and how to run it**.

---

## 1. Problem and product idea

Cities already have buses, CCTV, and inspection staff, but they do not share one operational picture. Reports of potholes, missing signs, waterlogging, congestion, and incidents sit in silos. Video is expensive to upload continuously. The same physical defect is reported many times and treated as many tickets.

**UrbanSense** treats public-transport vehicles (and later roadside cameras / IoT) as **mobile urban sensing units**.

The first prototype uses **Android smartphones mounted in a car/bus**. The **same backend event model** is designed so bus CCTV, road CCTV, and IoT devices can later post the same `Observation` JSON.

This is **not** “an AI pothole app.” Potholes are one event class. The product is:

- multi-source evidence fusion  
- infrastructure digital passports (QR)  
- closed-loop repair verification  
- fleet / sensor health  
- a city command center  

---

## 2. What differentiates this from a toy CRUD app

| Differentiator | What it means in this codebase |
| --- | --- |
| Observation vs Event | A phone report is an **observation**. The backend clusters reports into one **UrbanEvent**. |
| Fusion (not averaging) | Nearby same-type reports join one event. Score = max(confidence) + source-diversity + human-verify bonuses. Thresholds are configurable. |
| Digital passport | Roads, signs, lights, drains, etc. have persistent IDs, GPS, QR, condition, linked events and repairs. |
| QR as identity | Bus QR binds a phone as a sensor node. Asset QR opens the passport. Work-order QR opens the repair task. |
| Closed loop | DETECT → VERIFY → WORK ORDER → REPAIR → RE-SENSE → RESOLVED or REOPENED |
| Edge / bandwidth | Do not stream continuous video. Capture short evidence around events. Offline queue if the network is down. |
| Adaptive devices | HIGH = edge AI, MEDIUM = lightweight edge, LOW = camera+GPS+IMU and cloud-assisted AI. |
| Backend is source of truth | Flutter and React do not duplicate fusion, scoring, or work-order rules. |

---

## 3. Architecture

```mermaid
flowchart TB
  subgraph clients
    PHONE[Flutter — Sensor + Inspector]
    WEB[React Command Center]
    FUTURE[Future: BUS CCTV / Road CCTV / IoT]
  end
  PHONE -->|HTTPS JWT + offline queue| API[FastAPI modular monolith]
  WEB -->|HTTPS JWT + WebSocket| API
  FUTURE -->|same Observation model| API
  API --> DB[(PostgreSQL + PostGIS or SQLite fallback)]
  API --> FILES[Event evidence files]
  API --> AI[Pluggable Detection / OCR / Fusion engines]
```

**Future path (documented, not hardware-implemented):**

```
PHONE / BUS CCTV / ROAD CCTV / IoT
        → Ingestion gateway (HTTP now; RTSP/MQTT planned)
        → same Observation / UrbanEvent model
```

---

## 4. Repository layout

```
sih_winner_2026_prototype/
├── backend/                 FastAPI API, fusion, seed, tests
│   ├── app/
│   │   ├── api/routes/      auth, fleet, events, assets, work orders, analytics, ingest, demo, ws
│   │   ├── models/          SQLAlchemy tables
│   │   ├── schemas/         Pydantic
│   │   ├── services/        fusion, QR, road health, observations
│   │   ├── realtime/        WebSocket hub
│   │   └── seed.py          Demo data (separated from business logic)
│   ├── tests/
│   └── alembic/
├── dashboard/               React + Vite command center
├── mobile/                  Flutter sensor + inspector app
├── ai/urbansense_ai/        Replaceable detector / OCR / tracker interfaces
├── shared/schemas/          Cross-client JSON sketches
├── docs/                    Research mapping + future ingest
├── storage/evidence/        Uploaded clips/images
├── docker-compose.yml       Postgres/PostGIS, Redis, MinIO, optional backend
├── run-backend.cmd          Windows helper (no PowerShell activate)
├── run-dashboard.cmd        Windows helper (npm.cmd)
├── .env.example
├── README.md                Run book
└── PROJECT.md               This document
```

---

## 5. Tech stack

### 5.1 Backend

| Piece | Technology |
| --- | --- |
| Language | Python 3.12+ (developed on 3.14 locally) |
| API | FastAPI, Uvicorn, Pydantic v2 |
| Auth | JWT (`python-jose`), PBKDF2 password hashes |
| ORM | SQLAlchemy 2 |
| Database | PostgreSQL + PostGIS (Docker) **or** SQLite fallback |
| Geo math | Haversine in `app/geo.py` (works without PostGIS) |
| Realtime | WebSocket `/ws/events` |
| Migrations | Alembic (`create_all` also on startup) |
| Tests | pytest |

### 5.2 Dashboard

| Piece | Technology |
| --- | --- |
| UI | React 18, Vite 6 |
| Routing | React Router |
| Map | Leaflet / react-leaflet (OpenStreetMap tiles) |
| Charts | Recharts |
| API access | `fetch` via Vite `/api` proxy in development (avoids CORS / localhost vs 127.0.0.1 issues) |

Pages: Login, Dashboard, Live Map, Fleet, Events, Event Investigation, Assets, Asset Passport, Road Health, Work Orders, Analytics, Sensor Nodes, Users, Settings.

### 5.3 Mobile

| Piece | Technology |
| --- | --- |
| App | Flutter (Dart 3.13 / Flutter 3.47) |
| HTTP | `http` |
| GPS | `geolocator` |
| IMU | `sensors_plus` (Android/iOS; skipped on Windows) |
| Camera | `camera` |
| QR | `mobile_scanner` on phone; **paste payload** on Windows desktop |
| Offline | JSON file via `path_provider` (survives app restart) |
| Other | `battery_plus`, `connectivity_plus`, `shared_preferences` |

Modes:

- **Sensor mode** (operator): bind bus, trip, live view, emit/queue events, heartbeat, sync.  
- **Inspector mode** (inspector/admin): QR, notes, manual event, repair evidence, verify/fail repair.

### 5.4 AI layer (`ai/urbansense_ai`)

Interfaces (replaceable):

- `DetectionEngine.detect(frame) → Detection[]`  
- `TrackingEngine`  
- `OCRService.read_plate`  
- `SeverityEngine`  
- Backend `FusionEngine` (Python, server-side)

**MVP adapters are simulated and labeled.** No production neural weights are bundled. A real TFLite/ONNX model can be swapped later without changing the event API.

### 5.5 Infra / ops

| Piece | Technology |
| --- | --- |
| Compose | `postgis/postgis:16-3.4`, Redis 7, MinIO, optional backend image |
| Object storage | Local `storage/evidence` for MVP; MinIO in Compose for later |
| Windows helpers | `run-backend.cmd`, `run-dashboard.cmd` |

---

## 6. Data model (source of truth)

### 6.1 Observation (one sighting)

“Sensor X / inspector Y saw something here, then.”

Includes: type, severity, lat/lon, GPS accuracy, UTC timestamp, `source_type`, `source_id`, sensor/bus/route, confidence, simulated flag, optional plate + OCR confidence, evidence URLs, extra JSON.

`source_type` values: `PHONE`, `BUS_CCTV`, `ROAD_CCTV`, `IOT`, `INSPECTOR`, `DEMO`.

### 6.2 UrbanEvent (fused real-world occurrence)

Fields required by the spec (plus fusion metadata):

`event_id`, `public_code` (e.g. `EVENT-A1B2C3`), type, severity, **status**, lat/lon, GPS accuracy, timestamp, source/sensor/bus/route, confidence, evidence URLs, metadata, `fusion_group_id`, `verification_count`, `source_count`, `observation_count`, `fusion_reason`.

**Event statuses:**  
`NEW` · `UNVERIFIED` · `CONFIRMED` · `ASSIGNED` · `IN_PROGRESS` · `REPAIRED` · `RE_VERIFICATION` · `RESOLVED` · `REOPENED` · `REJECTED`

### 6.3 Other tables

`users`, `buses`, `routes`, `sensor_nodes`, `trips`, `assets`, `inspections`, `road_segments`, `event_observations`, `evidence`, `work_orders`, `repairs`, `sync_logs`, `audit_logs`

### 6.4 Event types (SIH coverage)

Road/infra: pothole, road damage, waterlogging, missing divider, missing zebra, damaged sign, obstruction.  
Traffic: congestion (vehicle class/count/density are **architecture + demo**, not a trained counter).  
Safety: pedestrian risk, school crossing.  
Incidents: hit-and-run, rash driving (workflow + plate fields; OCR mocked).

---

## 7. Fusion algorithm (MVP)

Implemented in `backend/app/services/fusion.py` as `SpatialTemporalFusionEngine`.

**Match if all of:**

1. Compatible event types (e.g. pothole ↔ road_damage)  
2. Distance ≤ `FUSION_MAX_DISTANCE_METERS` (default **40 m**)  
3. Time ≤ `FUSION_MAX_TIME_SECONDS` (default **6 hours**)

**If no match:** create a new UrbanEvent.  
**If match:** attach observation, recompute centroid, bump counts.

**Evidence score (transparent, not statistical certainty):**

```
score = min(0.99,
  max(confidences)
  + 0.05 * (unique_sources - 1)     # capped
  + type-diversity bonus
  + 0.12 if any INSPECTOR observation
)
```

The event stores a human-readable `fusion_reason` (distance, window, types, bonuses). The UI must not present this as a p-value.

This module is an interface so a learned fusion model can replace it later.

---

## 8. Road health score (rule-based)

Per road segment (configurable weights in `.env`):

- count of nearby **active** defects  
- extra penalty for HIGH/CRITICAL  
- recurrence (resolved/reopened nearby)  
- traffic exposure  
- pedestrian exposure  

Clamped 0–100. Sortable “worst roads” on the dashboard. **Not a learned model.**

---

## 9. Roles and auth

| Role | Intended access |
| --- | --- |
| SUPER_ADMIN | Everything |
| ADMIN | Fleet, events, analytics, work orders, assets, users, settings |
| INSPECTOR | Verify/reject, QR, evidence, repair submit/verify |
| OPERATOR | Sensor mode, trip, observations, sync |

Same JWT for mobile and dashboard. Register is admin-gated.

**Seeded demo users** (local only, password `UrbanSense@2026`):

- `superadmin@urbansense.local`  
- `admin@urbansense.local`  
- `inspector@urbansense.local`  
- `operator@urbansense.local`  

---

## 10. QR payloads

| Kind | Example |
| --- | --- |
| Bus | `urbansense://bus/BUS-042` |
| Asset | `urbansense://asset/ASSET-001` |
| Work order | `urbansense://work-order/WO-001` |
| Event (optional) | `urbansense://event/{id}` |

Lookup: `GET /qr/lookup?payload=...`

---

## 11. Work-order / repair loop

Work-order statuses: `PENDING` → `ASSIGNED` → `IN_PROGRESS` → `COMPLETED` → `RE_VERIFICATION` → `RESOLVED` / `FAILED`

API:

- `POST /work-orders` (sets event `ASSIGNED`)  
- `POST /work-orders/{id}/repair` (event `RE_VERIFICATION`)  
- `POST /work-orders/{id}/verify` `{ passed: true|false }` → event `RESOLVED` or `REOPENED`

---

## 12. APIs (implemented)

| Method | Path |
| --- | --- |
| POST | `/auth/login`, `/auth/register` |
| GET | `/auth/me` |
| GET/POST | `/buses`, `/sensor-nodes`, `/sensor-nodes/bind`, `/sensor-nodes/heartbeat` |
| POST | `/trips`, `/trips/{id}/stop` |
| POST/GET | `/observations`, `/events`, `/events/{id}` |
| PATCH | `/events/{id}` |
| POST | `/events/{id}/verify`, `/events/{id}/reject` |
| POST | `/evidence/upload` |
| GET/POST | `/assets`, `/assets/{id}`, `/assets/{id}/qr`, `/qr/lookup` |
| GET | `/road-health` |
| GET/POST/PATCH | `/work-orders`, `/work-orders/{id}` |
| POST | `/work-orders/{id}/repair`, `/work-orders/{id}/verify` |
| GET | `/analytics/summary`, `events-by-type`, `events-by-severity`, `events-over-time`, `heatmap`, `route-delay`, `repairs` |
| GET | `/users`, `/settings`, `/fleet/live`, `/health`, `/docs` |
| POST | `/ingest/phone`, `/ingest/cctv`, `/ingest/iot` |
| POST | `/demo/start` `{ step: pothole_a \| pothole_b \| reverify }` |
| WS | `/ws/events?token=` |

OpenAPI: `http://127.0.0.1:8000/docs`

---

## 13. What was implemented in this pass

End-to-end **vertical slice**, not a full production city platform.

### Backend

- JWT + roles  
- Observation ingest → fusion → UrbanEvent  
- WebSocket broadcast on create/update  
- Assets, QR, work orders, repair verify/reopen  
- Sensor bind + heartbeat  
- Analytics summaries + charts data  
- Rule-based road health  
- Demo seed (10 buses including **BUS-042** and **BUS-017**, 5 sensor nodes, ~40 observations fused to fewer events, 20 assets, 10 work orders)  
- HTTP ingest stubs for phone / CCTV / IoT  
- SQLite fallback if Postgres is down  
- pytest: auth, nearby fuse, distant stay separate, QR, work-order lifecycle, geo  

### React command center

- Login, KPI overview, live map, event list + investigation (fusion visualization), fleet, assets/passport, road health, work orders + START DEMO, analytics, sensor cards, users, settings  
- Dev proxy `/api` → `http://127.0.0.1:8000`  

### Flutter

- Login, sensor home (status, capability recommendation, trip, QR, sync)  
- Live screen: camera if available, else placeholder; emit simulated pothole; offline queue  
- Inspector: QR/manual payload, notes, repair/verify  
- Windows desktop: does **not** crash if IMU/QR plugins are missing  

### AI

- Interfaces + `SimulationDetector` / `SimulationOCR` (`DL01AB1234` @ 91%, flagged simulated)  

---

## 14. Status legend (honest)

| Area | Status |
| --- | --- |
| Auth, roles, JWT | **IMPLEMENTED** |
| Observation vs UrbanEvent | **IMPLEMENTED** |
| Spatial-temporal fusion | **IMPLEMENTED** (rules, not ML) |
| Work order + repair loop | **IMPLEMENTED** |
| QR bus/asset/WO | **IMPLEMENTED** |
| WebSocket alerts | **IMPLEMENTED** |
| React command center pages | **IMPLEMENTED** |
| Flutter sensor + inspector + offline queue | **IMPLEMENTED** |
| Demo seed + START DEMO | **IMPLEMENTED** (simulated observations) |
| Road health rules | **IMPLEMENTED** |
| Sensor heartbeats | **IMPLEMENTED** |
| PostgreSQL + PostGIS | **PARTIAL** (Compose ready; local demo often SQLite) |
| Phone camera / GPS / IMU | **PARTIAL** (real plugins; Windows often UNAVAILABLE) |
| Vehicle counting / tracking | **REAL (validated)** — yolov8n + ByteTrack, IDs persist |
| License-plate OCR | **REAL (validated)** — fast-plate-ocr global model on Indian plates |
| Plate detection | **REAL (validated)** — fast-alpr YOLOv9-t, throttled per track |
| Plate temporal vote | **RULE_BASED** — per-char weighted vote keyed by vehicle track |
| Road-damage neural net | **REAL (validated)** — YOLOv8_Small_RDD, see docs/AI_INTEGRATION.md |
| Traffic signs | **EXPERIMENTAL/DISABLED** — Turkish classes, no weights bundled |
| Waterlogging | **SIMULATED** (no model in boost/) |
| Speed | **EXPERIMENTAL** — uncalibrated homography |
| Face / plate blur vision | **FUTURE** (flags + audit only) |
| RTSP / MQTT live ingest | **FUTURE** (docs + HTTP stubs) |
| Learned fusion / TFLite | **FUTURE** |
| Voice notes | **FUTURE** (text field) |
| Blockchain, AR, K8s, training pipelines | **OUT OF SCOPE** for this MVP |

---

## 15. Research basis (used as design, not copied)

Informed by (among others): smartphone accelerometer road-anomaly work; multimodal road-surface sensing; SafeCity-style heterogeneous crowdsensing; GPS localization of reports; dashcam damage detection literature; edge vs cloud tradeoffs.

**A. Established:** IMU+GPS event capture, spatial-temporal clustering, crowdsensing, pluggable detectors, heterogeneous `source_type`.  
**B. Ours:** QR passports, closed-loop repair, transparent fusion score, device capability modes, sensor health, rule-based road health.  
**C. Future research:** learned fusion, calibrated on-device models, tracking, real LPR, blur pipeline, true O-D from AVL/AFC.

Details: `docs/research.md`. Future ingest: `docs/ingestion.md`.

---

## 16. Privacy (MVP)

- Prefer **event clips + metadata**, not continuous raw video  
- Evidence records: `restricted`, `blur_faces`, `blur_plates` flags  
- Role-gated APIs + `audit_logs`  
- Actual face/plate blurring models are **not** implemented  

---

## 17. How to run (Windows)

Backend is often already on **port 8000**. Do not start a second copy.

```bat
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Dashboard (PowerShell blocks `npm.ps1`; use the cmd shim):

```powershell
cd dashboard
& "C:\Program Files\nodejs\npm.cmd" run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). Login `admin@urbansense.local` / `UrbanSense@2026`.

Flutter:

```bat
cd mobile
flutter run
```

On Android emulator set `--dart-define=API_BASE=http://10.0.2.2:8000`.  
On Windows desktop use **DETECT / EMIT POTHOLE** and paste QR `urbansense://bus/BUS-042`.

PostGIS (optional):

```bat
docker compose up -d postgres
```

Then set `DATABASE_URL=postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense`.

Tests:

```bat
cd backend
.\.venv\Scripts\pytest.exe -q
```

---

## 18. Demo story (jury)

1. Admin dashboard + operator phone.  
2. Bind phone to **BUS-042** (QR or paste). Start trip.  
3. Emit pothole (simulated, labeled). Offline: queue then sync.  
4. Event appears on map (WebSocket).  
5. **START DEMO** → BUS-017 observes the same site → fusion (multiple observations, higher evidence score).  
6. Admin creates work order.  
7. Inspector submits repair → `RE_VERIFICATION`.  
8. Verify → `RESOLVED`, or fail → `REOPENED`.  

---

## 19. Known limitations

- Default passwords and `SECRET_KEY` are for **local demo only**.  
- SQLite has no PostGIS GIST indexes; distance is still haversine-correct.  
- Route-delay analytics are **simulated** when real AVL trips are missing (UI labels this).  
- Two Vite processes can land on **5174**; use one server and the `/api` proxy build.  
- Flutter plugin install on Windows may need **Developer Mode** (symlinks).  

---

## 20. What this prototype is for

A **demonstrable SIH foundation**: modular monolith, geospatial events, fusion, QR assets, repair loop, offline phone, live command center, pluggable AI.

It is **not** a production deployment, a trained damage-detection product, or a claim of field-measured AI accuracy.
