"""REST /agents/{spawn,despawn,kill,clear-history} endpoints.

The UI's AgentDrawer hits these to avoid going through slash-commands over
WS. Exercise the FastAPI app directly via httpx.ASGITransport so the test
suite doesn't need uvicorn or real tmux panes — CommunicationServer.
_rest_app is built eagerly in __init__ for exactly this purpose.

The orchestrator is stubbed as a plain object whose spawn_role/despawn_role
are async callables that can be programmed per test. This keeps the tests
hermetic (no AgentSpawner, no config.yml, no subprocesses) while still
covering the HTTP wiring contract.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import CommunicationServer  # noqa: E402


class _StubOrchestrator:
    """Duck-typed stand-in for core.orchestrator.Orchestrator.

    Records every call so tests can assert on them. spawn_result and
    despawn_result control what the awaitable returns.
    """

    def __init__(self, spawn_result: bool = True, despawn_result: bool = True) -> None:
        self.spawn_result = spawn_result
        self.despawn_result = despawn_result
        self.spawn_calls: list[str] = []
        self.despawn_calls: list[str] = []

    async def spawn_role(self, role: str) -> bool:
        self.spawn_calls.append(role)
        return self.spawn_result

    async def despawn_role(self, role: str) -> bool:
        self.despawn_calls.append(role)
        return self.despawn_result


def _build_server(
    orchestrator: _StubOrchestrator | None,
) -> CommunicationServer:
    # db_path=":memory:" keeps the log-insert codepath silent without touching
    # the real claudeorch dir (nothing calls start() here anyway).
    return CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=0,
        rest_host="127.0.0.1",
        rest_port=0,
        db_path=Path(":memory:"),
        orchestrator=orchestrator,
    )


def _client(server: CommunicationServer) -> httpx.AsyncClient:
    # base_url is required so relative paths on the test calls resolve.
    transport = httpx.ASGITransport(app=server._rest_app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_spawn_returns_ok_when_orchestrator_accepts() -> None:
    stub = _StubOrchestrator(spawn_result=True)
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/spawn", json={"role": "backend-dev"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "role": "backend-dev"}
    assert stub.spawn_calls == ["backend-dev"]


async def test_spawn_returns_409_when_orchestrator_rejects() -> None:
    stub = _StubOrchestrator(spawn_result=False)
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/spawn", json={"role": "backend-dev"})
    assert resp.status_code == 409, resp.text
    body: dict[str, Any] = resp.json()
    assert body["ok"] is False
    assert body["role"] == "backend-dev"
    assert body["reason"] == "unknown-or-active"


async def test_spawn_returns_400_when_role_missing() -> None:
    stub = _StubOrchestrator()
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/spawn", json={})
    assert resp.status_code == 400, resp.text
    assert "error" in resp.json()
    # orchestrator must not be touched when the input is rejected upfront
    assert stub.spawn_calls == []


async def test_spawn_returns_400_when_role_empty_string() -> None:
    stub = _StubOrchestrator()
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/spawn", json={"role": "   "})
    assert resp.status_code == 400, resp.text
    assert stub.spawn_calls == []


async def test_spawn_returns_503_when_orchestrator_not_attached() -> None:
    server = _build_server(None)
    async with _client(server) as client:
        resp = await client.post("/agents/spawn", json={"role": "backend-dev"})
    assert resp.status_code == 503, resp.text
    assert resp.json() == {"error": "orchestrator not attached"}


async def test_despawn_returns_ok_when_orchestrator_accepts() -> None:
    stub = _StubOrchestrator(despawn_result=True)
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/despawn", json={"role": "backend-dev"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "role": "backend-dev"}
    assert stub.despawn_calls == ["backend-dev"]


async def test_kill_aliases_despawn_for_now() -> None:
    # kill is currently an alias for despawn (TODO noted in the endpoint); the
    # behavioural contract is the same end-to-end.
    stub = _StubOrchestrator(despawn_result=True)
    server = _build_server(stub)
    async with _client(server) as client:
        resp = await client.post("/agents/kill", json={"role": "backend-dev"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "role": "backend-dev"}
    assert stub.despawn_calls == ["backend-dev"]


async def test_clear_history_wipes_memory_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Redirect paths at the env-var level so paths.memory_dir()/memory_archive_dir()
    # point at tmp_path. CLAUDEORCH_USER_DATA is the supported override and the
    # @functools.cache on paths must be cleared for each test run.
    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    import core.paths as paths

    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()

    # seed a non-empty memory file and matching archive copies
    memory_file = paths.memory_dir() / "backend-dev.md"
    memory_file.write_text("stale notes\n", encoding="utf-8")
    archive_dir = paths.memory_archive_dir()
    (archive_dir / "backend-dev-20260101T000000Z.md").write_text("a", encoding="utf-8")
    (archive_dir / "backend-dev-20260102T000000Z.md").write_text("b", encoding="utf-8")
    # unrelated archive entry must survive the wipe
    (archive_dir / "frontend-dev-20260101T000000Z.md").write_text("keep", encoding="utf-8")

    server = _build_server(_StubOrchestrator())
    async with _client(server) as client:
        resp = await client.post(
            "/agents/clear-history", json={"role": "backend-dev"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # memory file is truncated (exists, zero bytes) — not deleted
    assert memory_file.exists()
    assert memory_file.read_text(encoding="utf-8") == ""
    # both backend-dev archive copies are gone; frontend-dev one is untouched
    assert not (archive_dir / "backend-dev-20260101T000000Z.md").exists()
    assert not (archive_dir / "backend-dev-20260102T000000Z.md").exists()
    assert (archive_dir / "frontend-dev-20260101T000000Z.md").exists()
    # response lists what was touched (paths form, exact values aren't load-bearing
    # but the memory file path should appear)
    assert str(memory_file) in body["cleared"]

    # leave the cache clean for sibling tests
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
