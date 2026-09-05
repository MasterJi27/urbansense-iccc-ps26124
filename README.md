# UrbanSense — Distributed Urban Intelligence Platform

SIH 2026 · BEL Problem Statement **26124** · ICCC command register

Public-transport vehicles become **mobile urban sensing units**. FastAPI is the source of truth. React is the ICCC. Flutter is the phone edge. Fusion, work orders, and honesty labels live only in the API.

**Live (Azure App Service):** https://app-urbansense-yngmbk.azurewebsites.net/

**USP:** Fleet confirms presence. Fleet also confirms absence. One bus can do neither.

This is not a rewrite in C++ / Rust / Go. Those languages would add surface area without helping BEL. Production here means one backend language (Python), one ICCC UI (React), one phone client (Flutter), reusable domain services, and honest labels.

**Full project document** (problem, architecture, tech, implemented vs mocked): [PROJECT.md](PROJECT.md).  
**Software engineering approaches** (fusion, honesty, RBAC, closed loop): [docs/SOFTWARE_ENGINEERING.md](docs/SOFTWARE_ENGINEERING.md).

It is **not** “AI pothole detection.” Potholes are one event class inside a multi-source evidence platform.

---

## Architecture

```mermaid
flowchart TB
  subgraph clients
    PHONE[Flutter phone sensor / inspector]
    WEB[React command center]
    FUTURE[Future: bus CCTV / road CCTV / IoT]
  end
  PHONE -->|HTTPS + JWT| API[FastAPI modular monolith]
  WEB -->|HTTPS + WebSocket| API
  FUTURE -->|same Observation model| API
  API --> PG[(PostgreSQL + PostGIS or SQLite fallback)]
  API --> FILES[Event evidence storage]
  API --> AI[DetectionEngine / OCR / FusionEngine]
  PHONE --> Q[Offline observation queue]
  Q -->|sync| API
```

Backend is the only place business rules live (fusion, work orders, health scores, roles). Frontends do not duplicate that logic.

---

## Quick start

### Demo credentials (seeded, development only)

| Role | Email | Password |
| --- | --- | --- |
| SUPER_ADMIN | `superadmin@urbansense.local` | `UrbanSense@2026` |
| ADMIN | `admin@urbansense.local` | `UrbanSense@2026` |
| INSPECTOR | `inspector@urbansense.local` | `UrbanSense@2026` |
| OPERATOR | `operator@urbansense.local` | `UrbanSense@2026` |

QR examples: `urbansense://bus/BUS-042` · `urbansense://asset/ASSET-001` · `urbansense://work-order/WO-001`

### 1. Backend

Windows PowerShell often blocks `activate.ps1`. Do **not** rely on `uvicorn` being on PATH — call the venv executable:

```bat
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or double-click `run-backend.cmd` in the repo root.

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
copy ..\.env.example .env
```

OpenAPI: http://localhost:8000/docs · Health: http://localhost:8000/health

If Docker Desktop is running, use PostGIS instead:

```bash
docker compose up -d postgres
# set DATABASE_URL=postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense
```

Without Postgres the API **falls back to SQLite** so the demo still runs. Fusion still uses haversine (geospatially correct). PostGIS indexes apply when Postgres is used.

### 2. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

If `npm` is not recognized (new Node install, terminal not restarted):

```bat
$env:Path = "C:\Program Files\nodejs;" + $env:Path
npm run dev
```

Or double-click `run-dashboard.cmd`.

Open http://localhost:5173 — login as admin.

### 3. Flutter

```bash
cd mobile
flutter pub get
flutter run
# Android emulator: API_BASE may need http://10.0.2.2:8000
flutter run --dart-define=API_BASE=http://10.0.2.2:8000
```

Windows desktop: camera/GPS/IMU/QR-camera plugins are often missing. The app now shows **UNAVAILABLE** and a **paste QR payload** screen instead of crashing. Use **DETECT / EMIT POTHOLE** (simulated, labeled). For real camera + IMU + QR scan, run on an **Android** device or emulator.

### 4. Tests

```bash
cd backend
pytest -q
cd ../dashboard
npm run build
cd ../mobile
flutter analyze
flutter test
```

---

## Vertical slice demo (must work)

1. One command (Windows, from repo root): `scripts\start_demo.bat` — opens backend, dashboard, AI camera. Or start each manually below.
2. Login operator on phone; admin on web.
3. QR-bind `urbansense://bus/BUS-042`.
4. Start trip → live camera view (or offline placeholder).
5. Emit pothole (simulated detector unless a real engine is plugged in).
6. If offline, event is queued; reconnect → sync.
7. Dashboard WebSocket shows the event on the map.
8. Work Orders → **START DEMO** to emit BUS-042 then BUS-017 (fusion).
9. Open event: multiple observations, fusion reason text, "How this was determined" honesty block.
10. Create work order → inspector submits repair → status **RE_VERIFICATION**.
11. Verify repair → **RESOLVED**, or fail → **REOPENED**.
12. Missing-infrastructure demo: `POST /assets/SIGN-183/passes` ×3 with `observed:false` → GIS-derived DAMAGED_SIGN event (RULE_BASED, not a neural absence detector).

Clean jury database (SQLite dev): stop backend, `del backend\urbansense.db`, restart — seed recreates buses, SIGN-183/DIV-101/ZEBRA-101, trips, and the BUS-042/017 fusion pair. Full requirement audit: `docs/PS26124_COVERAGE_MATRIX.md`.

