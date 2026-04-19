"""Discord bridge + REST endpoints.

Covers the same surface as ``test_telegram_bridge.py`` adapted for the
Discord flow:

- ``POST /messenger/discord/configure``: format-only validation (no live
  probe — discord.py can't cheaply check a token without opening a
  gateway). 200 on well-shaped token + writes ``messenger-discord.json``;
  400 on malformed input, no file write.
- ``POST /messenger/discord/start-pairing``: nonce shape + per-call
  freshness + TTL eviction.
- ``GET /messenger/discord/status``: reads the JSON file and maps
  token+paired → ``connected``, token-only → ``connecting``, neither →
  ``not-connected``.
- ``DiscordBridge`` constructor + ``accept_pairing`` TTL semantics,
  lifecycle (``start``/``stop`` idempotence, client teardown), and the
  slash-command handlers ``_on_pair`` / ``_on_ask`` via a duck-typed
  interaction stub.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import (  # noqa: E402
    DISCORD_PAIR_CODE_LEN,
    DISCORD_PAIR_TTL,
    CommunicationServer,
)
from core.messengers.discord import (  # noqa: E402
    DiscordBridge,
    is_valid_token_format,
)


# A well-shaped Discord bot token for constructor tests. Not a real
# token — just matches the regex (<id>.<ts>.<hmac>).
_GOOD_TOKEN = (
    "MTIzNDU2Nzg5MDEyMzQ1Njc4OQ"  # id segment
    ".GabcDE"                       # ts segment
    ".abcdefghijklmnopqrstuvwxyz_-1234567890"  # hmac segment
)


# ------------------------------------------------------------------
# shared helpers
# ------------------------------------------------------------------


def _build_server(tmp_path: Path) -> CommunicationServer:
    return CommunicationServer(
        ws_host="127.0.0.1",
        ws_port=0,
        rest_host="127.0.0.1",
        rest_port=0,
        db_path=Path(":memory:"),
    )


def _client(server: CommunicationServer) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server._rest_app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _discord_state_file(tmp_path: Path) -> Path:
    return tmp_path / ".claudeorch" / "messenger-discord.json"


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same hermetic setup as test_telegram_bridge — env var + cache clears."""
    import core.paths as paths

    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


# ------------------------------------------------------------------
# /configure
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_success_writes_state(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/discord/configure", json={"token": _GOOD_TOKEN}
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"ok": True}

    state_path = _discord_state_file(tmp_path)
    assert state_path.exists(), "configure should persist state file"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["token"] == _GOOD_TOKEN
    # bot_user is null until the bridge fills it in on ready.
    assert data["bot_user"] is None


@pytest.mark.asyncio
async def test_configure_invalid_token_rejects(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/discord/configure", json={"token": "not-a-token"}
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "format" in body["error"]
    assert not _discord_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_preserves_paired_user(tmp_path: Path) -> None:
    """Re-configure after pairing must keep paired_user_id."""
    state_path = _discord_state_file(tmp_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "token": "old.old.oldoldoldoldoldoldoldold",
                "bot_user": "OldBot#1234",
                "paired_user_id": 777,
            }
        ),
        encoding="utf-8",
    )

    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/discord/configure", json={"token": _GOOD_TOKEN}
        )

    assert resp.status_code == 200
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["token"] == _GOOD_TOKEN
    assert data["paired_user_id"] == 777
    # bot_user is re-used from the previous state (bridge will refresh on ready).
    assert data["bot_user"] == "OldBot#1234"


@pytest.mark.asyncio
async def test_configure_bad_json(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/discord/configure", content=b"not-json"
        )
    assert resp.status_code == 400


