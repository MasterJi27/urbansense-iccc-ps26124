# UrbanSense Structural Pulse — Continuous Bridge-Health Screening (not collapse prediction)

> PS 26124.5 — Buses as mobile structural sensors. Correct framing per literature review 2026.

## 1. Positioning — one sentence that wins the jury

**UrbanSense Structural Pulse: Continuous bridge-health screening using the buses already crossing the city.**

- Sense: Smartphone IMU + GPS records bridge-crossing dynamics.
- Learn: Build a normal vibration signature per structure from repeated fleet passes.
- Flag: Persistent deviations trigger **inspection recommendation** — not an automatic safety judgment.

Never say: “We predict bridge collapse from phone acceleration.”

## 2. System-level innovation (what is actually novel)

Research already shows smartphone drive-by bridge monitoring works (modal estimation, crowdsensing). IoT drive-by with accel+GPS+4G+cloud was demonstrated 2023. So sensor novelty = 5/10.

Our novelty is **system + deployment**:

```
               PUBLIC BUS
                   │
     ┌─────────────┼─────────────┐
     ↓             ↓             ↓
  Camera        GPS           IMU
     │           │             │
 Road defects  Location    Vibration
     │           │             │
     └───────────┼─────────────┘
                 ↓
            URBANSENSE
                 ↓
     ┌───────────┴───────────┐
     ↓                       ↓
 Road condition        Structure health
     │                       │
  Potholes etc.        Bridge/ROB/Flyover
```

One bus simultaneously: road surface + bridge signature + traffic + pedestrian → **urban event intelligence**, not feature accumulation.

Reuse: `Observation → Fusion → UrbanEvent` stays. `Bus A+B+C → abnormal bridge signature → spatial+temporal+source diversity → STRUCTURAL ANOMALY EVENT`.

## 3. Per-structure baseline — the core data structure

```
BRIDGE-DEL-042
  Type: ROB / Flyover / Bridge, span 180m, crossings 17/day
  Dynamic baseline (EMA 0.92/0.08):
    dominant_freq, RMS, spectral power, crest
  Environmental context:
    speed, direction, time, temp (later)
  Health state:
    NORMAL → WATCH → ANOMALOUS → INSPECTION REQUIRED
```

Every crossing updates longitudinal history (`BridgeHealthLog` 80 pts). Not one-off measurement.

Code: `backend/app/models/shm.py:BridgHealthLog`, `asset.py:shm_baseline_*`, `bridge_shm.py:extract_features()` RMS/peak/crest + FFT f_dom, EMA update `0.92/0.08`, health_score -6/-12.

## 4. What we actually measure — honest answer

> “We aren't measuring structural stress directly. We're extracting repeatable dynamic features (spectral characteristics, vibration energy, crest) while crossing a known structure and tracking evolution over time.”

Challenge: distinguish bridge vs bus suspension/speed/tyre/load/road-profile/temp/joints. Research flags these as major issues. Answer:

- Control for route direction, speed, repeated observations
- Require **persistent anomaly across multiple buses/crossings** before escalation (fusion diversity bonus `services/fusion.py:152`)
- Joint vs span: crest≥4.5 + peak≥0.7 → `FLYOVER_JOINT`, else `BRIDGE_ANOMALY`

## 5. Screening layer — not certified inspection

Q: Certified system? A: Correct — **continuous screening & early-warning layer, not replacement for certified inspection.** Benefit: data-driven signal to inspect vs discovering at periodic inspection after visible deterioration.

Why buses vs fixed sensors? “Not another sensor network to maintain. Vehicles already crossing daily become temporary sensing nodes. Network-scale without installing on every structure.” Literature supports this.

## 6. Demo that is feasible & honest

2-3 phones → same flyover (BRG-ITO / FLY-AIIMS) → extract f_dom/RMS → establish baseline → inject anomalous vibration (or heavy speed) → anomaly score → GIS asset yellow/red → “Recommend inspection” + auto WO-BR-*.

Not: collapse countdown.

## 7. Presentation slide — use this verbatim

**Continuous Structural Health Screening — Buses become mobile structural sensors.**

Sense — IMU+GPS | Learn — per-structure signature | Flag — persistent drift → inspection

## 8. Scores (honest)

Impact 9.5/10, Fit 9.5/10, Depth 9/10, BEL relevance 9/10, Demo 9/10, Science novelty 5/10, System novelty 8.5/10, Difficulty 8/10.

Warning: Do not prove collapse in SIH — build screening demonstrator only.