---

## Features

- Observation vs fused **UrbanEvent**
- Deterministic spatial-temporal **fusion** (configurable meters/seconds, source diversity; not averaged confidence)
- JWT + roles: SUPER_ADMIN, ADMIN, INSPECTOR, OPERATOR
- Assets (digital passport) + QR lookup
- Work orders + repair verification
- Sensor heartbeats and processing modes
- Offline-first mobile queue (JSON file, survives app restart)
- Demo seed: 10 buses (incl. BUS-042 / BUS-017), 5 nodes, ~40+ events, 20 assets, 10 work orders
- Privacy *architecture*: restricted evidence flags, audit logs, prefer clips over raw video (blurring pipeline is **planned**)

---

## Tech stack

| Layer | Choice |
| --- | --- |
| Mobile | Flutter |
| Dashboard | React + Vite + Leaflet + Recharts |
| API | FastAPI + SQLAlchemy 2 + Pydantic v2 + JWT |
| Data | PostgreSQL/PostGIS (Docker) or SQLite fallback |
| Realtime | WebSocket `/ws/events` |
| AI | Replaceable Python interfaces; **simulation adapter** in MVP |

---

## Folder structure

```
backend/     FastAPI source of truth (fusion, WO, RBAC) + packaged ICCC UI
dashboard/   React ICCC (Vite). Production copy: backend/static_dash
mobile/      Flutter phone edge
ai/          Detection / OCR / tracking engines
infra/       Azure Bicep
docs/        Jury script + PS coverage
scripts/     Package + local demo
shared/      Cross-client schemas
```

---

## API (selected)

| Method | Path |
| --- | --- |
| POST | `/auth/login` `/auth/register` |
| GET/POST | `/buses` `/sensor-nodes` `/sensor-nodes/heartbeat` `/sensor-nodes/bind` |
| POST | `/trips` `/trips/{id}/stop` |
| POST/GET | `/observations` `/events` `/events/{id}` |
| POST | `/events/{id}/verify` `/events/{id}/reject` |
| GET/POST | `/assets` `/assets/{id}` `/assets/{id}/qr` `/qr/lookup` |
| GET/POST/PATCH | `/work-orders` `/work-orders/{id}` `/repair` `/verify` |
| GET | `/analytics/*` `/road-health` `/fleet/live` `/settings` |
| POST | `/ingest/phone` `/ingest/cctv` `/ingest/iot` `/demo/start` |
| WS | `/ws/events?token=` |

---

## AI setup

`ai/urbansense_ai` exposes `DetectionEngine`, `TrackingEngine`, `OCRService`, `SeverityEngine`. Every output carries `extra.ai_status`: REAL (neural inference executed) / RULE_BASED / EXPERIMENTAL / SIMULATED.

Validated REAL: YOLOv8 road-damage + yolov8n vehicles/ByteTrack + fast-alpr plate detection/fast-plate-ocr reading (see `docs/AI_INTEGRATION.md` for measured latency/FPS). Tesseract remains as fallback if the fast stack is unavailable. Speed is EXPERIMENTAL (uncalibrated). Install extras with `pip install -r ai/requirements-ai.txt`, then `python -m urbansense_ai.run_camera --source 0`.

To plug a different model later: implement `detect(frame) -> Detection[]` and inject it on HIGH/MEDIUM devices or an edge gateway.

---

## Implemented vs planned

| Area | Status |
| --- | --- |
| Auth JWT + roles | IMPLEMENTED |
| Observation / UrbanEvent split | IMPLEMENTED |
| Spatial-temporal fusion | IMPLEMENTED (rule-based, not ML) |
| Work order + repair verify/reopen | IMPLEMENTED |
| QR lookup (bus/asset/WO) | IMPLEMENTED |
| WebSocket event push | IMPLEMENTED |
| React command center pages | IMPLEMENTED |
| Flutter sensor + inspector + offline queue | IMPLEMENTED |
| Demo seed + START DEMO | IMPLEMENTED (simulated observations) |
| Road health rule score | IMPLEMENTED |
| Sensor heartbeats | IMPLEMENTED |
| PostGIS Docker | PARTIALLY IMPLEMENTED (compose file; local demo uses SQLite fallback) |
| Camera / GPS / IMU on phone | PARTIALLY IMPLEMENTED (real APIs; desktop often unavailable) |
| Independent-bus confirm + absence expire / repair audit | IMPLEMENTED (RULE_BASED) |
| Azure App Service (API + dashboard) | IMPLEMENTED |
| AI detection / OCR | REAL on stills when weights present; otherwise labeled SIMULATED |
| Face/plate blur pipeline | FUTURE (flags + audit only) |
| RTSP / MQTT live ingest | FUTURE (HTTP ingest stubs + docs) |
| Learned fusion / on-device TFLite | FUTURE |
| Voice notes | FUTURE (text notes now) |

---

## Known limitations

- Detector and OCR are **simulated** unless you wire a model.
- Face/plate blur is designed, not a vision pipeline.
- SQLite fallback has no PostGIS GIST indexes.
- Route delay charts use seeded/simulated durations when trips have no AVL.
- Flutter voice notes are a text field placeholder.
- Do not use default passwords or SECRET_KEY outside local demo.

## License

SIH 2026 evaluation prototype. Demo credentials are for the jury host only. Stop `rg-urbansense` after the demo so student credits do not drain.
