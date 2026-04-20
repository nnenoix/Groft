"""REST tests for GET /decisions."""
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
from core.decision_log import DecisionLog  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.paths as paths
    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


async def _make_server_with_log(tmp_path: Path) -> tuple[CommunicationServer, DecisionLog]:
    dl = DecisionLog(db_path=tmp_path / "decisions.duckdb")
    await dl.initialize()
    srv = CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=0,
        rest_host="127.0.0.1",
        rest_port=0,
        db_path=Path(":memory:"),
        decision_log=dl,
    )
    return srv, dl


def _client(server: CommunicationServer) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server._rest_app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_decisions_empty_log(tmp_path: Path) -> None:
    srv, dl = await _make_server_with_log(tmp_path)
    try:
        async with _client(srv) as c:
            resp = await c.get("/decisions")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        await dl.close()


@pytest.mark.asyncio
async def test_decisions_returns_appended_entry(tmp_path: Path) -> None:
    srv, dl = await _make_server_with_log(tmp_path)
    try:
        await dl.append("opus", "architecture", "DuckDB", ["SQLite"], "fast")
        async with _client(srv) as c:
            resp = await c.get("/decisions")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        r = rows[0]
        assert r["agent"] == "opus"
        assert r["category"] == "architecture"
        assert r["chosen"] == "DuckDB"
        assert r["alternatives"] == ["SQLite"]
        assert r["reason"] == "fast"
        assert "ts" in r
    finally:
        await dl.close()


@pytest.mark.asyncio
async def test_decisions_filter_by_agent(tmp_path: Path) -> None:
    srv, dl = await _make_server_with_log(tmp_path)
    try:
        await dl.append("opus", "arch", "A", None, "r1")
        await dl.append("backend-dev", "arch", "B", None, "r2")
        async with _client(srv) as c:
            resp = await c.get("/decisions?agent=opus")
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["agent"] == "opus"
    finally:
        await dl.close()


@pytest.mark.asyncio
async def test_decisions_limit(tmp_path: Path) -> None:
    srv, dl = await _make_server_with_log(tmp_path)
    try:
        for i in range(5):
            await dl.append("opus", "arch", f"choice{i}", None, "reason")
        async with _client(srv) as c:
            resp = await c.get("/decisions?limit=3")
        rows = resp.json()
        assert len(rows) == 3
    finally:
        await dl.close()


@pytest.mark.asyncio
async def test_decisions_503_when_not_wired(tmp_path: Path) -> None:
    srv = CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=0,
        rest_host="127.0.0.1",
        rest_port=0,
        db_path=Path(":memory:"),
    )
    async with _client(srv) as c:
        resp = await c.get("/decisions")
    assert resp.status_code == 503
