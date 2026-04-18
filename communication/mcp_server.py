from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite
import httpx
from mcp.server.fastmcp import FastMCP

from communication.client import CommunicationClient

AGENT_NAME = os.environ.get("AGENT_NAME", "unknown")
WS_URL = os.environ.get("WS_URL", "ws://localhost:8765")
REST_URL = os.environ.get("REST_URL", "http://localhost:8766")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / ".claudeorch" / "mcp_inbox.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    to_agent TEXT NOT NULL,
    from_agent TEXT,
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    consumed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_messages_to_unread
    ON messages(to_agent, consumed_at);
"""

server = FastMCP("claudeorch-comms")
client = CommunicationClient(agent_name=AGENT_NAME, ws_url=WS_URL)
_connected = False
_connect_lock = asyncio.Lock()
_db_conn: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
# strong refs to keep the consume loop alive across GC cycles
_background_tasks: set[asyncio.Task] = set()


async def _get_db() -> aiosqlite.Connection:
    global _db_conn
    async with _db_lock:
        if _db_conn is not None:
            return _db_conn
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(_DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(_SCHEMA)
        await conn.commit()
        _db_conn = conn
        return _db_conn


async def _ensure_connected() -> None:
    # lazy connect so the MCP server can start before orchestrator is up;
    # inbox task starts once the first tool call triggers a live connection
    global _connected
    async with _connect_lock:
        if _connected:
            return
        await client.connect()
        task = asyncio.create_task(_consume())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        _connected = True


async def _consume() -> None:
    async for msg in client.listen():
        db = await _get_db()
        await db.execute(
            "INSERT INTO messages (to_agent, from_agent, content, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                AGENT_NAME,
                msg.get("from"),
                json.dumps(msg, ensure_ascii=False),
                time.time(),
            ),
        )
        await db.commit()


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
    db = await _get_db()
    await db.execute("BEGIN IMMEDIATE")
    async with db.execute(
        "SELECT id, content FROM messages"
        " WHERE to_agent = ? AND consumed_at IS NULL ORDER BY id",
        (AGENT_NAME,),
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        await db.commit()
        return "Нет новых сообщений"
    now = time.time()
    await db.executemany(
        "UPDATE messages SET consumed_at = ? WHERE id = ?",
        [(now, row[0]) for row in rows],
    )
    await db.commit()
    msgs = [json.loads(row[1]) for row in rows]
    return json.dumps(msgs, ensure_ascii=False)


@server.tool()
async def get_connected_agents() -> str:
    """Получить список подключённых к ClaudeOrch агентов."""
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{REST_URL}/agents")
        return r.text


if __name__ == "__main__":
    server.run()
