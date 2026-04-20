"""Unit tests for AgentWatchdog.skip_liveness behaviour."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.watchdog.agent_watchdog import AgentWatchdog


class _FakeBackend:
    def __init__(self, output: str = "hello") -> None:
        self._output = output

    async def capture_output(self, target: str, lines: int) -> str:
        return self._output


@pytest.mark.asyncio
async def test_skip_liveness_still_updates_state_and_snapshot() -> None:
    backend = _FakeBackend(output="initial")
    snapshots: list[str] = []

    from communication.client import CommunicationClient

    class _FakeClient:
        async def snapshot(self, output: str, *, agent: str) -> None:
            snapshots.append(output)

    wd = AgentWatchdog(backend=backend)
    wd._comm_client = _FakeClient()  # type: ignore[assignment]
    wd.register_agent("opus", "claudeorch:0", skip_liveness=True)

    state = wd.get_state("opus")
    assert state is not None
    assert state.skip_liveness is True

    now = datetime.now(timezone.utc)
    # Feed changed output → should update state and send snapshot
    backend._output = "changed output"
    await wd._process("opus", "changed output", now)

    state = wd.get_state("opus")
    assert state.status == "active"
    assert state.last_output == "changed output"
    # Snapshot should have been scheduled (fire-and-forget task)
    await asyncio.sleep(0)  # let the task run
    assert snapshots == ["changed output"]


@pytest.mark.asyncio
async def test_skip_liveness_never_fires_wake_or_restart() -> None:
    backend = _FakeBackend(output="idle")
    wake_calls: list[str] = []
    restart_calls: list[str] = []
    notify_calls: list[str] = []

    async def fake_wake(name: str) -> None:
        wake_calls.append(name)

    async def fake_restart(name: str) -> None:
        restart_calls.append(name)

    async def fake_notify(name: str) -> None:
        notify_calls.append(name)

    # Use very short thresholds so any non-skipped agent would trigger immediately
    wd = AgentWatchdog(
        possibly_stuck_after=0.001,
        stuck_after=0.002,
        backend=backend,
    )
    wd.set_wake_up_callback(fake_wake)
    wd.set_restart_callback(fake_restart)
    wd.set_notification_callback(fake_notify)
    wd.register_agent("opus", "claudeorch:0", skip_liveness=True)

    # Seed last_output so that it "hasn't changed" (elapsed path)
    state = wd.get_state("opus")
    assert state is not None
    state.last_output = "idle"  # same as backend output

    # Simulate a ton of time passing
    from datetime import timedelta
    ancient = datetime.now(timezone.utc) - timedelta(seconds=9999)
    state.last_change_time = ancient

    now = datetime.now(timezone.utc)
    # Call _process with the same output (no change) — elapsed is huge
    await wd._process("opus", "idle", now)

    # No callbacks should have fired
    assert wake_calls == []
    assert restart_calls == []
    assert notify_calls == []
    # Status must remain active
    assert state.status == "active"
