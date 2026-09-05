# Future ingestion (not implemented as live device adapters)

## HTTP (implemented)

`POST /ingest/phone|cctv|iot` with the same Observation JSON as `POST /observations`.

## RTSP (planned)

Edge gateway pulls RTSP, runs DetectionEngine, posts observations. Do not stream raw video to the API.

```
rtsp://camera/stream  ->  edge gateway  ->  POST /ingest/cctv
```

## MQTT (planned)

Topic: `urbansense/v1/{source_type}/{source_id}/observation`

Payload: Observation JSON. Gateway authenticates and forwards to FastAPI.