# ------------------------------------------------------------------
# /start-pairing
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_pairing_returns_valid_code_shape(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post("/messenger/discord/start-pairing")

    assert resp.status_code == 200
    code = resp.json()["code"]
    assert isinstance(code, str)
    assert len(code) == DISCORD_PAIR_CODE_LEN
    assert code.isalnum()
    assert code.upper() == code


@pytest.mark.asyncio
async def test_start_pairing_ancient_codes_evict(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    now = [1000.0]
    srv._discord_clock = lambda: now[0]

    async with _client(srv) as c:
        first = (await c.post("/messenger/discord/start-pairing")).json()[
            "code"
        ]
        assert first in srv._discord_pairs
        now[0] += DISCORD_PAIR_TTL + 1.0
        (await c.post("/messenger/discord/start-pairing")).json()["code"]

    assert first not in srv._discord_pairs


@pytest.mark.asyncio
async def test_start_pairing_does_not_leak_into_telegram(tmp_path: Path) -> None:
    """Discord and Telegram stores must be fully separate."""
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        d_code = (await c.post("/messenger/discord/start-pairing")).json()[
            "code"
        ]
        t_code = (await c.post("/messenger/telegram/start-pairing")).json()[
            "code"
        ]

    assert d_code in srv._discord_pairs
    assert d_code not in srv._telegram_pairs
    assert t_code in srv._telegram_pairs
    assert t_code not in srv._discord_pairs


# ------------------------------------------------------------------
# /status
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reflects_disk_state(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)

    async with _client(srv) as c:
        resp = await c.get("/messenger/discord/status")
    assert resp.json() == {
        "status": "not-connected",
        "bot_user": None,
        "paired_user_id": None,
    }

    state_file = _discord_state_file(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"token": "abc", "bot_user": "MyBot#0001"}),
        encoding="utf-8",
    )

    async with _client(srv) as c:
        resp = await c.get("/messenger/discord/status")
    assert resp.json() == {
        "status": "connecting",
        "bot_user": "MyBot#0001",
        "paired_user_id": None,
    }

    state_file.write_text(
        json.dumps(
            {
                "token": "abc",
                "bot_user": "MyBot#0001",
                "paired_user_id": 123456,
            }
        ),
        encoding="utf-8",
    )

    async with _client(srv) as c:
        resp = await c.get("/messenger/discord/status")
    assert resp.json() == {
        "status": "connected",
        "bot_user": "MyBot#0001",
        "paired_user_id": 123456,
    }


# ------------------------------------------------------------------
# DiscordBridge constructor + pairing
# ------------------------------------------------------------------


class _OrchStub:
    def __init__(self) -> None:
        self.spawn_calls: list[str] = []
        self.active_agents: dict[str, Any] = {}

    def active(self) -> dict[str, Any]:
        return dict(self.active_agents)

    async def spawn_role(self, role: str) -> bool:
        self.spawn_calls.append(role)
        self.active_agents[role] = object()
        return True


def test_is_valid_token_format() -> None:
    assert is_valid_token_format(_GOOD_TOKEN)
    assert not is_valid_token_format("no-dots-here")
    assert not is_valid_token_format("a.b.c")  # segments too short
    assert not is_valid_token_format("")
    assert not is_valid_token_format("only.two.")


def test_bridge_rejects_bad_token_on_construct() -> None:
    orch = _OrchStub()
    with pytest.raises(ValueError):
        DiscordBridge("garbage", orch)  # type: ignore[arg-type]


async def _noop_gateway(bridge: DiscordBridge) -> None:
    # Default no-op for lifecycle tests. Parks until cancel so start/stop
    # exercise the cancel path. Real gateway is in _default_gateway.
    try:
        while bridge.running:
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        raise


@pytest.mark.asyncio
async def test_bridge_start_stop_tracks_task_and_cancels_cleanly() -> None:
    orch = _OrchStub()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_gateway(bridge: DiscordBridge) -> None:
        started.set()
        try:
            while bridge.running:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        client_factory=fake_gateway,
    )

    assert not bridge.running
    await bridge.start()
    first_task = bridge.task
    # start() is idempotent — second call leaves the task intact.
    await bridge.start()
    assert bridge.task is first_task

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert bridge.running
    assert bridge.task is not None
    assert not bridge.task.done()

    await bridge.stop()
    assert not bridge.running
    assert bridge.task is None
    assert cancelled.is_set()

    # stop() is idempotent
    await bridge.stop()


