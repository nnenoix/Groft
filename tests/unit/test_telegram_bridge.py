"""Telegram bridge + REST endpoints.

Covers:
- ``POST /messenger/telegram/configure``: getMe probe is mocked via httpx's
  MockTransport so the test never touches the network. We assert the
  success path writes ``.claudeorch/messenger-telegram.json`` and the
  bad-token path returns 400 without any file write.
- ``POST /messenger/telegram/start-pairing``: shape of the nonce, second
  call issues a fresh code while the first remains valid within TTL, and
  aged nonces evict after the bridge's internal clock advances.
- ``TelegramBridge.start()/stop()``: polling is swapped for an
  ``asyncio.sleep(0)`` loop via ``polling_factory`` so we can assert the
  task is tracked and cancelled cleanly.
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
    TELEGRAM_PAIR_CODE_LEN,
    TELEGRAM_PAIR_TTL,
    CommunicationServer,
)
from core.messengers.telegram import (  # noqa: E402
    TelegramBridge,
    is_valid_token_format,
)


# ------------------------------------------------------------------
# shared helpers
# ------------------------------------------------------------------


def _build_server(tmp_path: Path) -> CommunicationServer:
    # Isolate the .claudeorch dir to tmp_path so concurrent tests don't
    # fight over messenger-telegram.json. core/paths reads CLAUDEORCH_USER_DATA
    # at call-time and uses functools.cache, so we import-and-reset it below
    # via monkeypatch in each test.
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


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point CLAUDEORCH_USER_DATA at tmp_path and clear cached resolvers.

    Without this, every test would share the developer's real .claudeorch
    and leak state into each other. The ``@functools.cache`` on
    ``install_root``/``user_data_root`` is cleared so the env var actually
    takes effect in this process.
    """
    import core.paths as paths

    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


# ------------------------------------------------------------------
# configure endpoint
# ------------------------------------------------------------------


def _telegram_state_file(tmp_path: Path) -> Path:
    return tmp_path / ".claudeorch" / "messenger-telegram.json"


@pytest.mark.asyncio
async def test_configure_success_writes_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srv = _build_server(tmp_path)

    # Handler mocks Telegram's getMe endpoint. Anything else = hard fail so
    # we notice if the server starts hitting unexpected URLs.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getMe"), request.url
        assert "123456:ABCdef_ghi-JKL" in str(request.url)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"id": 1, "is_bot": True, "username": "my_test_bot"},
            },
        )

    transport = httpx.MockTransport(handler)

    # Monkeypatch httpx.AsyncClient to use our mock transport whenever the
    # endpoint constructs one. The handler constructs a fresh client per
    # call, so we replace the class's __init__ to inject transport.
    real_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", transport)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/telegram/configure",
            json={"token": "123456:ABCdef_ghi-JKL"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"ok": True, "username": "my_test_bot"}

    state_path = _telegram_state_file(tmp_path)
    assert state_path.exists(), "configure should persist state file"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["token"] == "123456:ABCdef_ghi-JKL"
    assert data["username"] == "my_test_bot"


