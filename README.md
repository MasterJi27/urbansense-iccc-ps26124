<div align="center">

<img src="assets/readme/hero.svg" alt="SadakSaarthi — every bus is a road scanner. Every ticket needs a second witness." width="100%" />

<br />

**Public transport is the sensor fleet. The ICCC desk is the ledger.**

[Live demo](https://app-urbansense-yngmbk.azurewebsites.net/) · [8-minute jury walk](docs/JURY_8MIN.md) · [Model report](docs/MODEL_OPTIMIZATION_REPORT.md) · [Product brief](PRODUCT.md) · [Full project document](PROJECT.md)

<br />

![SIH 2026](https://img.shields.io/badge/SIH-2026-C45C26?style=flat-square)
![BEL PS 26124](https://img.shields.io/badge/BEL%20PS-26124-1F3A5F?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![YOLOv8s](https://img.shields.io/badge/YOLOv8s-ONNX%20CPU-FF6F00?style=flat-square)
![Azure](https://img.shields.io/badge/Azure-App%20Service-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)
![Tests](https://img.shields.io/badge/backend%20tests-234%20passed-2EA043?style=flat-square)

</div>

> [!IMPORTANT]
> **One bus can raise a report. One bus cannot close it.**
> A second independent bus must see the same defect within **40 m and 6 hours** before ICCC treats it as confirmed. The same bus, the same phone, and the cabin camera do not count twice.

---

## The 30-second version

| | |
| --- | --- |
| **What** | A city road-intelligence platform built on the public buses already on the road. |
| **How** | Windshield phone → one JPEG → Azure CPU YOLOv8s → fused `UrbanEvent` → second-bus confirmation → work order → repair verification. |
| **Why it is different** | Fleet confirmation, one official cloud still, a closed repair loop, and a truth label on every payload. |
| **Proof** | Kent holdout D40 AP50 **0.6591** vs **0.2555** shipped · **187/187** ONNX detections matched · **234** backend tests passing. |
| **Status** | Working SIH 2026 prototype. Honest about what is simulated. No labelled Indian field set yet. |

---

## Why this exists

Cities already own the buses, the drivers, the routes, and the inspection staff. What they do not have is one trustworthy chain from **a thing a bus saw** to **a municipal action**.

SadakSaarthi builds that chain. Every scheduled bus becomes a mobile sensing unit. A phone on the windshield watches the road and sends one still when it sees damage. Azure scores the official image. The backend fuses sightings into one event, waits for a second independent bus, and closes the loop with a work order, a repair, and a re-sense.

> [!NOTE]
> The visible wordmark is **SADAKSAARTHI**. Seeded emails, the Python package, and the Azure hostname still say `urbansense`; those are identifiers, not a second product.

It is deliberately **not**:

- continuous video uploaded to the cloud;
- a single-frame “AI says pothole” accusation;
- a dashboard that hides which numbers are real, seeded, or simulated;
- another model demo with no repair workflow behind it.

### Four design choices that matter

1. **The fleet is the sensor, not one hero camera.**
   A bus route gives repeat coverage for free. The same street is seen again tomorrow, and the day after.

2. **One official still, scored on CPU.**
   The phone overlay is a preview. The municipal record is the JPEG that Azure scores with YOLOv8s ONNX. No GPU, no video firehose, no 24×7 stream.

3. **Confirmation is a state machine, not a confidence score.**
   Two independent sources in the same 40 m / 6 h cell. A later clear pass can expire a rumour. After a repair, the next pass can verify it.

4. **Honesty is part of the API.**
   Every payload carries `ai_status`: `REAL`, `RULE_BASED`, `SEED`, `SIMULATED`, or `DISABLED`. The UI shows seed data and engine status separately.

---

## See it work

**Live:** https://app-urbansense-yngmbk.azurewebsites.net/

> [!NOTE]
> The App Service is stopped between demos so student credits do not drain. If the URL returns `403`, start `rg-urbansense`; the first request after a cold start can take about 20 seconds. The full walk is in [docs/JURY_8MIN.md](docs/JURY_8MIN.md).

### Five-minute tour

1. **ICCC desk** — open `/` and sign in as an officer.
2. **Arm a phone** — Overview → **Arm PIN**. A QR or six-digit PIN appears.
3. **Phone booth** — open `/field` on a phone, enter the PIN and bus number, allow camera and GPS, leave **AUTO — on detect** on.
4. **First sighting** — point at a pothole or a printed photo. The phone overlay is a live preview; Azure files the official still. The event starts as `UNVERIFIED`.
5. **Second witness** — a second independent bus in the same cell moves it to `FLEET_CONFIRMED`. Create a work order, mark the repair, and let the next pass verify it.

<details>
<summary><strong>Local demo credentials (development only)</strong></summary>

| Role | Email | Password |
| --- | --- | --- |
| SUPER_ADMIN | `superadmin@urbansense.local` | `UrbanSense@2026` |
| ADMIN | `admin@urbansense.local` | `UrbanSense@2026` |
| INSPECTOR | `inspector@urbansense.local` | `UrbanSense@2026` |
| OPERATOR | `operator@urbansense.local` | `UrbanSense@2026` |

These accounts work with `APP_ENV=development`. With `APP_ENV=production`, the login refuses the seeded password by design. The Azure jury host uses a private password; never commit it.

</details>

---

## Architecture

```mermaid
flowchart LR
  subgraph Phone["Windshield phone · /field"]
    CAM["Camera + GPS"]
    WASM["On-device ONNX WASM<br/>preview only"]
    CAM --> WASM
  end

  subgraph API["FastAPI · Azure App Service B3"]
    ING["Ingest + still gates"]
    RDD["YOLOv8s 640<br/>ONNX CPU"]
    FUSE["Fusion engine<br/>40 m / 6 h · source diversity"]
    EV[("UrbanEvent<br/>ledger")]
    WS["WebSocket hub"]
    ING --> RDD --> FUSE --> EV --> WS
  end

  subgraph Desk["ICCC desk · /"]
    MAP["Live map + event register"]
    WO["Work orders + repair verification"]
  end

  CAM -->|JPEG + GPS| ING
  WASM -.->|boxes, 250 ms| WS
  WS --> MAP
  EV --> WO
```

The backend is the source of truth. React and the phone display state; they do not invent fusion rules, roles, or work-order transitions.

| Layer | What it owns | Where |
| --- | --- | --- |
| Phone | camera, GPS, on-device preview, offline outbox | `dashboard/src/field` |
| API | auth, ingest, gates, fusion, work orders, audit, WebSocket | `backend/app` |
| Official vision | YOLOv8s 640 ONNX CPU, D00/D10/D20/D40 | `backend/app/services/rdd_cloud.py` |
| ICCC | React command register, map, analytics, print pack | `dashboard/src` |
| Data | PostgreSQL/PostGIS, or SQLite for local demos | `backend/app/models` |
| Infra | Linux App Service B3, Blob evidence, Bicep | `infra/` |

### The confirmation ledger

| Step | Trigger | What ICCC does |
| --- | --- | --- |
| `UNVERIFIED` | First sighting | Shows the event on the map. Does **not** dispatch. |
| `FLEET_CONFIRMED` | Second independent bus in 40 m / 6 h | Moves the event into the work-order queue. |
| `EXPIRED` | Enough later independent clear passes | Closes a rumour instead of sending a crew. |
| `ASSIGNED` → `RE_VERIFICATION` | Work order → repair submitted | Waits for a verify still from the next pass. |
| `RESOLVED` / `REOPENED` | Verify pass or fail | Closes the loop, or sends it back. |

Same bus, same phone, and cabin camera never count as the second witness.

---

## What is real — and what is not

Every API payload carries `ai_status`. This table is the short version of [docs/PS26124_COVERAGE_MATRIX.md](docs/PS26124_COVERAGE_MATRIX.md).

| Capability | Label | What it actually is |
| --- | --- | --- |
| Official road-damage ticket | **REAL** | Phone JPEG → Azure CPU YOLOv8s 640 ONNX. D00/D10/D20/D40. One still per event. |
| Phone windshield boxes | **RULE_BASED preview** | On-device `rdd_web.onnx` WASM. Road-band + IoU tracker. Same weights, not a new test mAP, not the municipal record. |
| Fleet confirm / absence / repair verify | **RULE_BASED** | Second independent bus in 40 m / 6 h. Later clear passes expire a rumour or verify a repair. |
| Still gates | **RULE_BASED** | GPS accuracy worse than 25 m → `400`; outside the jury corridor → `400`; speed-breaker asset within 25 m → `409`. |
| ANPR / vehicle tracking | **REAL** (optional AI layer) | Validated adapters in `ai/`; install `ai/requirements-ai.txt`. Plate + confidence + GPS + time; masked until ADMIN / INSPECTOR. Not the pothole ticket path. |
| Live desk ticks | **REAL transport** | Phone `/ws/field-live` → ICCC `/ws/live` plus REST poll. Tens of milliseconds, not 1 ms. |
| Officer email | **DISABLED** | Composio mails only on `FLEET_CONFIRMED`; needs Gmail OAuth and `COMPOSIO_NOTIFY_TO`. |
| Officer SMS | **REAL when configured** | Plain webhook `POST {"text","event_id"}` on `FLEET_CONFIRMED`. Empty URL = off; the ticket still saves. |
| Indian sign classifier | **DISABLED** | GIS missing-sign geofence only. No trained Indian sign net. |
| Waterlogging | **SIMULATED** | No flood model. |
| Person / child detector | **DISABLED** | School geofence + speed drop, not a child detector. |
| App Service GPU | **none** | Linux B3 is CPU-only. The phone overlay is WASM. |

> [!WARNING]
> Do not quote a rival GitHub mAP as ours, and do not call Composio “the vision stack.” The official pothole ticket is the RDD ONNX still. Everything else is labelled.

---

## The model

The deployed model is **`pothole_opt_v2`**, selected on a clean Kent pothole validation split and exported as a model-only ONNX swap on **4 November 2026**.

| | |
| --- | --- |
| Architecture | YOLOv8s, 640 px, FP32 ONNX, decoded without NMS in the app |
| Classes | D00 longitudinal crack · D10 transverse crack · D20 alligator crack · **D40 pothole** |
| File | [`backend/app/weights/rdd_india.onnx`](backend/app/weights/rdd_india.onnx) |
| SHA-256 | `649BBBDE79F75ED5E5CCB22AB5FFAA66E3B52A976A4094538B20CAD4EF0C305D` |
| Runtime | `onnxruntime` CPU inside FastAPI |
| Threshold | `CONF = 0.18` in production; **0.30** is the recommended tuning point once a labelled field set exists |
| Export source | `ml/models/road_damage/runs/pothole_opt_v2/weights/best.pt` (epoch 15 of 45) |

### Measured quality

| Split | Model | D40 AP50 | 4-class mAP50 |
| --- | --- | ---: | ---: |
| Kent holdout, 70 photos, never selected or trained on | shipped | 0.2555 | — |
| Kent holdout, 70 photos, never selected or trained on | **deployed v2** | **0.6591** | — |
| India test, 322 images, in-distribution | shipped | 0.6577 | 0.7039 |
| India test, 322 images, in-distribution | **deployed v2** | 0.6250 | **0.6845** |

The gain is in the exact failure mode the experiment targeted: **big, close-up potholes**. On the 70-photo Kent holdout, D40 AP50 rose from **0.2555 to 0.6591** (+0.404, 95% CI +0.305 to +0.492). On the India test split, D40 AP50 moved from **0.6577 to 0.6250** (−0.033, 95% CI −0.071 to +0.009, not significant).

> [!WARNING]
> **This is not field accuracy.** India val/test overlap the base checkpoint’s training data. The Kent holdout is clean but is UK phone photography, not Indian roads. There is still no labelled Indian field set. Quote **0.6591** as evidence that close-up pothole transfer improved, not as a claim about Indian roads.

### Export parity

The production gate is **decoded-detection agreement**, not raw-tensor equality.

| Check | Result |
| --- | --- |
| Images | 70 / 70 Kent holdout |
| Decoded detections matched | 187 / 187 |
| Worst matched IoU | 1.0000 |
| Confidence delta | 0.0000 |
| Raw tensor max abs diff | 0.0205 (expected CPU kernel difference) |

<details>
<summary><strong>Reproduce the export and parity check</strong></summary>

```powershell
.\.venv-train\Scripts\python.exe ml\scripts\export_rdd_onnx.py
.\.venv-train\Scripts\python.exe ml\scripts\verify_onnx_parity.py `
  --pt ml\models\road_damage\runs\pothole_opt_v2\weights\best.pt `
  --onnx ml\models\road_damage\runs\pothole_opt_v2\weights\best.onnx `
  --data data\rdd_pothole_opt_v2\data_kent_holdout.yaml --split test --limit 70
.\.venv-train\Scripts\python.exe ml\scripts\export_field_onnx.py
```

Ultralytics embeds an export date in ONNX metadata, so a re-export changes the checksum even when the graph weights are unchanged. Use the parity check, not the checksum alone, to decide whether a re-export is equivalent.

</details>

The full experiment, including v1/v2 selection, bootstrap intervals, and the deployment record, is in [docs/MODEL_OPTIMIZATION_REPORT.md](docs/MODEL_OPTIMIZATION_REPORT.md). The evaluation log is [ml/models/road_damage/EVAL.md](ml/models/road_damage/EVAL.md).

---

## Features

| ICCC desk | Field phone |
| --- | --- |
| Live map, event register, fusion view, heatmap | Browser camera and GPS, no app install |
| Work orders, repair submit/verify, re-sense prompt | 6-digit PIN + bus binding, phone-scoped JWT |
| Assets, digital passports, QR lookup | On-device ONNX preview with box tracker |
| Fleet, five camera bays, sensor heartbeats | AUTO still + short clip on detect, offline outbox, retry |
| Analytics, honest labels, print incident pack | Repair-due verify prompt within 40 m |
| Citizen report bridge and claim tickets | Field-live ticks to the ICCC desk |

**Platform**

- Observation vs fused `UrbanEvent`
- Deterministic spatial-temporal fusion (40 m / 6 h, source diversity; not averaged confidence)
- JWT + roles: `SUPER_ADMIN`, `ADMIN`, `INSPECTOR`, `OPERATOR`; field PIN scope
- Still gates: GPS accuracy, jury corridor, speed-breaker immunity
- CSV export for field tickets; seed rows skipped
- Local backup helper for PostgreSQL and SQLite
- Privacy flags, masked plates, audit logs; face/plate blur is **planned**
- Docker Compose for PostGIS, Redis, and MinIO; SQLite fallback for demos

---

## Quick start

**Fresh clone needs no training.** The deploy ONNX and honesty `metrics.json` files are tracked in git. Training weights (`*.pt`, runs, datasets) are gitignored. Run `scripts\build-ui.bat` once if you want FastAPI to serve the built dashboard; Vite dev mode does not need it.

**Prerequisites:** Python 3.12+, Node 20+, and optionally Docker Desktop (Postgres/PostGIS) and Azure CLI/`azd` for deployment.

### 0. One-click Windows

Double-click **`SadakSaarthi.exe`** in the repo root if it exists. It starts the backend, waits until it answers, and opens `http://127.0.0.1:8000/` (dashboard, `/field`, `/docs`). Close its window or press **Q** to stop. Logs go to `logs\backend.log`.

Build the launcher once with `deploy\windows\build-exe.bat`; build the UI once with `scripts\build-ui.bat`. Prefer a console? `scripts\start_demo.bat` does the same checks and also accepts `dev` (Vite) and `camera`.

### 1. Backend

```bat
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
copy ..\.env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell often blocks `activate.ps1`. Calling the venv executable directly avoids it.

- OpenAPI: `http://127.0.0.1:8000/docs` (development only; `APP_ENV=production` disables it)
- Health: `http://127.0.0.1:8000/health` — `rdd` should be `REAL`
- Dashboard: `http://127.0.0.1:8000/` after `scripts\build-ui.bat`, or use Vite at `:5173`
- Phone: `http://127.0.0.1:8000/field` after the build, or `http://localhost:5173/field` in Vite dev

With Docker Desktop:

```bash
docker compose up -d postgres
# DATABASE_URL=postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense
```

Without Postgres, the API falls back to SQLite in development. Fusion still uses haversine.

### 2. Dashboard in dev mode

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and copies `backend/app/weights/rdd_india.onnx` to `dashboard/public/weights/rdd_web.onnx`, plus ONNX Runtime WASM to `public/ort/`.

### 3. Phone against the local API

Run uvicorn with `--host 0.0.0.0`. On a phone on the same Wi-Fi, open:

```text
http://<this-PC-LAN-IP>:8000/field
```

Use the built dashboard served by FastAPI, or the Vite origin if the phone can reach port `5173` and the `/api` proxy. Allow camera and GPS; the first overlay load can take 10–20 seconds while the WASM weights load.

### 4. Tests

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q     # 234 passed
cd ../dashboard
npm run build
```

### Common fixes

| Symptom | Fix |
| --- | --- |
| `activate.ps1` is blocked | Call `.\.venv\Scripts\python.exe` directly. |
| `npm.ps1` is blocked | Use `npm.cmd run dev`, or run from `cmd`. |
| Port 8000 is already in use | Stop the old uvicorn process; do not start a second copy. |
| Phone cannot reach the API | Same Wi-Fi, `--host 0.0.0.0`, allow port 8000 through the firewall. |
| Overlay never shows boxes | Wait for the WASM weights, hard-refresh, and confirm `rdd_web.onnx` exists. |
| Login rejected on Azure | `APP_ENV=production` refuses the seeded demo password. Use the private host password. |

---

## API

The full OpenAPI schema is at `/docs` in development; `APP_ENV=production` disables it. Selected routes:

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/auth/login` · `/auth/field-booth` · `/auth/field-join` | Officer login, arm a phone, join with PIN |
| `GET` | `/health` · `/ai/capabilities` · `/weights/manifest.json` | Liveness, honesty map, deployed model metadata |
| `POST` | `/ingest/phone/still` · `/ingest/phone/probe` | Official still; pre-check without a ticket |
| `GET` | `/ingest/repair-due` | Verify-still prompt within 40 m of a repaired cell |
| `GET` | `/events` · `/events/{id}` · `/events/export.csv` | Register, detail, field CSV |
| `POST` | `/events/{id}/verify` · `/work-orders` … | Human endorsement and repair loop |
| `POST` | `/citizen/report` · `GET /citizen/tickets?claim=…` | Report without login; claim-token status |
| `GET/POST` | `/sensor-nodes` · `/sensor-nodes/heartbeat` | Fleet sensor health |
| `WS` | `/ws/events` · `/ws/live` · `/ws/field-live` | Desk events, live ticks, phone overlay stream |

---

## Repository map

```text
backend/        FastAPI API, fusion, seed, tests, built UI, deployed ONNX
dashboard/      React ICCC desk and the /field phone page
ml/             Road-damage training, evaluation, export, metrics, reports
ai/             Perception adapters (vehicles, ANPR, mapping) and camera helpers
data/           Datasets (not in git) — see data/README.md
deploy/         Azure zip builder, Windows launchers, local Kubernetes
infra/          Azure Bicep; azure.yaml points here
docs/           Jury script, coverage matrix, model report, deployment checklist
scripts/        Dev helpers: start_demo, build-ui, run-*, backup-db
shared/         Cross-client JSON schemas
assets/         Demo images and README artwork
storage/        Runtime evidence (not in git)
```

Training weights (`ml/models/**/*.pt`, `runs/`), datasets, `.env`, and the built `SadakSaarthi*.exe` files are not tracked.

---

## Deploy to Azure

```bat
deploy\azure\package-azure.bat
```

The script builds the dashboard, runs the backend tests (stops on failure), and writes `dist\azure\sadaksaarthi-api-<time>.zip` with a `.sha256`. The zip contains `backend/app`, `alembic`, the built `static_dash` UI, `models/road_damage/metrics.json`, `requirements.txt`, the RDD ONNX, and `build_info.json`. `.env`, `*.db`, `.venv`, and tests are excluded; the script refuses to write a zip if one slips in.

```powershell
az webapp deploy --resource-group rg-urbansense --name app-urbansense-yngmbk --src-path dist\azure\<the zip> --type zip
# or let azd package and deploy it:
azd deploy api
```

| | |
| --- | --- |
| Host | Linux App Service, plan **B3** (4 CPU / 7 GB, Always On) |
| Resource group | `rg-urbansense`, Southeast Asia |
| Runtime | `PYTHON|3.12` |
| Post-deploy check | `/health` → `ok`, `rdd: REAL`; `/weights/manifest.json` → `imgsz: 640` |
| Cost control | Stop `rg-urbansense` after the demo; a stopped app returns `403` |
| GPU | **None.** App Service cannot grow CUDA; a T4 sidecar is a separate host. |

Do not change App Settings while a deploy is running — the Oryx restart can answer `503`. Full checklist: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Limits, stated plainly

- **No labelled Indian field set.** The model is measured on RDD India (in-distribution) and a clean UK Kent holdout; neither is a field guarantee.
- **The phone overlay is a preview.** The official record is the Azure still, not the box you see on the windshield.
- **One still plus one short clip per event.** There is no continuous video upload. A longer pre-roll + 60-second event clip is on the roadmap; the deployed path records a ~2-second rolling clip with the still.
- **CPU only on App Service.** Faster inference needs a separate GPU host; a plan SKU bump does not add CUDA.
- **SQLite fallback has no PostGIS GIST indexes.** Haversine fusion still runs.
- **Some analytics are seeded or simulated.** Route delay and OD are empty without a real AVL feed; waterlogging is simulated; Indian signs are disabled.
- **Demo security is demo security.** Default passwords and `SECRET_KEY` are for local/jury use. `APP_ENV=production` refuses the seeded password.
- **No load test, penetration test, or dependency audit has been run.** This is an evaluation prototype, not a live city deployment.

---

## Documentation

| Document | What it answers |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | Product brief and PPT-ready story |
| [PROJECT.md](PROJECT.md) | Full problem, data model, fusion, APIs, status |
| [docs/JURY_8MIN.md](docs/JURY_8MIN.md) | Eight-minute jury walk, step by step |
| [docs/PS26124_COVERAGE_MATRIX.md](docs/PS26124_COVERAGE_MATRIX.md) | Every BEL requirement, mechanism, status, and evidence |
| [docs/MODEL_OPTIMIZATION_REPORT.md](docs/MODEL_OPTIMIZATION_REPORT.md) | Full pothole experiment, metrics, parity, deployment |
| [ml/models/road_damage/EVAL.md](ml/models/road_damage/EVAL.md) | Honest evaluation log, including what the numbers do not prove |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Azure build, settings, post-deploy checks, rollback |
| [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) | Perception adapters, vehicles, ANPR, mapping |
| [backend/app/weights/README.md](backend/app/weights/README.md) | Weight checksum, measured quality, parity, rollback |

---

## Credits

Built for **SIH 2026 · BEL Problem Statement 26124**.

The road-damage model builds on RDD2022 / CRDDC and the University of Kent pothole photographs (CC BY 4.0), trained with [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) and served with [ONNX Runtime](https://onnxruntime.ai/). The stack also uses FastAPI, React, Leaflet, Recharts, PostgreSQL/PostGIS, and Azure App Service.

This repository is an evaluation prototype. Demonstration data is labelled; third-party datasets, weights, and libraries keep their own licences.
