from __future__ import annotations

import json
from typing import AsyncIterator

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed


class CommunicationClient:
    def __init__(self, agent_name: str, ws_url: str = "ws://localhost:8765") -> None:
        self._agent_name = agent_name
        self._ws_url = ws_url
        self._ws: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._ws_url)
        # register is mandatory first frame — server closes 1008 otherwise
        await self._ws.send(
            json.dumps({"type": "register", "agent": self._agent_name})
        )

    async def disconnect(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send(self, to: str, content: str) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "message",
                    "from": self._agent_name,
                    "to": to,
                    "content": content,
                }
            )
        )

    async def broadcast(self, content: str) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {"type": "broadcast", "from": self._agent_name, "content": content}
            )
        )

    async def snapshot(self, terminal: str) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "snapshot",
                    "agent": self._agent_name,
                    "terminal": terminal,
                }
            )
        )

    async def status(self, status: str) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {"type": "status", "agent": self._agent_name, "status": status}
            )
        )

    async def listen(self) -> AsyncIterator[dict]:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    # malformed frames are skipped — caller should not see them
                    continue
                if isinstance(data, dict):
                    yield data
        except ConnectionClosed:
            return
