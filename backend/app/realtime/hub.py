from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._clients: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channel: str = "events") -> None:
        await ws.accept()
        async with self._lock:
            self._clients[channel].append(ws)

    async def disconnect(self, ws: WebSocket, channel: str = "events") -> None:
        async with self._lock:
            if ws in self._clients[channel]:
                self._clients[channel].remove(ws)

    async def broadcast(self, payload: dict, channel: str = "events") -> None:
        data = json.dumps(payload, default=str)
        async with self._lock:
            targets = list(self._clients[channel])
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, channel)


hub = Hub()
