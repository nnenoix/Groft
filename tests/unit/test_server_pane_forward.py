"""Tests for _forward_to_pane / _resolve_pane_target behaviour."""
from __future__ import annotations

import asyncio
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
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.paths as paths
    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


class _FakeBackend:
    def __init__(self, targets: dict[str, str]) -> None:
        self._targets = dict(targets)
        self.sent: list[tuple[str, str]] = []

    def list_targets(self) -> dict[str, str]:
        return dict(self._targets)

    async def send_text(self, target: str, text: str, **kwargs: Any) -> bool:
        self.sent.append((target, text))
        return True

    async def shutdown(self) -> None:
        pass


def _make_server(backend: _FakeBackend | None = None, lead: str = "claudeorch:0") -> CommunicationServer:
    srv = CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=0,
        rest_host="127.0.0.1",
        rest_port=0,
        db_path=Path(":memory:"),
        lead_target=lead,
        backend=backend,
    )
    return srv


@pytest.mark.asyncio
async def test_unknown_target_does_not_forward_to_lead() -> None:
    """send_message to unknown agent must NOT echo to lead_target (opus pane)."""
    backend = _FakeBackend(targets={})  # no agents registered
    srv = _make_server(backend=backend, lead="claudeorch:0")

    await srv._forward_to_pane("unknown-agent", "hello")

    # send_text must never be called — not to lead, not to anyone
    assert backend.sent == [], f"Expected no pane forward, got: {backend.sent}"


@pytest.mark.asyncio
async def test_known_target_forwards_to_its_pane() -> None:
    """send_message to registered agent goes to its pane, not lead."""
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    srv = _make_server(backend=backend, lead="claudeorch:0")

    await srv._forward_to_pane("backend-dev", "do the thing")

    assert backend.sent == [("claudeorch:backend-dev", "do the thing")]


@pytest.mark.asyncio
async def test_echo_regression_unregistered_does_not_reach_lead() -> None:
    """Regression: frontend-dev not in list_targets → send_text not called at all."""
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    srv = _make_server(backend=backend, lead="claudeorch:0")

    await srv._forward_to_pane("frontend-dev", "test message")

    # Must not forward to backend-dev's pane nor to lead
    assert backend.sent == []


@pytest.mark.asyncio
async def test_resolve_pane_target_fallback_explicit() -> None:
    """fallback_to_lead=True must still return lead_target for unknown agent."""
    backend = _FakeBackend(targets={})
    srv = _make_server(backend=backend, lead="claudeorch:0")

    result = srv._resolve_pane_target("nobody", fallback_to_lead=True)
    assert result == "claudeorch:0"


@pytest.mark.asyncio
async def test_resolve_pane_target_no_fallback_default() -> None:
    """By default (fallback_to_lead=False), unknown agent returns None."""
    backend = _FakeBackend(targets={})
    srv = _make_server(backend=backend, lead="claudeorch:0")

    result = srv._resolve_pane_target("nobody")
    assert result is None
