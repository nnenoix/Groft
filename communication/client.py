from __future__ import annotations

import json
from typing import Any, AsyncIterator

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

    async def snapshot(self, terminal: str, agent: str | None = None) -> None:
        assert self._ws is not None
        # agent overrides the registered name so an orchestrator can relay
        # snapshots captured from other tmux panes without masquerading.
        await self._ws.send(
            json.dumps(
                {
                    "type": "snapshot",
                    "agent": agent or self._agent_name,
                    "terminal": terminal,
                }
            )
        )

    async def status(self, status: str, **extras: Any) -> None:
        assert self._ws is not None
        payload: dict[str, Any] = {
            "type": "status",
            "agent": self._agent_name,
            "status": status,
        }
        payload.update(extras)
        await self._ws.send(json.dumps(payload))

    async def status_for(self, agent: str, status: str, **extras: Any) -> None:
        # used by orchestrator to report on agents it monitors but isn't
        # registered as — e.g. watchdog reporting worker health.
        assert self._ws is not None
        payload: dict[str, Any] = {
            "type": "status",
            "agent": agent,
            "status": status,
        }
        payload.update(extras)
        await self._ws.send(json.dumps(payload))

    async def tasks(
        self,
        backlog: list | None = None,
        current: list | None = None,
        done: list | None = None,
    ) -> None:
        assert self._ws is not None
        payload: dict = {"type": "tasks"}
        if backlog is not None:
            payload["backlog"] = backlog
        if current is not None:
            payload["current"] = current
        if done is not None:
            payload["done"] = done
        await self._ws.send(json.dumps(payload))

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
