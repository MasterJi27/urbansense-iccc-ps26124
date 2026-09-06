import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.api.routes.fleet import _clip_live_boxes, _live_telemetry
from app.realtime.hub import hub
from app.security import decode_token

router = APIRouter()


async def _bind_events_ws(ws: WebSocket, token: str, channel: str) -> None:
    try:
        payload = decode_token(token)
    except ValueError:
        await ws.close(code=4401)
        return
    if payload.get("scope") == "field":
        await ws.close(code=4403)
        return
    await hub.connect(ws, channel)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws, channel)


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket, token: str = Query(default="")):
    await _bind_events_ws(ws, token, "events")


@router.websocket("/ws/live")
async def live_ws(ws: WebSocket, token: str = Query(default="")):
    await _bind_events_ws(ws, token, "live")


@router.websocket("/ws/field-live")
async def field_live_ws(ws: WebSocket, token: str = Query(default="")):
    """Phone pushes overlay ticks. ICCC listens on /ws/live. Field is send-only."""
    try:
        payload = decode_token(token)
    except ValueError:
        await ws.close(code=4401)
        return
    if payload.get("scope") != "field":
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            code = str(msg.get("sensor_code") or msg.get("bus_code") or "")[:32]
            try:
                infer_ms = float(msg["infer_ms"]) if msg.get("infer_ms") is not None else None
            except (TypeError, ValueError):
                infer_ms = None
            backend = str(msg.get("overlay_backend") or "")[:16] or None
            live = {
                "type": "live.heartbeat",
                "sensor_id": code or "FIELD",
                "sensor_code": code or "FIELD",
                "bus_code": str(msg.get("bus_code") or "")[:16] or None,
                "latitude": msg.get("latitude"),
                "longitude": msg.get("longitude"),
                "heading": msg.get("heading"),
                "last_boxes": _clip_live_boxes(msg.get("last_boxes")),
                "person_count": int(msg.get("person_count") or 0),
                "overlay_fps": msg.get("overlay_fps"),
                "overlay_mode": msg.get("overlay_mode"),
                "overlay_backend": backend,
                "infer_ms": infer_ms,
                "ai_mode": msg.get("ai_mode"),
                "camera_status": "ONLINE",
                **_live_telemetry(msg),
            }
            await hub.broadcast(live, "live")
    except WebSocketDisconnect:
        return
