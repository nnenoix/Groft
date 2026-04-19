"""POST /shutdown dispatches the registered callback and returns immediately.

The endpoint is the hook the Tauri sidecar hits on window close to land the
orchestrator on the same teardown path as a SIGTERM. Two invariants:

  1. The handler returns 200 synchronously — Tauri's reqwest has a 2s timeout
     and the real callback (ProcessGuard.request_shutdown) can take seconds.
  2. The callback is actually invoked (via create_task) so shutdown starts.

We skip the real signal wiring here: a bare async callable + asyncio.Event
mirrors the fire-and-forget contract without pulling in ProcessGuard.
"""
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import CommunicationServer  # noqa: E402


def _free_port() -> int:
    # pick a fresh loopback port per test to keep the suite hermetic
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest_asyncio.fixture
async def server():
    ws_port = _free_port()
    rest_port = _free_port()
    srv = CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=ws_port,
        rest_host="127.0.0.1",
        rest_port=rest_port,
        db_path=Path(":memory:"),
    )
    await srv.start()
    try:
        yield srv, rest_port
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_shutdown_endpoint_invokes_callback(server) -> None:
    srv, rest_port = server

    triggered = asyncio.Event()

    async def _cb() -> None:
        triggered.set()

    srv.set_shutdown_callback(_cb)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{rest_port}/shutdown", timeout=2.0
        )
    assert resp.status_code == 200, f"unexpected status: {resp.status_code}"
    assert resp.json() == {"ok": True}, f"unexpected body: {resp.text!r}"

    # callback is scheduled via create_task, so the response can beat it —
    # give the loop a tick or two to drain before asserting.
    await asyncio.wait_for(triggered.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_shutdown_endpoint_without_callback_is_noop(server) -> None:
    srv, rest_port = server

    # Deliberately do not call set_shutdown_callback — endpoint should still
    # respond 200 so the Tauri graceful path doesn't stall when the Python
    # side hasn't wired the callback yet (e.g. during early boot).
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{rest_port}/shutdown", timeout=2.0
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
