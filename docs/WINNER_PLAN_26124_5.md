# UrbanSense 26124.5 — Winner Plan (Bridge SHM + Urban Intel) — Proper Execution

> SIH 2026 • PS 26124 BEL • Extended with Bridge/Flyover SHM via phone accel + bus GPS
> Goal: SIH Winner — not just demo, but deployable, DOPT/DPDP compliant, low-phone ready

## 0) Why we will win — 20x insight
- Others: pothole CNN + table. We: **crowd SHM + fusion + closed-loop** — bus = 100x/day bridge sensor, no extra hardware.
- Zero QR on bridge (70m geofence), offline PWA <1.5MB, on-device blur → DOPT/DPDP safe.
- Every claim is RULE_BASED + transparent, never "AI magic".

## 1) System Architecture (single source of truth = FastAPI)
```
Flutter (Sensor+Inspector, accel 50Hz, GPS 1Hz, offline queue)
  → POST /bridge/batch (~1KB, RMS/peak/crest+FFT) or POST /observations
    → FastAPI modular monolith (fusion.py, bridge_shm.py, asset_watch.py)
      → PostgreSQL+PostGIS (or SQLite) + BridgeHealthLog, UrbanEvent, WorkOrder
        → WebSocket → React Fleetory dashboard
  → Edge: bus CCTV optional, phone is fallback
```
Backend only owns fusion/health/predictive. Frontends never duplicate logic.

## 2) Phases — 4 sprints to 20 Sept

### Sprint 1 (Done 70%): Foundation + Fleetory UI
- styles.css tokens, App.jsx grouped nav, topbar Ctrl+K
- Overview, LiveMap, Events, EventDetail, Fleet, Assets, RoadHealth, Analytics, Sensors
- AssetDetail, Users, Settings polish (today)
- BridgeHealth v1 (RMS/crest)

### Sprint 2 (This week): SHM v2 + Polish — IN PROGRESS → DONE today
- [x] bridge_shm.py v2: FFT f_dom, temp-comp, EMA 0.92/0.08, history log
- [x] Predictive days (linear slope to 0.55g), auto WO-BR-* on CRITICAL
- [x] BridgeHealth.jsx: sparkline history, freq badge, auto WO
- [x] Mobile auto geofence (80m, ≥180 samples)
- [ ] Visual joint photo (Inspector → WO evidence) — next 2h
- [ ] Waterlogging under-deck (existing WATERLOGGING type reuse)

### Sprint 3 (Next 5 days): Hardening + Field QA — DONE (polish) / field QA pending
- [x] Skeletons — `dashboard/src/components/Skeleton.jsx:1` (`SkeletonCard:11`, `SkeletonKPI:23`, `SkeletonGrid:33`), `dashboard/src/styles.css:212` shimmer; used `Overview.jsx:5,46`, `EventDetail.jsx:6,34`, `AssetDetail.jsx:5,14`, `Settings.jsx:3,17`
- [x] Toast — `dashboard/src/components/Toast.jsx:7` (`ToastProvider:7`, `useToast:43`), `dashboard/src/App.jsx:15,206`, `dashboard/src/styles.css:224`, `EventDetail.jsx:5,12,18`
- [x] Responsive drawer — `dashboard/src/App.jsx:37` state / `117` overlay / `158` hamburger / `69` auto-close, `dashboard/src/styles.css:68` hamburger / `70` overlay / `122` `max-width:760` fixed drawer
- [x] Code-split — `dashboard/src/App.jsx:17` `lazy(Overview/LiveMap/Analytics/BridgeHealth)` + `178` `Suspense`, `dashboard/vite.config.js:21` `manualChunks:{vendor:26,leaflet:27,charts:28}`
- [x] Mobile fixes — `dashboard/src/styles.css:108` `@media 1280` + `122` `@media 760` (grids →1fr: `fleet-grid:109,130`, `bridge-visual-grid:116`, `event/asset-detail-grid:113,133`, `search:128`, `topbar:58` wrap, `content:141`)
- Field test: 2 phones (good + 2GB low-end) on 1 bridge, 10 passes, tune 70m→55m if drift — pending
- Low-phone battery 50Hz duty 70% / heartbeat 12s + DPDP blur/30d/audit + docs (`AI_INTEGRATION.md`, `COVERAGE_MATRIX`) — pending

### Sprint 4 (Final): SIH Deliverables
- PPT 12 slides (problem → crowd SHM wow → architecture → demo → impact)
- 3-min video: phone on bus → bridge batch → map red dot → WO
- Idea submission + GitHub + 2-min live demo script

## 3) 60 Agents — 8 squads (realistic parallel)

| Squad | Agents | Owns | Files |
|---|---|---|---|
| Design System | 8 | tokens, layout, skeletons, responsive 760/1280 | styles.css, App.jsx |
| Core Dashboard | 10 | Overview/LiveMap/Events/Detail/BridgeHealth charts | pages/*.jsx |
| Bridge SHM | 10 | FFT, baseline, predictive, logs | services/bridge_shm.py, models/shm.py, seed.py |
| Mobile | 10 | accel, geofence, offline, joint photo | mobile/lib/main.dart |
| Backend GIS | 8 | PostGIS, fusion, health recompute | models/asset.py, services/fusion.py |
| QA/Compliance | 6 | low-phone, DPDP, audit | tests/, docs/ |
| DevOps/MCP | 4 | compose.io, CI, seed | opencode.json, docker-compose.yml |
| Pitch | 4 | PPT, video, script | docs/*.md |

Each squad = 1 lead + Task tool subagents. Daily sync 15 min.

## 4) Deliverables & Done Definition
- `npm run build` passes (<800kB) + `pytest 41 passed`
- 3 bridges seeded (BRG-ITO 62, FLY-AIIMS 74, BRG-DHAULA 74) + 4 SHM events
- Bridge page: health bars + sparkline + map + simulate buttons work offline queue
- No QR scan on bridge — GPS auto, phone 2GB works
- PPT + video ready 18 Sept

## 5) Risks & Mitigation
- GPS drift 15m → 70m geofence (tuned field) + snap to centroid
- Vibration noise (suspension) → crowd baseline, not single phone; ratio not absolute
- DOPT scan fatigue → zero scan on bridge, one-time bus bind only
- Overclaim SHM → label RULE_BASED everywhere, not certified modal

## 6) Immediate Next (today, 4h)
1. Visual joint photo flow (2h)
2. Under-bridge waterlogging reuse (1h)
3. Full visual QA 760/1280 + lighthouse (1h)
4. Update docs/AI_INTEGRATION.md + coverage matrix

Approve → I execute strictly squad-wise, no random edits.
