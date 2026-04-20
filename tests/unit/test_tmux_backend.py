"""Unit tests for TmuxBackend.send_text submit sequence.

Empirical finding (2026-04-20): C-j (Ctrl+J / LF / 0x0A) acts as submit in
prompt-toolkit-based TUIs such as claude TUI. A bare Enter is treated as
newline in multi-line mode. Implementation therefore sends C-j as the final
keystroke instead of Enter.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.process.tmux_backend import TmuxBackend  # noqa: E402


@pytest.mark.asyncio
async def test_send_text_single_line_uses_submit_not_bare_enter() -> None:
    """Single-line message: last tmux call must be C-j, not bare Enter."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    ok = await backend.send_text("claudeorch:test", "hello")
    assert ok is True
    # The last call must be the submit sequence (C-j), not bare Enter
    last_call = calls[-1]
    assert last_call == ["C-j"], (
        f"Last tmux call should be C-j (submit), got {last_call}"
    )
    # First call should be the literal text
    assert calls[0] == ["-l", "--", "hello"]


@pytest.mark.asyncio
async def test_send_text_multiline_enters_between_lines_submit_at_end() -> None:
    """Multi-line: Enter between lines (newline), C-j submit at end."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    ok = await backend.send_text("claudeorch:test", "line1\nline2")
    assert ok is True

    # Expected sequence: literal "line1", Enter (inter-line newline), literal "line2", C-j
    assert calls[0] == ["-l", "--", "line1"], f"Expected literal line1, got {calls[0]}"
    assert calls[1] == ["Enter"], f"Expected inter-line Enter, got {calls[1]}"
    assert calls[2] == ["-l", "--", "line2"], f"Expected literal line2, got {calls[2]}"
    assert calls[3] == ["C-j"], f"Expected C-j submit at end, got {calls[3]}"
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_send_text_submit_false_no_final_keystroke() -> None:
    """submit=False and press_enter=False: no final keystroke sent."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    ok = await backend.send_text("claudeorch:test", "hello", submit=False, press_enter=False)
    assert ok is True
    # Only the literal text call, no Enter or C-j
    assert calls == [["-l", "--", "hello"]]


@pytest.mark.asyncio
async def test_send_text_empty_line_skipped() -> None:
    """Empty lines in payload don't generate literal send-keys calls."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    await backend.send_text("claudeorch:test", "line1\n\nline2")
    literal_calls = [c for c in calls if c[0] == "-l"]
    assert len(literal_calls) == 2, (
        f"Expected only 'line1' and 'line2' as literal calls, got {literal_calls}"
    )


@pytest.mark.asyncio
async def test_send_text_press_enter_true_also_submits() -> None:
    """press_enter=True (legacy callers) still sends C-j submit."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    ok = await backend.send_text("claudeorch:test", "hi", press_enter=True)
    assert ok is True
    assert calls[-1] == ["C-j"], f"press_enter=True should still use C-j, got {calls[-1]}"


@pytest.mark.asyncio
async def test_send_text_submit_only_no_press_enter() -> None:
    """submit=True, press_enter=False: still sends C-j."""
    backend = TmuxBackend()
    calls: list[list[str]] = []

    async def fake_tmux_send(target: str, extra: list[str]) -> bool:
        calls.append(list(extra))
        return True

    backend._tmux_send = fake_tmux_send  # type: ignore[method-assign]

    ok = await backend.send_text("claudeorch:test", "msg", press_enter=False, submit=True)
    assert ok is True
    assert calls[-1] == ["C-j"], f"submit=True should send C-j, got {calls[-1]}"
