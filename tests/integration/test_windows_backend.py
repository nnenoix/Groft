"""Windows-only smoke tests for WindowsBackend.

All tests skip on non-Windows hosts. Kept deliberately small — real-console
behaviour of `claude.exe` isn't exercised here; we only prove that Popen +
CREATE_NEW_CONSOLE wires up through the ProcessBackend contract (spawn,
capture_output, kill, list_targets, select_backend).

Timeouts are short (`timeout /t 2`) so a hung ctrl-break can't stall CI —
each test should complete in under ~5 seconds even with the kill fallback.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from core.process import select_backend
from core.process.windows_backend import WindowsBackend


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only"
)


@pytest.mark.asyncio
async def test_spawn_and_kill(tmp_path: Path) -> None:
    backend = WindowsBackend(log_dir=tmp_path / "panes")
    target = await backend.spawn(
        "probe", ["cmd", "/c", "timeout", "/t", "2", "/nobreak"], None
    )
    assert target is not None, "spawn returned None"
    assert target.startswith("pid:"), f"unexpected target shape: {target!r}"
    try:
        assert await backend.is_alive(target) is True
        assert backend.list_targets().get("probe") == target
    finally:
        killed = await backend.kill(target)
        assert killed is True
    assert await backend.is_alive(target) is False
    assert "probe" not in backend.list_targets()


@pytest.mark.asyncio
async def test_capture_output(tmp_path: Path) -> None:
    backend = WindowsBackend(log_dir=tmp_path / "panes")
    # `echo hello && timeout` keeps the process alive long enough for the
    # log tail to pick up the echoed line before we kill it.
    target = await backend.spawn(
        "echo",
        ["cmd", "/c", "echo hello && timeout /t 2 /nobreak"],
        None,
    )
    assert target is not None
    try:
        # Give cmd.exe a moment to flush the echo into the log file.
        await asyncio.sleep(0.5)
        output = await backend.capture_output(target, lines=50)
        assert "hello" in output, f"expected 'hello' in output, got: {output!r}"
    finally:
        await backend.kill(target)


@pytest.mark.asyncio
async def test_factory_on_windows() -> None:
    backend = select_backend({})
    assert type(backend).__name__ == "WindowsBackend", (
        f"factory returned {type(backend).__name__} on Windows; expected WindowsBackend"
    )
