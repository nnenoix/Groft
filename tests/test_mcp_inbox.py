"""Focused test for P5.1 durable MCP inbox."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import aiosqlite
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_get_messages_consumes_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_NAME", "test-agent")
    import importlib

    import communication.mcp_server as mcp
    importlib.reload(mcp)

    db_path = tmp_path / "mcp_inbox.db"
    monkeypatch.setattr(mcp, "_DB_PATH", db_path)
    monkeypatch.setattr(mcp, "AGENT_NAME", "test-agent")

    async def _noop_ensure() -> None:
        return None

    monkeypatch.setattr(mcp, "_ensure_connected", _noop_ensure)

    db = await mcp._get_db()
    payload = {"type": "message", "from": "opus", "content": "hello"}
    await db.execute(
        "INSERT INTO messages (to_agent, from_agent, content, created_at)"
        " VALUES (?, ?, ?, ?)",
        ("test-agent", "opus", json.dumps(payload), time.time()),
    )
    await db.commit()

    result = await mcp.get_messages()
    msgs = json.loads(result)
    assert msgs == [payload]

    async with db.execute(
        "SELECT consumed_at FROM messages WHERE to_agent = ?", ("test-agent",)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None and row[0] is not None

    second = await mcp.get_messages()
    assert second == "Нет новых сообщений"

    await db.close()
    mcp._db_conn = None
