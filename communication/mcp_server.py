from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from mcp.server.fastmcp import FastMCP

from communication.client import CommunicationClient

AGENT_NAME = os.environ.get("AGENT_NAME", "unknown")
WS_URL = os.environ.get("WS_URL", "ws://localhost:8765")
REST_URL = os.environ.get("REST_URL", "http://localhost:8766")

server = FastMCP("claudeorch-comms")
client = CommunicationClient(agent_name=AGENT_NAME, ws_url=WS_URL)
inbox: list[dict] = []
_connected = False
_connect_lock = asyncio.Lock()


async def _ensure_connected() -> None:
    # lazy connect so the MCP server can start before orchestrator is up;
    # inbox task starts once the first tool call triggers a live connection
    global _connected
    async with _connect_lock:
        if _connected:
            return
        await client.connect()
        asyncio.create_task(_consume())
        _connected = True


async def _consume() -> None:
    async for msg in client.listen():
        inbox.append(msg)


@server.tool()
async def send_message(to: str, content: str) -> str:
    """Отправить сообщение другому агенту через ClaudeOrch."""
    await _ensure_connected()
    await client.send(to, content)
    return f"✓ Сообщение отправлено агенту {to}"


@server.tool()
async def broadcast_message(content: str) -> str:
    """Отправить сообщение всем подключённым агентам."""
    await _ensure_connected()
    await client.broadcast(content)
    return "✓ Broadcast отправлен"


@server.tool()
async def get_messages() -> str:
    """Получить и очистить входящие сообщения для этого агента."""
    await _ensure_connected()
    if not inbox:
        return "Нет новых сообщений"
    msgs = inbox.copy()
    inbox.clear()
    return json.dumps(msgs, ensure_ascii=False)


@server.tool()
async def get_connected_agents() -> str:
    """Получить список подключённых к ClaudeOrch агентов."""
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{REST_URL}/agents")
        return r.text


if __name__ == "__main__":
    server.run()
