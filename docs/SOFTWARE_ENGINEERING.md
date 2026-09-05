# Software engineering approaches — UrbanSense

SIH 2026 · BEL PS 26124  
This note is the engineering README for the PPT / jury: **how we build**, not only which libraries we import.

The product is a **modular monolith**. The FastAPI backend is the single source of truth. Flutter and React never duplicate fusion, work-order state, health scores, or roles.

Azure App Service hosts the **API + ICCC dashboard** as one origin (`https://app-urbansense-yngmbk.azurewebsites.net/`). Flutter stays on the phone. YOLO weights are optional on the App Service (CPU, no live GPU stream). Student credits: stop the resource group after the demo.

---

## 1. Approaches to put at the top of the PPT

These are the production techniques. Stack names come after.

1. **Backend as source of truth.** Fusion, scoring, work orders, bridge health, and RBAC live in one API. Clients display; they do not invent business rules.
2. **Observation → Event → Work order.** A phone report is an observation. Nearby compatible reports fuse into one UrbanEvent. An officer endorses it. A ward work order closes the loop. Re-sense after repair.
3. **Deterministic spatial-temporal fusion.** ~40 m, 6 h, compatible type, source diversity. Score = max(confidence) + diversity + human-verify bonuses. Not an average. Not a claim of statistical certainty.
4. **Honesty-by-design.** Every payload carries `ai_status`: REAL, RULE_BASED, SEED, SIMULATED, DISABLED. Seed data is labelled seed. The engine for that event type can still be REAL. Dual labels on the UI.
5. **Split intelligence (edge contract).** Phone = IMU + GPS trigger, ~1 KB JSON, RULE_BASED. Backend still = REAL neural (YOLO RDD, YOLOv8n + ByteTrack, ANPR). No live YOLO on a 2 GB phone. No continuous video upload.
6. **Human-in-the-loop.** ICCC VERIFY / SEND TO WARD. The system assists authorities; it does not accuse.
7. **Privacy by design (DPDP).** Plates masked until ADMIN / INSPECTOR. Faces never shown. Evidence restricted. Logs must not dump plate values. India-region host when Azure is wired.
8. **Offline-first phone.** Queue on disk, survives reboot, SYNC when the bus has network.
9. **Graceful degradation.** Postgres + PostGIS when available; SQLite fallback so the demo still runs. Fusion still uses haversine.
10. **Closed-loop state machine.** DETECT → VERIFY → WORK ORDER → REPAIR → RE-VERIFICATION → RESOLVED or REOPENED.

---

## 2. Architecture style

**Modular monolith**, not microservices.

```
Flutter phone  ──HTTPS + JWT──►  FastAPI
React ICCC     ──HTTPS + WS───►  FastAPI
Future CCTV    ──same Observation JSON──► FastAPI
                      │
                      ▼
              PostgreSQL / SQLite
```

Layers inside the API:

| Layer | Folder | Owns |
| --- | --- | --- |
| HTTP / OpenAPI | `backend/app/api/routes/` | Auth, events, ingest, fleet, assets, work orders, bridge, analytics, WS |
| Domain services | `backend/app/services/` | Fusion, asset-watch, bridge SHM, road health, observations, QR, audit |
| Persistence | `backend/app/models/` | SQLAlchemy entities |
| Contracts | `backend/app/schemas/` | Pydantic request/response |
| Security | `backend/app/security.py`, `deps.py` | JWT, role ranks |
| Config | `backend/app/config.py` | `pydantic-settings`, env |

Replaceable **engine interfaces** for fusion / detectors so a YOLO box or a rule engine can be swapped without rewriting the event model.

Same `Observation` JSON for phone today and bus CCTV tomorrow. That is **one evidence model**, not a new product per sensor.

---

## 3. Domain model (DDD-lite)

Not a full DDD rewrite. We keep a small, strict language:

- **Observation** — one sensor report (phone IMU/GPS, still, inspector, later CCTV).
- **UrbanEvent** — fused municipal record (the folio the officer stamps).
- **Asset passport** — persistent infrastructure ID + QR + condition + linked events.
- **WorkOrder** — ward task with repair evidence and re-verification.
- **Sensor node** — phone bound to a bus QR.
- **Bridge health log** — longitudinal RMS / crest / f_dom, EMA baseline.

