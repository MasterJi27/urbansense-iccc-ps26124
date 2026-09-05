# SadakSaarthi

SIH 2026 · BEL problem statement **26124** · Delhi ICCC command register

Public-transport vehicles are **mobile sensing units**. FastAPI is the source of truth. React is the ICCC desk. The windshield is a phone browser on `/field` (Chrome or Safari). Fusion, work orders, and honesty labels live only in the API.

**Live:** https://app-urbansense-yngmbk.azurewebsites.net/

**USP:** Fleet confirms presence. Fleet also confirms absence. One bus can do neither.

Visible wordmark is **SADAKSAARTHI**. Login emails, Azure hostname (`app-urbansense-yngmbk`), and Flutter package name still say `urbansense` — those are identifiers, not a second product.

This is **not** “AI pothole detection.” Potholes are one event class in a multi-source evidence platform.

**Full project document:** [PROJECT.md](PROJECT.md)  
**Engineering approaches:** [docs/SOFTWARE_ENGINEERING.md](docs/SOFTWARE_ENGINEERING.md)  
**Jury walk:** [docs/JURY_8MIN.md](docs/JURY_8MIN.md)

---

## Two surfaces (do not mix)

| Surface | URL | Who | Auth |
| --- | --- | --- | --- |
| ICCC desk | `/` after officer login | Depot / ICCC | JWT (`admin@urbansense.local` …) |
| Phone booth | `/field` | Windshield phone | 6-digit PIN from the desk |

- ICCC has no FIELD / CCTV nav. `/cctv` redirects to Overview.
- An ICCC JWT is **not** a field token. A field token cannot open ICCC (`4403` on `/ws/field-live` if you send the wrong scope).
- Flutter, if used, loads the same `/field` page. It is not a second detector.

---

## What is real (honesty)

Every payload carries `ai_status`: **REAL** / **RULE_BASED** / **SEED** / **SIMULATED** / **DISABLED**.

| Piece | Label | What it actually is |
| --- | --- | --- |
| Official road-damage ticket | REAL | Azure App Service still → YOLOv8s 640 ONNX **CPU**, India RDD D00/D10/D20/D40, conf 0.22 |
| Phone windshield boxes | RULE_BASED preview | On-device 640 India RDD (`rdd_web.onnx`). Road-band + full-frame merge + IoU tracker. Same weights, not a new test mAP |
| Held-out test mAP@0.5 | 0.6189 | 323-image India RDD test split on this host. D10 has 6 boxes (noisy). Not certified field accuracy |
| Live desk ticks | REAL transport | Phone `/ws/field-live` → ICCC `/ws/live` plus REST poll. Round-trip is tens of ms, **not 1 ms** |
| Fleet confirm / absence expire | RULE_BASED | Second independent bus in 40 m / 6 h. Same bus cannot self-confirm |
| Officer email | DISABLED until Gmail is connected | Composio mails only on `FLEET_CONFIRMED`. It is not a detector |
| App Service GPU | none | Linux App Service has no CUDA. Overlay is WASM (WebGPU only if ONNX Runtime attaches). Official still stays CPU unless a separate T4 host is added |
| Indian MoRTH signs | DISABLED | GIS missing-sign geofence only |
| Waterlogging net | SIMULATED | No flood model |
| School-child classifier | RULE_BASED | School geofence + speed drop. No child detector |

Do not quote a rival GitHub mAP as ours. Do not call Composio “the vision stack.”

---

## Architecture

```mermaid
flowchart LR
  subgraph phone [Phone Chrome or Safari]
    LENS[Windshield /field]
    WASM[ONNX WASM overlay]
    LENS --> WASM
  end
  subgraph azure [Azure App Service B3]
    API[FastAPI + static ICCC]
    CPU[YOLOv8s 640 ONNX CPU]
    PG[(Postgres or SQLite)]
    API --> CPU
    API --> PG
  end
  WASM -->|field JWT + boxes 250 ms| LIVE["/ws/field-live"]
  LIVE --> HUB[hub channel live]
  HUB --> DESK["ICCC /ws/live"]
  LENS -->|JPEG still| STILL["POST /ingest/phone"]
  STILL --> CPU
  CPU -->|UrbanEvent| DESK
```