@pytest.mark.asyncio
async def test_configure_invalid_token_format_rejects_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srv = _build_server(tmp_path)

    # Guard: if the endpoint still reaches httpx with a bad token, this
    # handler raises and the test fails loudly.
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network should not be hit: {request.url}")

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", transport)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/telegram/configure", json={"token": "not-a-token"}
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "format" in body["error"]
    # No state written
    assert not _telegram_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_getme_rejects_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Well-formed token but Telegram refuses → 400, no state written."""
    srv = _build_server(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"ok": False, "description": "Unauthorized"}
        )

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", transport)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/telegram/configure",
            json={"token": "999:AAAbbbCCC_ddd-EEE"},
        )

    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert not _telegram_state_file(tmp_path).exists()


# ------------------------------------------------------------------
# start-pairing + status
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_pairing_returns_valid_code_shape(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)
    async with _client(srv) as c:
        resp = await c.post("/messenger/telegram/start-pairing")

    assert resp.status_code == 200
    body = resp.json()
    assert "code" in body
    code = body["code"]
    assert isinstance(code, str)
    assert len(code) == TELEGRAM_PAIR_CODE_LEN
    # Alphabet is a restricted subset — assert it's uppercase alnum at minimum.
    assert code.isalnum()
    assert code.upper() == code


@pytest.mark.asyncio
async def test_start_pairing_second_call_issues_new_code_old_remains_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srv = _build_server(tmp_path)

    # Freeze clock so no TTL expiry interferes with "both codes live" check.
    now = [1000.0]
    srv._telegram_clock = lambda: now[0]

    async with _client(srv) as c:
        first = (await c.post("/messenger/telegram/start-pairing")).json()["code"]
        # Advance 10s — still well within TTL.
        now[0] += 10.0
        second = (await c.post("/messenger/telegram/start-pairing")).json()["code"]

    assert first != second
    assert first in srv._telegram_pairs
    assert second in srv._telegram_pairs


@pytest.mark.asyncio
async def test_start_pairing_ancient_codes_evict(
    tmp_path: Path,
) -> None:
    srv = _build_server(tmp_path)

    now = [1000.0]
    srv._telegram_clock = lambda: now[0]

    async with _client(srv) as c:
        first = (await c.post("/messenger/telegram/start-pairing")).json()["code"]
        assert first in srv._telegram_pairs
        # Jump past TTL — next issue should GC the expired nonce.
        now[0] += TELEGRAM_PAIR_TTL + 1.0
        (await c.post("/messenger/telegram/start-pairing")).json()["code"]

    assert first not in srv._telegram_pairs


@pytest.mark.asyncio
async def test_status_reflects_disk_state(tmp_path: Path) -> None:
    srv = _build_server(tmp_path)

    # Before any configure: not-connected
    async with _client(srv) as c:
        resp = await c.get("/messenger/telegram/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "not-connected",
        "username": None,
        "paired_user_id": None,
    }

    # After configure (manual write — configure endpoint is already covered):
    state_file = _telegram_state_file(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"token": "abc", "username": "my_bot"}), encoding="utf-8"
    )

    async with _client(srv) as c:
        resp = await c.get("/messenger/telegram/status")
    assert resp.json() == {
        "status": "connecting",
        "username": "my_bot",
        "paired_user_id": None,
    }

    # After pairing:
    state_file.write_text(
        json.dumps(
            {"token": "abc", "username": "my_bot", "paired_user_id": 42}
        ),
        encoding="utf-8",
    )

    async with _client(srv) as c:
        resp = await c.get("/messenger/telegram/status")
    assert resp.json() == {
        "status": "connected",
        "username": "my_bot",
        "paired_user_id": 42,
    }


# ------------------------------------------------------------------
# TelegramBridge lifecycle
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
    assert is_valid_token_format("123456:ABCdef_ghi-JKL")
    assert not is_valid_token_format("no-colon-here")
    assert not is_valid_token_format("123:")
    assert not is_valid_token_format(":ABC")
    assert not is_valid_token_format("")


def test_bridge_rejects_bad_token_on_construct() -> None:
    orch = _OrchStub()
    with pytest.raises(ValueError):
        TelegramBridge("garbage", orch)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_bridge_start_stop_tracks_task_and_cancels_cleanly() -> None:
    orch = _OrchStub()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_polling(bridge: TelegramBridge) -> None:
        # Signal we were launched so the test can observe task-liveness
        # before issuing stop(); then park until cancel.
        started.set()
        try:
            while bridge.running:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        polling_factory=fake_polling,
    )

    assert not bridge.running
    await bridge.start()
    # start() is idempotent — second call is a no-op, task stays the same.
    first_task = bridge.task
    await bridge.start()
    assert bridge.task is first_task

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert bridge.running
    assert bridge.task is not None
    assert not bridge.task.done()

    await bridge.stop()
    assert not bridge.running
    assert bridge.task is None
    # fake_polling's except-block should have fired
    assert cancelled.is_set()

    # stop() is idempotent — second call is a no-op
    await bridge.stop()


@pytest.mark.asyncio
async def test_bridge_accept_pairing_honors_ttl(tmp_path: Path) -> None:
    orch = _OrchStub()
    state_path = tmp_path / "messenger-telegram.json"

    async def noop_polling(bridge: TelegramBridge) -> None:
        # Never actually used — we're just testing pairing arithmetic.
        await asyncio.sleep(0)

    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        state_path=state_path,
        polling_factory=noop_polling,
    )

    bridge.register_pairing_code("AAA111", ts=100.0)
    # Within TTL
    assert bridge.accept_pairing("AAA111", user_id=42, now=150.0, ttl=300.0)
    assert 42 in bridge.allowlist
    # Persisted to disk
    assert json.loads(state_path.read_text())["paired_user_id"] == 42

    # Same code can't be replayed
    assert not bridge.accept_pairing("AAA111", user_id=99, now=151.0, ttl=300.0)
    # Fresh code past TTL is rejected
    bridge.register_pairing_code("BBB222", ts=100.0)
    assert not bridge.accept_pairing("BBB222", user_id=7, now=500.0, ttl=300.0)
    assert 7 not in bridge.allowlist


# ------------------------------------------------------------------
# PTB handler coverage — _on_pair / _on_ask / _on_fallback
# ------------------------------------------------------------------


class _FakeMessage:
    """Minimal stand-in for telegram.Message — only the bits our handlers touch."""

    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _FakeUpdate:
    def __init__(
        self,
        user_id: int,
        chat_id: int | None = None,
        message: _FakeMessage | None = None,
    ) -> None:
        self.effective_user = _FakeUser(user_id)
        self.effective_chat = _FakeChat(chat_id) if chat_id is not None else None
        self.effective_message = message or _FakeMessage()
        # PTB also exposes update.message alongside effective_message; the
        # handlers read either one, so mirror the same object here.
        self.message = self.effective_message


class _FakeContext:
    def __init__(self, args: list[str]) -> None:
        self.args = list(args)


class _FakeBackend:
    """ProcessBackend stub — records send_text calls and fakes list_targets."""

    def __init__(self, targets: dict[str, str] | None = None) -> None:
        self._targets = dict(targets or {})
        self.sent: list[tuple[str, str]] = []

    def list_targets(self) -> dict[str, str]:
        return dict(self._targets)

    async def send_text(self, target: str, text: str) -> bool:
        self.sent.append((target, text))
        return True


async def _noop_polling(bridge: TelegramBridge) -> None:
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_on_pair_success_replies_paired() -> None:
    orch = _OrchStub()
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )
    # Seed a code; handler uses loop.time() for the "now" probe so we freeze
    # that window by registering with the current loop time.
    now = asyncio.get_running_loop().time()
    bridge.register_pairing_code("ABCDEF", ts=now)

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=100, message=msg)
    context = _FakeContext(args=["ABCDEF"])

    await bridge._on_pair(update, context)

    assert bridge.paired_user_id == 42
    assert 42 in bridge.allowlist
    # \u2713 = check mark — the handler uses the unicode char directly
    assert msg.replies == ["Paired \u2713"]


@pytest.mark.asyncio
async def test_on_pair_invalid_code_replies_failure() -> None:
    orch = _OrchStub()
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )
    # No code registered — any input is invalid.

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=100, message=msg)
    context = _FakeContext(args=["WRONGCODE"])

    await bridge._on_pair(update, context)

    assert bridge.paired_user_id is None
    assert msg.replies == ["Invalid/expired code"]


@pytest.mark.asyncio
async def test_on_pair_missing_arg_shows_usage() -> None:
    orch = _OrchStub()
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=100, message=msg)
    context = _FakeContext(args=[])

    await bridge._on_pair(update, context)

    assert bridge.paired_user_id is None
    assert msg.replies == ["Usage: /pair <code>"]


@pytest.mark.asyncio
async def test_on_ask_parses_agent_and_calls_handle_ask() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    # Pre-seed the agent as active so spawn_role doesn't get called (the test
    # is about argv parsing + dispatch, not spawn).
    orch.active_agents["backend-dev"] = object()

    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )
    assert bridge.paired_user_id == 42  # derived from single-entry allowlist

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=500, message=msg)
    context = _FakeContext(args=["backend-dev", "please", "read", "memory"])

    await bridge._on_ask(update, context)

    # handle_ask should have routed to the backend with the joined tail.
    assert backend.sent == [("claudeorch:backend-dev", "please read memory")]
    # spawn_role is NOT called because the agent is already active.
    assert orch.spawn_calls == []


@pytest.mark.asyncio
async def test_on_ask_drops_non_paired_user() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )

    msg = _FakeMessage()
    # user_id 999 is NOT paired.
    update = _FakeUpdate(user_id=999, chat_id=500, message=msg)
    context = _FakeContext(args=["backend-dev", "hello"])

    await bridge._on_ask(update, context)

    # No pane write, no spawn, no reply — we silently drop strangers.
    assert backend.sent == []
    assert orch.spawn_calls == []
    assert msg.replies == []


@pytest.mark.asyncio
async def test_on_ask_missing_text_shows_usage() -> None:
    orch = _OrchStub()
    backend = _FakeBackend(targets={"backend-dev": "claudeorch:backend-dev"})
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        allowlist={42},
        backend=backend,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=500, message=msg)
    context = _FakeContext(args=["backend-dev"])  # no text

    await bridge._on_ask(update, context)

    assert backend.sent == []
    assert msg.replies == ["Usage: /ask <agent> <text>"]


@pytest.mark.asyncio
async def test_on_fallback_replies_hint() -> None:
    orch = _OrchStub()
    bridge = TelegramBridge(
        "123456:ABCdef_ghi-JKL",
        orch,  # type: ignore[arg-type]
        polling_factory=_noop_polling,
    )

    msg = _FakeMessage()
    update = _FakeUpdate(user_id=42, chat_id=500, message=msg)
    context = _FakeContext(args=[])

    await bridge._on_fallback(update, context)

    assert len(msg.replies) == 1
    assert "/ask" in msg.replies[0]
    assert "/pair" in msg.replies[0]