Compatible event types are an explicit map in `fusion.py` (pothole ↔ road damage, vibration ↔ anomaly, and so on). Incompatible types do not collapse into one ticket.

---

## 4. Fusion as an algorithm, not “AI magic”

Established technique: spatial-temporal clustering of crowdsourced reports.

Project-specific:

- configurable distance and time (`fusion_max_distance_meters`, `fusion_max_time_seconds`)
- source diversity bonus
- human verification bonus
- **no averaging of confidence**
- fusion reason string stored on the event (“how determined”)

This is the technique to name on the architecture slide: **deterministic multi-source fusion with an inspectable reason**.

---

## 5. Adapter pattern for perception

Boost repos are a **component library**. Their UIs, databases, and auth were not merged.

Adapters (see `docs/AI_INTEGRATION.md`):

- YOLOv8 RDD → pothole / road damage
- YOLOv8n + ByteTrack → vehicles / persons
- fast-alpr + fast-plate-ocr → plate detect + OCR
- track-level character vote
- rule adapters: LOS congestion, bbox pedestrian risk, rash speed, asset-watch, bridge SHM

Capabilities endpoint tells the UI what is REAL vs DISABLED vs SIMULATED. Turkish sign weights stay `enabled: false`. Waterlogging has no model.

---

## 6. Security and roles

- JWT bearer auth (`python-jose`).
- Ranked RBAC: OPERATOR < INSPECTOR < ADMIN < SUPER_ADMIN (`require_roles` in `deps.py`).
- Plate reveal only at inspector/admin rank.
- CORS allowlist for localhost; credentials on.
- Audit service for sensitive actions.
- Demo users are seeded and labelled demonstration data.

Planned on Azure: Entra ID for ICCC officers instead of demo passwords.

---

## 7. Workflow and state machines

Work-order lifecycle is tested (`backend/tests/test_lifecycle.py`):

observation → event → work order → repair → `RE_VERIFICATION` → verify → resolved (or reopen).

Event actions: verify, reject, create work order.

Bridge SHM: NORMAL → WATCH → ANOMALOUS → INSPECTION REQUIRED, with auto work order on CRITICAL. Screening, not certified inspection.

QR identity: `urbansense://bus/…`, `urbansense://asset/…`, `urbansense://work-order/…`.

---

## 8. Reliability, edge, and data

- Offline queue on the phone (`pending_observations.json`, cap, reboot-safe).
- Heartbeat ~12 s.
- Detector throttles (example: congestion needs persistence across frames; ANPR OCR throttled per track).
- WebSocket hub pushes `event.created` to the register.
- Alembic for schema; startup `create_all` + small SQLite column patches for demo machines.
- Docker Compose Postgres when Docker is available; otherwise SQLite.
- Dashboard code-split (lazy routes, vendor / leaflet / charts chunks).

---

## 9. Testing and honesty contract

Pytest covers fusion, geo, auth, asset-watch, perception rules, AI integration, and work-order lifecycle.

Honesty contract (`dashboard/src/honesty.js` + `extra.ai_status`):

| Label | Meaning |
| --- | --- |
| REAL | Neural forward pass ran |
| RULE_BASED | Deterministic rule on real signals |
| SEED | Demo/seed payload (engine may still be REAL) |
| SIMULATED | Mock path (waterlogging) |
| DISABLED | Adapter present, not turned on (Indian signs) |
| EXPERIMENTAL | Runs, not evidence-grade (uncalibrated speed) |

UI must show seed ≠ engine. Tests and the coverage matrix (`docs/PS26124_COVERAGE_MATRIX.md`) are the audit trail for the jury.

---

## 10. API-first and contracts

- OpenAPI at `/docs`.
- Pydantic schemas at the boundary.
- Shared observation shape so phone, inspector, and future CCTV post the same JSON.
- `GET /ai/capabilities` is the machine-readable honesty map.
- `GET /health` for process liveness.

---

## 11. What we are not doing

- Microservices per detector
- Federated learning on the phone
- Averaging confidences into “certainty”
- Treating Azure OpenAI as the pothole model
- Claiming a live city deployment

---

## 12. One sentence for the engineering slide

Modular monolith, API as source of truth, observation-to-event fusion, honesty labels, DPDP masking, offline-first phone, human endorsement, closed-loop work orders — hosted later on Azure for Students, not as a replacement for the models.
