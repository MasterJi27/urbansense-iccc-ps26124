# Research basis and engineering choices

UrbanSense does **not** copy papers or claim their reported accuracies. The literature informed *what to build*, not *what to claim*.

## A. Established techniques (used as design constraints)

| Area | What we took | Where it lives |
| --- | --- | --- |
| Smartphone IMU + GPS road sensing | Event-centric capture (not continuous video); store lat/lon/accuracy/timestamp/speed | Flutter sensor mode + Observation model |
| Crowdsensing / multiple phones | Many observations of one defect | Observation vs UrbanEvent split |
| Spatial-temporal clustering | Distance + time windows for association | `SpatialTemporalFusionEngine` |
| Dashcam / camera damage detection | Pluggable `DetectionEngine`; edge-first bandwidth | `ai/urbansense_ai` |
| Heterogeneous sources (SafeCity-style) | `source_type`: PHONE, BUS_CCTV, ROAD_CCTV, IOT, INSPECTOR | Ingest gateway |
| Geospatial monitoring | PostGIS when Postgres is available; haversine always | `app/geo.py`, Docker PostGIS |

## B. Project-specific integration (SIH 26124)

- Digital passport + QR for buses, assets, work orders
- Closed-loop repair: DETECT → VERIFY → WORK ORDER → REPAIR → RE-SENSE
- Transparent fusion score (max confidence + diversity + human bonus — **not** an average, **not** a p-value)
- Adaptive device modes: EDGE_AI / LIGHTWEIGHT_EDGE_AI / CAPTURE_AND_SENSOR
- Sensor health heartbeats
- Rule-based road health score
- Privacy architecture: event clips over raw video, evidence flags, audit log

## C. Future research ideas (not in this MVP)

- Learned fusion / entity resolution for observations
- On-device TFLite pothole and sign models with real precision-recall reporting
- Multi-object tracking for congestion and pedestrian risk
- Production LPR OCR with calibrated confidence
- Face/plate blurring as an actual vision pipeline
- Origin-destination analytics from real AFC/AVL feeds
