"""Smoke test for the log_decision MCP tool."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_log_decision_returns_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.decision_log import DecisionLog

    dl = DecisionLog(db_path=tmp_path / "mcp_test.duckdb")
    await dl.initialize()

    import communication.mcp_server as mcp_mod
    monkeypatch.setattr(mcp_mod, "AGENT_NAME", "opus")

    # Inject our test DecisionLog directly
    original = mcp_mod._decision_log
    mcp_mod._decision_log = dl
    try:
        result = await mcp_mod.log_decision(
            category="architecture",
            chosen="DuckDB",
            alternatives=["SQLite"],
            reason="columnar analytics",
            task_id="phase-8",
        )
        assert result.startswith("✓ decision #")
        assert "logged" in result
        rows = await dl.list_recent()
        assert len(rows) == 1
        assert rows[0]["agent"] == "opus"
        assert rows[0]["category"] == "architecture"
    finally:
        mcp_mod._decision_log = original
        await dl.close()


@pytest.mark.asyncio
async def test_log_decision_returns_error_string_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import communication.mcp_server as mcp_mod
    monkeypatch.setattr(mcp_mod, "AGENT_NAME", "opus")

    # Force _get_decision_log to raise
    async def boom() -> None:
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(mcp_mod, "_get_decision_log", boom)
    result = await mcp_mod.log_decision(
        category="arch", chosen="X", reason="r"
    )
    assert result.startswith("✗ decision log failed:")
