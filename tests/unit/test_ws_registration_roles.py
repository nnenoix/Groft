"""Tests for role-aware WS registry in CommunicationServer."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import CommunicationServer  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.paths as paths
    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


def _make_server() -> CommunicationServer:
    return CommunicationServer(
        ws_host="127.0.0.1", ws_port=0,
        rest_host="127.0.0.1", rest_port=0,
        db_path=Path(":memory:"),
    )


def _fake_ws(name: str = "ws") -> MagicMock:
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_register_multiple_roles_both_stay_in_registry() -> None:
    """native + mcp-bridge for same agent: both coexist, neither evicted."""
    srv = _make_server()
    ws_native = _fake_ws("native")
    ws_mcp = _fake_ws("mcp")

    await srv._register("opus", "native", ws_native)
    await srv._register("opus", "mcp-bridge", ws_mcp)

    with srv._lock:
        roles = srv._registry.get("opus", {})
    assert roles.get("native") is ws_native
    assert roles.get("mcp-bridge") is ws_mcp
    # old socket NOT closed (different roles, not a reconnect)
    ws_native.close.assert_not_called()
    ws_mcp.close.assert_not_called()


@pytest.mark.asyncio
async def test_same_role_reconnect_evicts_old() -> None:
    """Same (agent, role) reconnect must evict the previous WS."""
    srv = _make_server()
    ws_old = _fake_ws("old")
    ws_new = _fake_ws("new")

    await srv._register("opus", "native", ws_old)
    await srv._register("opus", "native", ws_new)

    with srv._lock:
        roles = srv._registry.get("opus", {})
    assert roles.get("native") is ws_new
    ws_old.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_slash_route_to_native_only() -> None:
    """Slash command /spawn -> delivered only to native, not mcp-bridge."""
    srv = _make_server()
    ws_native = _fake_ws("native")
    ws_mcp = _fake_ws("mcp")

    await srv._register("opus", "native", ws_native)
    await srv._register("opus", "mcp-bridge", ws_mcp)

    msg = {"type": "message", "from": "ui", "to": "opus", "content": "/spawn backend-dev"}
    await srv._route_direct("opus", msg)

    ws_native.send.assert_awaited_once()
    ws_mcp.send.assert_not_called()


@pytest.mark.asyncio
async def test_normal_message_fanout_all_roles() -> None:
    """Normal (non-slash) message -> delivered to ALL roles."""
    srv = _make_server()
    ws_native = _fake_ws("native")
    ws_mcp = _fake_ws("mcp")

    await srv._register("opus", "native", ws_native)
    await srv._register("opus", "mcp-bridge", ws_mcp)

    msg = {"type": "message", "from": "ui", "to": "opus", "content": "hello"}
    await srv._route_direct("opus", msg)

    ws_native.send.assert_awaited_once()
    ws_mcp.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_backward_compat_no_role_defaults_to_worker() -> None:
    """Old register frame without role -> role defaults to 'worker', agent registered."""
    srv = _make_server()
    ws = _fake_ws()

    # Register without explicit role — simulates old client
    await srv._register("backend-dev", "worker", ws)

    with srv._lock:
        roles = srv._registry.get("backend-dev", {})
    assert "worker" in roles
    assert roles["worker"] is ws


@pytest.mark.asyncio
async def test_unregister_removes_correct_role_leaves_others() -> None:
    """Unregister one role doesn't remove others for same agent."""
    srv = _make_server()
    ws_native = _fake_ws("native")
    ws_mcp = _fake_ws("mcp")

    await srv._register("opus", "native", ws_native)
    await srv._register("opus", "mcp-bridge", ws_mcp)

    srv._unregister("opus", "mcp-bridge", ws_mcp)

    with srv._lock:
        roles = srv._registry.get("opus", {})
    assert "native" in roles
    assert "mcp-bridge" not in roles


@pytest.mark.asyncio
async def test_roster_no_duplicates() -> None:
    """Roster must list each agent name once even with multiple roles."""
    srv = _make_server()
    ws_native = _fake_ws("native")
    ws_mcp = _fake_ws("mcp")

    await srv._register("opus", "native", ws_native)
    await srv._register("opus", "mcp-bridge", ws_mcp)

    with srv._lock:
        agents = list(srv._registry.keys())
    assert agents.count("opus") == 1