Backend owns fusion, work orders, health scores, and roles. Frontends display; they do not invent those rules.

---

## Live demo (Azure)

1. Laptop: open the live URL → sign in as ICCC admin.
2. Overview → **Arm PIN** (QR / copy). Do not open `/field` on the same ICCC login.
3. Phone: Chrome or Safari → `https://app-urbansense-yngmbk.azurewebsites.net/field` → PIN + bus number + AUTO.
4. First overlay load can take 10–20 s (WASM + 640 weights). Hard-refresh if boxes never appear.
5. Phone overlay ticks **LIVE FIELD** on Overview. Official ticket appears in Events after the Azure still.
6. Second independent bus in 40 m / 6 h → `FLEET_CONFIRMED`. One phone cannot close a city ticket.

Demo credentials (seeded, demonstration only):

| Role | Email | Password |
| --- | --- | --- |
| SUPER_ADMIN | `superadmin@urbansense.local` | `UrbanSense@2026` |
| ADMIN | `admin@urbansense.local` | `UrbanSense@2026` |
| INSPECTOR | `inspector@urbansense.local` | `UrbanSense@2026` |
| OPERATOR | `operator@urbansense.local` | `UrbanSense@2026` |

QR examples: `urbansense://bus/BUS-042` · `urbansense://asset/ASSET-001` · `urbansense://work-order/WO-001`

---

## Quick start (local)

### 1. Backend

Windows PowerShell often blocks `activate.ps1`. Call the venv executable:

```bat
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or double-click `run-backend.cmd` in the repo root.

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
copy ..\.env.example .env
```

OpenAPI: http://127.0.0.1:8000/docs · Health: http://127.0.0.1:8000/health (`rdd` should be `REAL` when `backend/app/weights/rdd_india.onnx` is present).

If Docker Desktop is running:

```bash
docker compose up -d postgres
# DATABASE_URL=postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense
```

Without Postgres the API **falls back to SQLite**. Fusion still uses haversine.

### 2. Dashboard (dev)

```bash
cd dashboard
npm install
npm run dev
```

http://localhost:5173 — ICCC login as admin. Phone booth: http://localhost:5173/field (needs a PIN armed on the desk).

Vite copies `backend/app/weights/rdd_india.onnx` → `dashboard/public/weights/rdd_web.onnx` and ORT wasm → `public/ort/`.

### 3. Phone against local API

Run uvicorn `--host 0.0.0.0`. On the phone open `http://<this-PC-LAN-IP>:8000/field` after packaging the dashboard into `backend/static_dash`, **or** use the Vite origin if the phone can reach `:5173` and the `/api` proxy.

Flutter (optional WebView of the same booth):

```bash
cd mobile
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:8000
```

Windows desktop camera/GPS/IMU are often missing. Use an Android device or `/field` in the phone browser.

### 4. Tests

```bash
cd backend
python -m pytest -q
cd ../dashboard
npm run build
```

---

## Ship to Azure

```powershell
# packages dashboard → backend/static_dash, then azd deploy (not azd up)
scripts\ship-ui.ps1
```

- App Service `app-urbansense-yngmbk`, plan B3 (4 CPU / 7 GB, Always On), RG `rg-urbansense`, Southeast Asia.
- Do **not** change App Settings in parallel with a deploy (Oryx restart mid-build → 503).
- After ship: `/health` → `ok`, `rdd: REAL`; `/weights/manifest.json` → `imgsz: 640`.
- Stop `rg-urbansense` after the demo so student credits do not drain.

A GPU sidecar (Container Apps T4) is **not** in this stack. App Service cannot grow CUDA. See the honesty table.

---

## Features

