# SadakSaarthi — Product brief

SIH 2026 · BEL **PS 26124** · Delhi ICCC  
**Live:** https://app-urbansense-yngmbk.azurewebsites.net/

Public-transport vehicles are **mobile sensing units**. The phone on the windshield detects; Azure writes the official ticket; the ICCC desk only acts when **a second independent bus** confirms. One bus cannot close a city ticket. Cloud stores **alerts and short evidence**, not a 24×7 video stream.

Visible wordmark: **SADAKSAARTHI**. Login emails and the Azure hostname still say `urbansense` — identifiers, not a second product.

Use this file for PPT slides. Engineering runbook: [README.md](README.md) · Jury walk: [docs/JURY_8MIN.md](docs/JURY_8MIN.md).

---

## Who uses it

| Surface | Who | How |
| --- | --- | --- |
| ICCC desk `/` | Depot / ICCC officer | JWT login |
| Phone booth `/field` | Windshield phone | 6-digit PIN from the desk |

Do not open `/field` on the same browser as the ICCC login. Flutter, if used, loads the same `/field` page. It is not a second detector.

---

## What is live today

**USP:** Fleet confirms presence. Fleet also confirms absence. Same bus cannot self-confirm.

| Capability | Honesty | What it is |
| --- | --- | --- |
| Official pothole / crack ticket | **REAL** | Phone JPEG → Azure App Service → YOLOv8s 640 ONNX **CPU** (India RDD D00/D10/D20/D40) |
| Windshield overlay boxes | **RULE_BASED** preview | On-device WASM (`rdd_web.onnx`). Official event is the Azure still |
| Held-out test | mAP@0.5 **0.6189** | 323-image India RDD split. Not certified field accuracy |
| AUTO capture | shipped | Default **on detect** (rising edge). Still + short clip; no tap needed |
| Fleet confirm / expire / repair-verify | **RULE_BASED** | Second bus in **40 m / 6 h**. Later clear passes expire rumours or verify repair |
| Five camera bays | **REAL** contract | FRONT / REAR / LEFT / RIGHT / CABIN. Cabin **never** scores a road defect |
| Missing divider / zebra / sign | **RULE_BASED** | GIS asset-watch (N non-confirming passes). No Indian sign net |
| ANPR on still | **REAL** | Plate + confidence + GPS + time. Masked until ADMIN / INSPECTOR. Assists authorities — does not accuse |
| Work orders | **REAL** | Verify → work order → repair → re-sense |
| ICCC map, heatmap, print pack | **REAL** transport | Leaflet, WebSocket ticks, browser print. Heatmap from fused events |
| Officer email | **DISABLED** until Gmail is connected | Composio mails only on `FLEET_CONFIRMED` |
| Waterlogging model | **SIMULATED** | No flood net |
| OD / route delay | **SIMULATED** | Empty without a real AVL feed |
| Person / child net | **DISABLED** | School VRU = geofence + speed, not a child detector |
| App Service GPU | none | B3 CPU. Overlay is WASM |

Every payload carries `ai_status`: **REAL** / **RULE_BASED** / **SEED** / **SIMULATED** / **DISABLED**.

---

## Evidence clip — now vs next

BEL asks for edge analysis and **no continuous video**. We keep that. We only lengthen the **one clip that belongs to one event**.

| | Now (shipped) | Next (we will add) |
| --- | --- | --- |
| Trigger | AUTO on detect, with the JPEG still | Same trigger — not a always-on camera |
| Length | ~**2 s** rolling WebM | **Pre-roll + 60 s after** the UrbanEvent is created |
| What ICCC plays | Hold the still to play the live clip | One approach-to-aftermath clip on the event |
| Upload | One clip per ticket, Blob `evidence` | Still one clip per ticket — **not** 60 stills/minute |
| Hard no | Cadence `track1s` (1 Hz for 1 min) | Still banned on the jury walk — that path fills CPU and Blob |

**Next clip, in one line:** when a ticket is born, keep the seconds *before* the detect and record until **one minute after**. Upload that single file. Cap size on the phone; reject oversize on the API. JPEG remains the official RDD still.

---

## What else we will add (eight items)

Realistic, countable, no new circus of models. India RDD **0.6189** stays the promotion floor.

1. **One-minute event clip** — as above. Pre-event buffer + 60 s after. One Blob object per event.
2. **Speed-breaker immunity** — pin known breakers/rumbles on the demo corridor. RDD pothole *on* that pin + no IMU pothole-hit → **do not** open a ticket.
3. **GPS quality gate** — no ticket if the fix is missing or accuracy is worse than **25 m**.
4. **Officer ping on confirm** — WhatsApp or SMS when status becomes `FLEET_CONFIRMED` (Gmail path already exists).
5. **Next-pass repair photo** — after a work order is marked repaired, the next `/field` phone in that 40 m cell is prompted for a verify still.
6. **PWD CSV** — public code, lat/lon, bus, time, honesty, status. Excel, not a screenshot.
7. **Demo-corridor geofence** — AUTO ingest only on the jury route so home streets do not spam the desk.
8. **Live vs seed filter** — map default = phone-born events. Seed rows stay for the 8-minute script, off the live layer.

---

## What we will not add

Indian sign classifier, waterlogging net, child/person detector, live CCTV wall, GPU YOLO on App Service, 24×7 video upload, federated learning, collapse prediction.

---

## PPT closer

> Every scheduled bus is a daily road scanner. The still is scored on CPU. The clip is one minute around the event, not a stream. A second bus must agree before ICCC dispatches.
