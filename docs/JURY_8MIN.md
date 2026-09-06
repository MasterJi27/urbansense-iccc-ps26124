# UrbanSense — 8-minute jury script (BEL PS 26124)

Live: https://app-urbansense-yngmbk.azurewebsites.net/

**USP:** Independent-Bus Confirmation Ledger. Fleet confirms. One bus cannot.

## Phone check (2 min, before the 8-min walk)

1. Phone Chrome/Safari: https://app-urbansense-yngmbk.azurewebsites.net/field
2. PIN + bus + allow camera and GPS. Leave **AUTO — on detect** (not 1 s burst).
3. Point at a pothole/crack (or a printed photo). Ticket should appear on ICCC without tapping FILE REPORT.
4. Settings → About: pedestrian overlay is **DISABLED**. Cloud RDD is **REAL**.

## Login

1. Open the live URL.
2. Sign in as ICCC admin (`admin@urbansense.local` / seeded password on the login card).
3. You land on Overview. The red strip is the product: first sighting vs 2nd bus confirm.

## One button

4. Click **JURY RUN (8 min)**. Wait for the checklist. Each row is a live event URL.

## Walk the PS lines (do not skip)

5. **Pothole first sighting** — open the first checklist code. Status `UNVERIFIED`. BUS-042 FRONT. Payload is `SEED`; pothole engine is still `REAL`.
6. **Pothole fleet-confirm** — same public code, now `CONFIRMED` / `FLEET_CONFIRMED`. BUS-017 is the second independent bus. Same bus cannot self-confirm.
6b. **Absence is evidence** — three later buses pass the confirmed cell and do not re-trigger. Confirm still stands. A *separate* one-bus rumour nearby expires (`EXPIRED`) — we will not dispatch it. After a repair mark, two later buses set `REPAIR_VERIFIED`. RULE_BASED. Not “the pothole vanished.”
7. **Map** — Overview map: the fused pothole is the larger marker. Two buses, one UrbanEvent, ~1 KB alerts, not video.
8. **GIS missing sign** — SIGN-183, three non-confirming passes. `RULE_BASED`. Not a neural “absence” detector. Signs stay `DISABLED` as a trained Indian model.
9. **Congestion** — LOS persistence, `RULE_BASED`. Not a traffic forecast.
10. **Rash + plate** — ANPR fields present. Plate is masked (`DL8C••••`). Line on the pack: **ASSISTS AUTHORITIES — DOES NOT ACCUSE**.
11. **Cabin split** — CABIN bay is `OTHER`, never `POTHOLE`. Cabin cannot invent a road defect.
12. **Waterlogging** — explicit `SIMULATED`. No flood net.

## Close the loop

13. Event Detail → **Print incident pack** (browser print, no PDF library): GPS, buses, honesty, masked plate.
14. **Create work order**. Work Orders cards sort by repair priority score.
15. Fleet: BUS-042 / BUS-017 show five bays. Cabin is labelled **cabin only**.
16. Analytics honesty banner: heatmap REAL-derived; OD / delay SIMULATED until AVL.
17. Settings: “Fleet confirms. One bus cannot.” Signs `DISABLED`, waterlogging `SIMULATED`.

## What we will not claim

No Indian sign model, no waterlogging net, no raw video to Azure, no GPU YOLO on App Service, no live AVL.
