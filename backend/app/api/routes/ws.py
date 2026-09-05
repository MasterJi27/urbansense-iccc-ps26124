from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.realtime.hub import hub
from app.security import decode_token

router = APIRouter()


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket, token: str = Query(default="")):
    try:
        decode_token(token)
    except ValueError:
        await ws.close(code=4401)
        return
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