@pytest.mark.asyncio
async def test_bridge_stop_closes_client_handle() -> None:
    """When a client is attached (real gateway path), stop() awaits close."""
    orch = _OrchStub()
    close_calls: list[int] = []

    class _FakeClient:
        async def close(self) -> None:
            close_calls.append(1)

    async def gateway_with_client(bridge: DiscordBridge) -> None:
        bridge._client = _FakeClient()
        try:
            while bridge.running:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise

    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        client_factory=gateway_with_client,
    )

    await bridge.start()
    await asyncio.sleep(0)  # let the gateway coroutine assign the client
    await bridge.stop()
    assert close_calls == [1]


@pytest.mark.asyncio
async def test_bridge_accept_pairing_honors_ttl(tmp_path: Path) -> None:
    orch = _OrchStub()
    state_path = tmp_path / "messenger-discord.json"

    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        state_path=state_path,
        client_factory=_noop_gateway,
    )

    bridge.register_pairing_code("AAA111", ts=100.0)
    assert bridge.accept_pairing("AAA111", user_id=42, now=150.0, ttl=300.0)
    assert 42 in bridge.allowlist
    assert json.loads(state_path.read_text())["paired_user_id"] == 42

    # Replay rejected
    assert not bridge.accept_pairing("AAA111", user_id=99, now=151.0, ttl=300.0)
    # Expired code rejected
    bridge.register_pairing_code("BBB222", ts=100.0)
    assert not bridge.accept_pairing("BBB222", user_id=7, now=500.0, ttl=300.0)
    assert 7 not in bridge.allowlist


# ------------------------------------------------------------------
# _on_pair / _on_ask handler coverage
# ------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for discord.InteractionResponse."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []
        self.deferred: list[bool] = []

    async def send_message(self, text: str, *, ephemeral: bool = False) -> None:
        self.sent.append((text, ephemeral))

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.deferred.append(ephemeral)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakeInteraction:
    def __init__(
        self,
        user_id: int,
        channel_id: int | None = None,
    ) -> None:
        self.user = _FakeUser(user_id)
        self.channel = _FakeChannel(channel_id) if channel_id is not None else None
        self.response = _FakeResponse()


class _FakeBackend:
    def __init__(self, targets: dict[str, str] | None = None) -> None:
        self._targets = dict(targets or {})
        self.sent: list[tuple[str, str]] = []

    def list_targets(self) -> dict[str, str]:
        return dict(self._targets)

    async def send_text(self, target: str, text: str) -> bool:
        self.sent.append((target, text))
        return True


@pytest.mark.asyncio
async def test_on_pair_success_replies_paired() -> None:
    orch = _OrchStub()
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )
    now = asyncio.get_running_loop().time()
    bridge.register_pairing_code("ABCDEF", ts=now)

    interaction = _FakeInteraction(user_id=42, channel_id=100)
    await bridge._on_pair(interaction, "ABCDEF")

    assert bridge.paired_user_id == 42
    assert 42 in bridge.allowlist
    assert interaction.response.sent == [("Paired \u2713", True)]


@pytest.mark.asyncio
async def test_on_pair_invalid_code_replies_failure() -> None:
    orch = _OrchStub()
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )

    interaction = _FakeInteraction(user_id=42, channel_id=100)
    await bridge._on_pair(interaction, "WRONGCODE")

    assert bridge.paired_user_id is None
    assert interaction.response.sent == [("Invalid/expired code", True)]


@pytest.mark.asyncio
async def test_on_pair_empty_code_shows_usage() -> None:
    orch = _OrchStub()
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )

    interaction = _FakeInteraction(user_id=42, channel_id=100)
    await bridge._on_pair(interaction, "   ")

    assert bridge.paired_user_id is None
    assert interaction.response.sent == [("Usage: /pair <code>", True)]


@pytest.mark.asyncio
async def test_on_ask_parses_and_calls_handle_ask() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    orch.active_agents["backend-dev"] = object()

    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )
    assert bridge.paired_user_id == 42  # derived from single-entry allowlist

    interaction = _FakeInteraction(user_id=42, channel_id=500)
    await bridge._on_ask(interaction, "backend-dev", "please read memory")

    assert backend.sent == [("claudeorch:backend-dev", "please read memory")]
    assert orch.spawn_calls == []
    # Echo uses the "[agent] sent: <first-line>" shape per spec.
    assert interaction.response.sent == [
        ("[backend-dev] sent: please read memory", True)
    ]