- Observation vs fused **UrbanEvent**
- Deterministic spatial-temporal fusion (40 m / 6 h, source diversity; not averaged confidence)
- JWT + roles: SUPER_ADMIN, ADMIN, INSPECTOR, OPERATOR; field PIN scope
- Phone overlay → live desk boxes; Azure still → official event
- Assets (digital passport) + QR lookup
- Work orders + repair verification
- Sensor heartbeats (`POST /sensor-nodes/heartbeat`)
- Offline-first Flutter queue (JSON file) when the native app is used
- Demo seed: buses including BUS-042 / BUS-017, events, assets, work orders
- Privacy: restricted evidence flags, masked plates, audit logs (blur pipeline is **planned**)

---

## Tech stack

| Layer | Choice |
| --- | --- |
| ICCC | React 18 + Vite 6 + Leaflet + Recharts, served from `backend/static_dash` |
| Phone booth | Same SPA at `/field` + `onnxruntime-web` worker |
| API | FastAPI + SQLAlchemy 2 + Pydantic v2 + JWT |
| Data | PostgreSQL/PostGIS (Azure / Docker) or SQLite fallback |
| Realtime | `/ws/events`, `/ws/live`, `/ws/field-live` |
| Cloud RDD | `onnxruntime` CPU, `rdd_india.onnx` |
| Phone RDD | `rdd_web.onnx` (copy of the same family), WASM |
| Infra | Azure Bicep + `azd` (`azure.yaml`) |
| Optional native | Flutter WebView of `/field` |

---

## Folder structure

```
backend/     FastAPI + packaged ICCC (`static_dash`) + RDD weights
dashboard/   React ICCC / field source
mobile/      Flutter (same /field booth in a WebView)
ai/          Local camera / RTSP helpers — not App Service GPU
infra/       Azure Bicep
docs/        Jury script + PS coverage
scripts/     package-dashboard, ship-ui, local demo
shared/      Cross-client schemas
```

---

## API (selected)

| Method | Path |
| --- | --- |
| POST | `/auth/login` `/auth/field-booth` `/auth/field-join` |
| GET | `/health` `/ai/capabilities` `/weights/manifest.json` |
| GET/POST | `/sensor-nodes` `/sensor-nodes/heartbeat` |
| POST | `/ingest/phone` `/ingest/phone/probe` |
| GET | `/events` `/events/{id}` `/sensor-nodes` |
| POST | `/events/{id}/verify` `/work-orders` … |
| WS | `/ws/events` `/ws/live` (ICCC) · `/ws/field-live` (phone, field JWT) |

---

## Implemented vs planned

| Area | Status |
| --- | --- |
| Split ICCC vs `/field` | IMPLEMENTED |
| Phone WASM overlay + live desk | IMPLEMENTED (preview; official ticket is the Azure still) |
| Azure RDD still (YOLOv8s 640 CPU) | IMPLEMENTED (REAL) |
| Independent-bus confirm + absence expire | IMPLEMENTED (RULE_BASED) |
| Work order + repair verify/reopen | IMPLEMENTED |
| Azure App Service (API + dashboard) | IMPLEMENTED |
| Composio officer mail | DISABLED until Gmail OAuth + `COMPOSIO_NOTIFY_TO` |
| App Service GPU / live RTSP on Azure | NOT AVAILABLE (by platform) |
| Face/plate blur vision | FUTURE (flags + audit only) |
| Indian sign classifier | DISABLED |
| Waterlogging net | SIMULATED |

---

## Known limitations

- Overlay is a windshield preview. Do not treat phone boxes as the municipal record.
- Linux App Service has no GPU. Faster stills need a separate T4 host, not a plan SKU bump.
- SQLite fallback has no PostGIS GIST indexes (haversine still runs).
- Route delay charts use seeded durations when trips have no AVL.
- Default passwords and `SECRET_KEY` are for the jury host only. Never commit `.env` or API keys.

## License

SIH 2026 evaluation prototype. Demonstration data — not a live city deployment. Stop `rg-urbansense` after judging.
