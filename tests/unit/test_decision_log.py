"""Unit tests for DecisionLog."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.decision_log import DecisionLog  # noqa: E402


@pytest.fixture
async def dl(tmp_path: Path):
    log = DecisionLog(db_path=tmp_path / "test.duckdb")
    await log.initialize()
    yield log
    await log.close()


@pytest.mark.asyncio
async def test_append_list_round_trip(dl: DecisionLog) -> None:
    id_ = await dl.append("opus", "architecture", "DuckDB", ["SQLite"], "fast")
    assert id_ == 1
    rows = await dl.list_recent()
    assert len(rows) == 1
    r = rows[0]
    assert r["agent"] == "opus"
    assert r["category"] == "architecture"
    assert r["chosen"] == "DuckDB"
    assert r["alternatives"] == ["SQLite"]
    assert r["reason"] == "fast"
    assert r["task_id"] is None


@pytest.mark.asyncio
async def test_filter_by_agent(dl: DecisionLog) -> None:
    await dl.append("opus", "arch", "A", None, "r1")
    await dl.append("backend-dev", "arch", "B", None, "r2")
    rows = await dl.list_recent(agent="opus")
    assert len(rows) == 1
    assert rows[0]["agent"] == "opus"


@pytest.mark.asyncio
async def test_limit(dl: DecisionLog) -> None:
    for i in range(5):
        await dl.append("opus", "arch", f"choice{i}", None, "reason")
    rows = await dl.list_recent(limit=3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_alternatives_none_stored_and_read_as_empty(dl: DecisionLog) -> None:
    await dl.append("opus", "arch", "X", None, "reason")
    rows = await dl.list_recent()
    # Contract: None alternatives come back as []
    assert rows[0]["alternatives"] == []


@pytest.mark.asyncio
async def test_value_error_on_empty_fields(dl: DecisionLog) -> None:
    with pytest.raises(ValueError):
        await dl.append("", "cat", "chosen", None, "reason")
    with pytest.raises(ValueError):
        await dl.append("opus", "", "chosen", None, "reason")
    with pytest.raises(ValueError):
        await dl.append("opus", "cat", "", None, "reason")
    with pytest.raises(ValueError):
        await dl.append("opus", "cat", "chosen", None, "")


@pytest.mark.asyncio
async def test_persistence_close_reopen(tmp_path: Path) -> None:
    dl = DecisionLog(db_path=tmp_path / "persist.duckdb")
    await dl.initialize()
    await dl.append("opus", "arch", "pick", None, "because")
    await dl.close()

    dl2 = DecisionLog(db_path=tmp_path / "persist.duckdb")
    await dl2.initialize()
    rows = await dl2.list_recent()
    assert len(rows) == 1
    assert rows[0]["chosen"] == "pick"
    await dl2.close()