@pytest.mark.asyncio
async def test_on_ask_drops_non_paired_user_with_silent_defer() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )

    interaction = _FakeInteraction(user_id=999, channel_id=500)
    await bridge._on_ask(interaction, "backend-dev", "hello")

    # No pane write, no visible reply — just a silent ephemeral defer.
    assert backend.sent == []
    assert orch.spawn_calls == []
    assert interaction.response.sent == []
    assert interaction.response.deferred == [True]


@pytest.mark.asyncio
async def test_on_ask_missing_text_shows_usage() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )

    interaction = _FakeInteraction(user_id=42, channel_id=500)
    await bridge._on_ask(interaction, "backend-dev", "")

    assert backend.sent == []
    assert interaction.response.sent == [("Usage: /ask <agent> <text>", True)]


@pytest.mark.asyncio
async def test_on_ask_spawns_when_agent_inactive() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    bridge = DiscordBridge(
        _GOOD_TOKEN,
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        client_factory=_noop_gateway,
    )

    interaction = _FakeInteraction(user_id=42, channel_id=500)
    await bridge._on_ask(interaction, "backend-dev", "wake up")

    # spawn_role was called because the agent wasn't active at dispatch.
    assert orch.spawn_calls == ["backend-dev"]
    assert backend.sent == [("claudeorch:backend-dev", "wake up")]


# ------------------------------------------------------------------
# _maybe_start_discord_bridge (boot hook)
# ------------------------------------------------------------------


def _write_state(tmp_path: Path, data: dict[str, Any]) -> Path:
    state_dir = tmp_path / ".claudeorch"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "messenger-discord.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_boot_hook_returns_none_when_no_state_file(tmp_path: Path) -> None:
    from core.main import _maybe_start_discord_bridge

    orch = _OrchStub()
    result = await _maybe_start_discord_bridge(orch, backend=None)
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_returns_none_on_malformed_token(tmp_path: Path) -> None:
    from core.main import _maybe_start_discord_bridge

    _write_state(tmp_path, {"token": "not-a-token"})
    orch = _OrchStub()
    result = await _maybe_start_discord_bridge(orch, backend=None)
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_starts_bridge_on_valid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.main import _maybe_start_discord_bridge
    from core.messengers import discord as disc_module

    _write_state(
        tmp_path,
        {
            "token": _GOOD_TOKEN,
            "bot_user": "MyBot#0001",
            "paired_user_id": 42,
        },
    )

    start_calls: list[int] = []
    real_start = disc_module.DiscordBridge.start

    async def fake_start(self: disc_module.DiscordBridge) -> None:
        start_calls.append(1)
        self._running = True

    monkeypatch.setattr(disc_module.DiscordBridge, "start", fake_start)

    orch = _OrchStub()
    bridge = await _maybe_start_discord_bridge(orch, backend=None)
    try:
        assert bridge is not None
        assert isinstance(bridge, disc_module.DiscordBridge)
        assert start_calls == [1]
        assert 42 in bridge.allowlist
        assert bridge.paired_user_id == 42
    finally:
        if bridge is not None:
            bridge._running = False
        monkeypatch.setattr(disc_module.DiscordBridge, "start", real_start)


@pytest.mark.asyncio
async def test_boot_hook_survives_bridge_construction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.main import _maybe_start_discord_bridge
    from core.messengers import discord as disc_module

    _write_state(tmp_path, {"token": _GOOD_TOKEN})

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated ctor failure")

    monkeypatch.setattr(disc_module, "DiscordBridge", boom)

    orch = _OrchStub()
    result = await _maybe_start_discord_bridge(orch, backend=None)
    assert result is None


@pytest.mark.asyncio
async def test_boot_hook_survives_bridge_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.main import _maybe_start_discord_bridge
    from core.messengers import discord as disc_module

    _write_state(tmp_path, {"token": _GOOD_TOKEN})

    async def boom_start(self: disc_module.DiscordBridge) -> None:
        raise RuntimeError("simulated start failure")

    monkeypatch.setattr(disc_module.DiscordBridge, "start", boom_start)

    orch = _OrchStub()
    result = await _maybe_start_discord_bridge(orch, backend=None)
    assert result is None
