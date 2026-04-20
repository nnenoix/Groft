from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiosqlite
import httpx
from mcp.server.fastmcp import FastMCP

from communication.client import CommunicationClient
from core.paths import claudeorch_dir
from core.vision import (
    VisionError,
    ask_about_image,
    ask_about_text,
    capture_screen,
)

log = logging.getLogger(__name__)

AGENT_NAME = os.environ.get("AGENT_NAME", "unknown")
WS_URL = os.environ.get("WS_URL", "ws://localhost:8765")
REST_URL = os.environ.get("REST_URL", "http://localhost:8766")

_DB_PATH = claudeorch_dir() / "mcp_inbox.db"

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


# tmux session name is fixed by AgentSpawner ("claudeorch"). We reach tmux
# directly here instead of plumbing the ProcessBackend through the MCP
# process — the MCP server is a separate process with its own stdio
# transport, and sharing a backend would require IPC that doesn't exist
# today. Capture-pane is cheap, idempotent and read-only, so the
# shortcut is safe. If the session name ever changes, update this
# constant and the matching AgentSpawner side.
_TMUX_SESSION = "claudeorch"


def _capture_pane_sync(agent_name: str) -> str:
    """Shell out to ``tmux capture-pane`` synchronously.

    Kept sync + off-loaded via ``run_in_executor`` in the async wrapper
    because subprocess.run is blocking. Errors collapse to VisionError
    so the MCP tool has one failure type to surface.
    """
    try:
        proc = subprocess.run(
            [
                "tmux",
                "capture-pane",
                "-t",
                f"{_TMUX_SESSION}:{agent_name}",
                "-p",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise VisionError(f"tmux not installed: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VisionError(f"tmux capture-pane timed out: {exc}") from exc
    except Exception as exc:
        raise VisionError(f"tmux capture-pane failed: {exc}") from exc
    if proc.returncode != 0:
        # tmux prints diagnostics to stderr; echo them back so the
        # operator sees "can't find window 'foo'" rather than a bare
        # exit code.
        raise VisionError(
            f"tmux capture-pane exit {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


async def _capture_pane(agent_name: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _capture_pane_sync, agent_name)


@server.tool()
async def see_screen(monitor_idx: int, question: str) -> str:
    """Take a screenshot and ask Claude Sonnet about it.

    WARNING: Uses the multimodal API, which costs roughly 5-10x more
    than a normal text call. Prefer ``see_agent_pane`` when you just
    need to inspect a terminal — that path goes through the text-only
    model. Use this tool only when the answer genuinely requires
    pixels (e.g. "what colour is the error banner in the browser?").

    Parameters:
        monitor_idx: 0 = primary display, 1 = second monitor, etc.
        question: what to ask about the screenshot.
    """
    try:
        png = await capture_screen(monitor_idx)
        return await ask_about_image(png, question)
    except VisionError as exc:
        return f"Vision error: {exc}"


@server.tool()
async def see_agent_pane(agent_name: str, question: str) -> str:
    """Read another agent's tmux pane and ask Claude Sonnet about it.

    Cheaper than ``see_screen`` because it skips the multimodal path —
    the pane is already text, so we send it as text. Still Sonnet-class
    though, so each call is ~5x a normal Haiku call; keep questions
    specific.

    Parameters:
        agent_name: tmux window name (e.g. "backend-dev"). Must match
            the name AgentSpawner used when creating the window.
        question: what to ask about the captured pane.
    """
    try:
        pane = await _capture_pane(agent_name)
        return await ask_about_text(pane, question, agent_label=agent_name)
    except VisionError as exc:
        return f"Vision error: {exc}"


_decision_log: "DecisionLog | None" = None
_decision_log_lock = asyncio.Lock()


async def _get_decision_log() -> "DecisionLog":
    global _decision_log
    async with _decision_log_lock:
        if _decision_log is not None:
            return _decision_log
        from core.decision_log import DecisionLog
        dl = DecisionLog(claudeorch_dir() / "decisions.duckdb")
        await dl.initialize()
        _decision_log = dl
        return _decision_log


@server.tool()
async def log_decision(
    category: str,
    chosen: str,
    alternatives: list[str] | None = None,
    reason: str = "",
    task_id: str | None = None,
) -> str:
    """Записать архитектурное решение в общий журнал.

    agent берётся из AGENT_NAME env. Возвращает '✓ decision #<id> logged'.
    """
    try:
        dl = await _get_decision_log()
        id_ = await dl.append(
            agent=AGENT_NAME,
            category=category,
            chosen=chosen,
            alternatives=alternatives,
            reason=reason if reason else "unspecified",
            task_id=task_id,
        )
        return f"✓ decision #{id_} logged"
    except Exception as exc:
        log.exception("log_decision failed")
        return f"✗ decision log failed: {exc}"


if __name__ == "__main__":
    server.run()
