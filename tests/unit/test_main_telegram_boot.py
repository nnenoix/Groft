"""main.py boot hook for the Telegram bridge.

We exercise ``_maybe_start_telegram_bridge`` directly instead of standing up
the whole ``main()`` coroutine — the hook is a pure function of its inputs
(orchestrator, backend, on-disk JSON) and that's the contract PR 6.2 adds.

Covered paths:
- JSON missing: returns None silently.
- JSON with malformed token: returns None, no bridge.
- JSON with valid token: constructs bridge, calls ``start()``.
- JSON with valid token but PTB import shimmed to fail: returns None, no
  crash in boot (degrades to warning).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.main import _maybe_start_telegram_bridge  # noqa: E402


class _OrchStub:
    def __init__(self) -> None:
        self.spawn_calls: list[str] = []
        self.active_agents: dict[str, Any] = {}

    def active(self) -> dict[str, Any]:
        return dict(self.active_agents)

    async def spawn_role(self, role: str) -> bool:
        self.spawn_calls.append(role)
        return True


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point CLAUDEORCH_USER_DATA at tmp_path so state reads stay hermetic."""
    import core.paths as paths

    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


def _write_state(tmp_path: Path, data: dict[str, Any]) -> Path:
    state_dir = tmp_path / ".claudeorch"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "messenger-telegram.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_boot_hook_returns_none_when_no_state_file(tmp_path: Path) -> None:
    # No messenger-telegram.json anywhere under tmp_path.claudeorch.
    orch = _OrchStub()
    result = await _maybe_start_telegram_bridge(orch, backend=None)
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_returns_none_on_malformed_token(tmp_path: Path) -> None:
    _write_state(tmp_path, {"token": "not-a-token"})
    orch = _OrchStub()
    result = await _maybe_start_telegram_bridge(orch, backend=None)
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_starts_bridge_on_valid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_state(
        tmp_path,
        {
            "token": "123456:ABCdef_ghi-JKL",
            "username": "my_test_bot",
            "paired_user_id": 42,
        },
    )

    # Mock TelegramBridge.start so no network/polling ever boots. We observe
    # by counting start() calls on the returned bridge object.
    from core.messengers import telegram as tg_module

    start_calls: list[int] = []
    real_start = tg_module.TelegramBridge.start

    async def fake_start(self: tg_module.TelegramBridge) -> None:
        start_calls.append(1)
        # Don't actually invoke real_start — that would spin up the default
        # polling factory and try to import python-telegram-bot.
        self._running = True

    monkeypatch.setattr(tg_module.TelegramBridge, "start", fake_start)

    orch = _OrchStub()
    bridge = await _maybe_start_telegram_bridge(orch, backend=None)
    try:
        assert bridge is not None
        assert isinstance(bridge, tg_module.TelegramBridge)
        assert start_calls == [1]
        # Allowlist seeded from paired_user_id on disk.
        assert 42 in bridge.allowlist
        assert bridge.paired_user_id == 42
    finally:
        # Reset running so bridge cleanup is trivial (no real task was made).
        if bridge is not None:
            bridge._running = False
        monkeypatch.setattr(tg_module.TelegramBridge, "start", real_start)


@pytest.mark.asyncio
async def test_boot_hook_survives_bridge_construction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_state(tmp_path, {"token": "123456:ABCdef_ghi-JKL"})

    from core.messengers import telegram as tg_module

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated ctor failure")

    monkeypatch.setattr(tg_module, "TelegramBridge", boom)

    orch = _OrchStub()
    result = await _maybe_start_telegram_bridge(orch, backend=None)
    # Hook swallows the error and returns None — boot must keep going.
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_survives_bridge_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_state(tmp_path, {"token": "123456:ABCdef_ghi-JKL"})

    from core.messengers import telegram as tg_module

    async def boom_start(self: tg_module.TelegramBridge) -> None:
        raise RuntimeError("simulated start failure")

    monkeypatch.setattr(tg_module.TelegramBridge, "start", boom_start)

    orch = _OrchStub()
    result = await _maybe_start_telegram_bridge(orch, backend=None)
    assert result is None
