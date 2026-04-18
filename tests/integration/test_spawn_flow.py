"""End-to-end Team-mode spawn flow.

Exercises the real wiring that turns `/spawn backend-dev` into:
    spawner.spawn → register_callback → watchdog.register_agent
                 → status_for("active") → UI WS frame

Real tmux/claude are not invoked: `AgentSpawner._run_tmux` is replaced with a
stub so every subprocess call reports success. The WebSocket server runs on a
free port picked per test so the suite is hermetic.

Failure modes surface as concrete assertions: if the spawn never reaches the
watchdog, the test says so; if the UI never sees the status frame, same.
"""
from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.client import CommunicationClient  # noqa: E402
from communication.server import CommunicationServer  # noqa: E402
from core.orchestrator import Orchestrator  # noqa: E402
from core.spawner import AgentSpawner  # noqa: E402
from core.watchdog.agent_watchdog import AgentWatchdog  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _recv_until(
    ws: websockets.WebSocketClientProtocol,
    predicate,
    timeout: float = 3.0,
) -> dict:
    """Drain WS frames until one matches `predicate`; fail the test on timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError(
                f"timed out after {timeout}s waiting for matching frame"
            )
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        frame = json.loads(raw)
        if predicate(frame):
            return frame


@pytest_asyncio.fixture
async def stub_tmux(monkeypatch):
    """Replace AgentSpawner._run_tmux so tmux/claude are never invoked."""
    calls: list[list[str]] = []

    async def fake_run_tmux(args: list[str]) -> bool:
        calls.append(list(args))
        return True

    monkeypatch.setattr(AgentSpawner, "_run_tmux", staticmethod(fake_run_tmux))
    yield calls


@pytest_asyncio.fixture
async def server():
    """Boot CommunicationServer on free ports, tear down at end of test."""
    ws_port = _free_port()
    rest_port = _free_port()
    srv = CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=ws_port,
        rest_host="127.0.0.1",
        rest_port=rest_port,
        db_path=Path(":memory:"),
        lead_tmux_target="claudeorch:0",
        agent_tmux_targets={"opus": "claudeorch:0"},
    )
    await srv.start()
    try:
        yield srv, ws_port, rest_port
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_spawn_backend_dev_reaches_watchdog_and_ui(stub_tmux, server):
    srv, ws_port, _rest_port = server
    ws_url = f"ws://127.0.0.1:{ws_port}"

    ui_ws = await websockets.connect(ws_url)
    try:
        await ui_ws.send(json.dumps({"type": "register", "agent": "ui"}))

        opus_client = CommunicationClient(agent_name="opus", ws_url=ws_url)
        await opus_client.connect()
        try:
            spawner = AgentSpawner(
                str(PROJECT_ROOT), str(PROJECT_ROOT / "config.yml")
            )
            orchestrator = Orchestrator(spawner)
            watchdog = AgentWatchdog(comm_client=opus_client)

            spawner.set_register_callback(
                lambda name, target: watchdog.register_agent(name, target)
            )
            spawner.set_unregister_callback(
                lambda name: watchdog.unregister_agent(name)
            )

            await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "roster"
                and "opus" in (f.get("agents") or []),
            )

            spawned = await orchestrator.spawn_role("backend-dev")
            assert spawned is True, "orchestrator.spawn_role returned False"

            assert "backend-dev" in spawner.active_agents, (
                "spawner did not record backend-dev in active_agents; "
                f"got {list(spawner.active_agents)}"
            )
            assert watchdog.get_state("backend-dev") is not None, (
                "spawner register_callback never reached watchdog; "
                "watchdog has no state for backend-dev"
            )
            state = watchdog.get_state("backend-dev")
            assert state is not None
            assert state.tmux_target == "claudeorch:backend-dev", (
                f"unexpected tmux_target={state.tmux_target!r}"
            )

            await opus_client.status_for("backend-dev", "active")

            status_frame = await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "status"
                and f.get("agent") == "backend-dev",
            )
            assert status_frame["status"] == "active", (
                f"UI saw wrong status frame: {status_frame!r}"
            )

            tmux_calls = stub_tmux
            assert any(
                "new-window" in c for c in tmux_calls
            ), f"tmux new-window never called; calls={tmux_calls!r}"
            assert any(
                "send-keys" in c for c in tmux_calls
            ), f"tmux send-keys never called; calls={tmux_calls!r}"
        finally:
            await opus_client.disconnect()
    finally:
        await ui_ws.close()


@pytest.mark.asyncio
async def test_despawn_removes_watchdog_state_and_emits_idle(stub_tmux, server):
    srv, ws_port, _rest_port = server
    ws_url = f"ws://127.0.0.1:{ws_port}"

    ui_ws = await websockets.connect(ws_url)
    try:
        await ui_ws.send(json.dumps({"type": "register", "agent": "ui"}))

        opus_client = CommunicationClient(agent_name="opus", ws_url=ws_url)
        await opus_client.connect()
        try:
            spawner = AgentSpawner(
                str(PROJECT_ROOT), str(PROJECT_ROOT / "config.yml")
            )
            orchestrator = Orchestrator(spawner)
            watchdog = AgentWatchdog(comm_client=opus_client)

            spawner.set_register_callback(
                lambda name, target: watchdog.register_agent(name, target)
            )
            spawner.set_unregister_callback(
                lambda name: watchdog.unregister_agent(name)
            )

            assert await orchestrator.spawn_role("backend-dev") is True
            assert watchdog.get_state("backend-dev") is not None

            despawned = await orchestrator.despawn_role("backend-dev")
            assert despawned is True, "despawn_role returned False"
            assert "backend-dev" not in spawner.active_agents
            assert watchdog.get_state("backend-dev") is None, (
                "watchdog still tracks backend-dev after despawn"
            )

            await opus_client.status_for("backend-dev", "idle")

            frame = await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "status"
                and f.get("agent") == "backend-dev"
                and f.get("status") == "idle",
            )
            assert frame["status"] == "idle"
        finally:
            await opus_client.disconnect()
    finally:
        await ui_ws.close()


@pytest.mark.asyncio
async def test_worker_disconnect_drops_agent_from_roster(stub_tmux, server):
    """Full lifecycle: spawn → worker WS connect → despawn → disconnect → UI
    sees roster without the worker. Covers P1.1 — UI dropping despawned
    agents from the agents list, plus idle status frame before the drop.
    """
    srv, ws_port, _rest_port = server
    ws_url = f"ws://127.0.0.1:{ws_port}"

    ui_ws = await websockets.connect(ws_url)
    try:
        await ui_ws.send(json.dumps({"type": "register", "agent": "ui"}))

        opus_client = CommunicationClient(agent_name="opus", ws_url=ws_url)
        await opus_client.connect()
        try:
            spawner = AgentSpawner(
                str(PROJECT_ROOT), str(PROJECT_ROOT / "config.yml")
            )
            orchestrator = Orchestrator(spawner)
            watchdog = AgentWatchdog(comm_client=opus_client)
            spawner.set_register_callback(
                lambda name, target: watchdog.register_agent(name, target)
            )
            spawner.set_unregister_callback(
                lambda name: watchdog.unregister_agent(name)
            )

            assert await orchestrator.spawn_role("backend-dev") is True

            worker_ws = await websockets.connect(ws_url)
            await worker_ws.send(
                json.dumps({"type": "register", "agent": "backend-dev"})
            )

            await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "roster"
                and "backend-dev" in (f.get("agents") or []),
            )

            assert await orchestrator.despawn_role("backend-dev") is True
            await opus_client.status_for("backend-dev", "idle")

            await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "status"
                and f.get("agent") == "backend-dev"
                and f.get("status") == "idle",
            )

            await worker_ws.close()

            final_roster = await _recv_until(
                ui_ws,
                lambda f: f.get("type") == "roster"
                and "backend-dev" not in (f.get("agents") or []),
                timeout=5.0,
            )
            assert "backend-dev" not in final_roster["agents"], (
                "UI still sees backend-dev in roster after worker disconnect; "
                f"roster={final_roster!r}"
            )
        finally:
            await opus_client.disconnect()
    finally:
        await ui_ws.close()


@pytest.mark.asyncio
async def test_spawn_unknown_role_is_rejected(stub_tmux, server):
    srv, ws_port, _rest_port = server
    ws_url = f"ws://127.0.0.1:{ws_port}"

    opus_client = CommunicationClient(agent_name="opus", ws_url=ws_url)
    await opus_client.connect()
    try:
        spawner = AgentSpawner(
            str(PROJECT_ROOT), str(PROJECT_ROOT / "config.yml")
        )
        orchestrator = Orchestrator(spawner)

        spawned = await orchestrator.spawn_role("frontend-dev--typo")
        assert spawned is False, (
            "orchestrator accepted unknown role — "
            "config.yml allowlist is not being enforced"
        )
        assert "frontend-dev--typo" not in spawner.active_agents
    finally:
        await opus_client.disconnect()
