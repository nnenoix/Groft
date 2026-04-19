"""IMessageBridge + REST endpoint coverage.

Covers:
- Non-Darwin: ``notify`` returns False without spawning osascript;
  ``test()`` returns a shaped ``{ok: False, platform, error}`` dict.
- Darwin stub: with ``IS_MACOS`` monkeypatched to True and
  ``subprocess.run`` mocked, ``notify`` composes the expected
  AppleScript string and returns True on ``returncode == 0``.
- Escaping: text containing backslashes and double quotes must not
  break the generated AppleScript command.
- REST endpoints:
  - ``/configure`` shape-validates and writes the state file; surfaces
    ``supported`` based on ``sys.platform``.
  - ``/test`` on non-macOS returns ``{ok: false, ...}`` without
    touching subprocess.
  - ``/status`` reports ``unsupported`` when platform != darwin,
    regardless of saved config.

Platform mocking strategy: the bridge captures ``sys.platform`` once at
import time into ``imessage.IS_MACOS``. We monkeypatch that module
attribute (cheap, scoped, doesn't leak into other tests). For the
server endpoints we monkeypatch ``communication.server.sys.platform``
— the endpoints read it live on each call.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import CommunicationServer  # noqa: E402
from core.messengers import imessage  # noqa: E402
from core.messengers.imessage import IMessageBridge  # noqa: E402


# ------------------------------------------------------------------
# shared helpers / fixtures
# ------------------------------------------------------------------


def _build_server() -> CommunicationServer:
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


def _imessage_state_file(tmp_path: Path) -> Path:
    return tmp_path / ".claudeorch" / "messenger-imessage.json"


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route CLAUDEORCH_USER_DATA to tmp_path; reset path caches.

    Same pattern as test_webhook_bridge.py / test_telegram_bridge.py —
    without it the tests would touch the real ``.claudeorch`` dir and
    leak state across runs.
    """
    import core.paths as paths

    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


# ------------------------------------------------------------------
# Constructor
# ------------------------------------------------------------------


def test_bridge_accepts_email_contact() -> None:
    b = IMessageBridge(contact="alice@example.com")
    assert b.contact == "alice@example.com"


def test_bridge_accepts_phone_contact() -> None:
    b = IMessageBridge(contact="+15551234567")
    assert b.contact == "+15551234567"


def test_bridge_strips_whitespace() -> None:
    b = IMessageBridge(contact="  alice@example.com  ")
    assert b.contact == "alice@example.com"


def test_bridge_rejects_empty_contact() -> None:
    with pytest.raises(ValueError):
        IMessageBridge(contact="")


def test_bridge_rejects_whitespace_only_contact() -> None:
    with pytest.raises(ValueError):
        IMessageBridge(contact="   ")


def test_bridge_rejects_overlong_contact() -> None:
    with pytest.raises(ValueError):
        IMessageBridge(contact="x" * 201)


# ------------------------------------------------------------------
# notify / test on non-Darwin (no subprocess)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_on_non_darwin_returns_false_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force IS_MACOS False — same effect as sys.platform != "darwin" but
    # scoped to the bridge module, so we don't perturb the rest of the
    # test suite's platform detection.
    monkeypatch.setattr(imessage, "IS_MACOS", False)

    calls: list[Any] = []

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        # If the bridge reaches subprocess.run on non-Darwin, that's a
        # bug — it should have short-circuited above.
        calls.append((args, kwargs))
        raise AssertionError("subprocess.run must not be called on non-Darwin")

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    result = await b.notify("test", "groft", "hello")
    assert result is False
    assert calls == []


@pytest.mark.asyncio
async def test_test_method_on_non_darwin_returns_shaped_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", False)
    b = IMessageBridge(contact="alice@example.com")
    result = await b.test()
    assert result["ok"] is False
    # platform is whatever the real runner is — should NOT be "darwin"
    # if IS_MACOS was False at bridge-call time. We can't assert the
    # exact string cross-platform, but we can assert the expected shape.
    assert result["platform"] == sys.platform
    assert isinstance(result["error"], str) and result["error"]


# ------------------------------------------------------------------
# notify / test on Darwin (mocked subprocess)
# ------------------------------------------------------------------


def _fake_completed(returncode: int = 0, stderr: bytes = b"") -> Any:
    """Build a stand-in ``subprocess.CompletedProcess`` without args.

    We only read ``returncode`` and ``stderr`` on the result, so a
    minimal object is enough.
    """

    class _Result:
        def __init__(self) -> None:
            self.returncode = returncode
            self.stdout = b""
            self.stderr = stderr

    return _Result()


@pytest.mark.asyncio
async def test_notify_on_darwin_invokes_osascript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pretend we're on macOS for the duration of this test without
    # actually mutating sys.platform — that would leak into every other
    # test running in the same process.
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    b = IMessageBridge(contact="alice@example.com")
    ok = await b.notify("deploy", "backend-dev", "shipped")

    assert ok is True
    assert captured["cmd"][0] == "osascript"
    assert captured["cmd"][1] == "-e"
    script = captured["cmd"][2]
    # The script must be a ``tell application "Messages"`` directive
    # with our rendered body and contact embedded verbatim.
    assert 'tell application "Messages"' in script
    assert "[deploy] backend-dev: shipped" in script
    assert '"alice@example.com"' in script
    # ``service 1`` addresses the first enabled iMessage account.
    assert "service 1" in script
    # Timeout is passed through so osascript can't block the loop
    # indefinitely if Messages.app hangs.
    assert "timeout" in captured["kwargs"]
    assert captured["kwargs"]["timeout"] == pytest.approx(5.0)
    assert captured["kwargs"]["capture_output"] is True


@pytest.mark.asyncio
async def test_notify_on_darwin_returns_false_on_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        return _fake_completed(
            returncode=1, stderr=b"Messages got an error: Can't get buddy"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    ok = await b.notify("test", "groft", "hello")
    assert ok is False


@pytest.mark.asyncio
async def test_notify_on_darwin_returns_false_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    ok = await b.notify("test", "groft", "hello")
    assert ok is False


@pytest.mark.asyncio
async def test_notify_on_darwin_returns_false_when_osascript_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError("osascript")

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    ok = await b.notify("test", "groft", "hello")
    assert ok is False


@pytest.mark.asyncio
async def test_test_method_on_darwin_returns_ok_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    result = await b.test()
    assert result["ok"] is True
    assert result["platform"] == sys.platform
    assert result["error"] is None


# ------------------------------------------------------------------
# Escaping
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_escapes_backslashes_and_quotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imessage, "IS_MACOS", True)
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        captured["cmd"] = cmd
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    b = IMessageBridge(contact="alice@example.com")
    # Text with raw quotes and a backslash — the bridge must not emit
    # an AppleScript string that terminates early or otherwise unravels.
    await b.notify("ev", "ag", 'he said "hello" \\n world')
    script = captured["cmd"][2]
    # Body should contain the escaped forms; originals must not appear
    # as unescaped ``"`` or trailing ``\`` because that would break the
    # surrounding ``"..."`` literal in AppleScript.
    # The input ``"hello"`` → ``\"hello\"`` (backslash-escaped quotes).
    assert '\\"hello\\"' in script
    # The input ``\n`` (literal backslash + n) → ``\\n``.
    assert "\\\\n" in script
    # The rendered body must be wrapped in a single AppleScript string
    # literal that ends with its contact-separator ``to buddy "...``.
    # Use a direct substring check rather than trying to count quotes:
    # we want the literal ``"[ev] ag: he said \"hello\" \\n world"``
    # followed immediately by the literal `` to buddy ``.
    expected_body_literal = (
        '"[ev] ag: he said \\"hello\\" \\\\n world"'
    )
    assert expected_body_literal in script
    assert f"{expected_body_literal} to buddy " in script


# ------------------------------------------------------------------
# /configure endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_success_writes_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pretend we're on darwin so ``supported`` comes back True — the
    # endpoint doesn't touch the bridge, so we don't need to stub
    # IS_MACOS, just the platform string the endpoint reads.
    monkeypatch.setattr("communication.server.sys.platform", "darwin")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/imessage/configure",
            json={"contact": "alice@example.com"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["platform"] == "darwin"
    assert body["supported"] is True
    state_file = _imessage_state_file(tmp_path)
    assert state_file.exists()
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted == {"contact": "alice@example.com"}


@pytest.mark.asyncio
async def test_configure_on_non_darwin_still_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Per spec: supported=false doesn't block configure. The operator
    # may be prepping a config on Linux for later sync to a Mac.
    monkeypatch.setattr("communication.server.sys.platform", "linux")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/imessage/configure",
            json={"contact": "+15551234567"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["platform"] == "linux"
    assert body["supported"] is False
    assert _imessage_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_missing_contact(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/imessage/configure", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert not _imessage_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_empty_contact(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/imessage/configure", json={"contact": "   "}
        )
    assert resp.status_code == 400
    assert not _imessage_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_overlong_contact(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/imessage/configure",
            json={"contact": "x" * 250},
        )
    assert resp.status_code == 400
    assert not _imessage_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_non_object_body(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/imessage/configure",
            content=b"[]",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    assert not _imessage_state_file(tmp_path).exists()


# ------------------------------------------------------------------
# /test endpoint
# ------------------------------------------------------------------


def _seed_imessage_config(
    tmp_path: Path, contact: str = "alice@example.com"
) -> None:
    state_file = _imessage_state_file(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"contact": contact}), encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_test_endpoint_on_non_darwin_returns_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_imessage_config(tmp_path)
    # Both the endpoint and the bridge consult different sources for
    # platform detection — the endpoint reads sys.platform live, while
    # the bridge reads its own IS_MACOS. Patch both so the test is
    # unambiguous even if the test host happens to be a Mac.
    monkeypatch.setattr("communication.server.sys.platform", "linux")
    monkeypatch.setattr(imessage, "IS_MACOS", False)
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/imessage/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert isinstance(body["error"], str) and body["error"]


@pytest.mark.asyncio
async def test_test_endpoint_400_when_not_configured(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/imessage/test")
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "not configured" in body["error"]


@pytest.mark.asyncio
async def test_test_endpoint_on_darwin_invokes_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_imessage_config(tmp_path, contact="bob@example.com")
    monkeypatch.setattr("communication.server.sys.platform", "darwin")
    monkeypatch.setattr(imessage, "IS_MACOS", True)

    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        captured["cmd"] = cmd
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/imessage/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert "bob@example.com" in captured["cmd"][2]


# ------------------------------------------------------------------
# /status endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_unsupported_on_non_darwin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No config yet — status should still report the platform so the UI
    # can surface the right banner even before the user saves anything.
    monkeypatch.setattr("communication.server.sys.platform", "linux")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/imessage/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unsupported"
    assert body["contact"] is None
    assert body["platform"] == "linux"


@pytest.mark.asyncio
async def test_status_unsupported_overrides_saved_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Per spec: unsupported wins even if a config is saved. Sending
    # wouldn't work anyway, so we don't pretend it's "connected".
    _seed_imessage_config(tmp_path, contact="alice@example.com")
    monkeypatch.setattr("communication.server.sys.platform", "linux")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/imessage/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unsupported"
    # contact still surfaced so the UI can show the prepped value.
    assert body["contact"] == "alice@example.com"
    assert body["platform"] == "linux"


@pytest.mark.asyncio
async def test_status_not_connected_on_darwin_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("communication.server.sys.platform", "darwin")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/imessage/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not-connected"
    assert body["contact"] is None
    assert body["platform"] == "darwin"


@pytest.mark.asyncio
async def test_status_connected_on_darwin_with_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_imessage_config(tmp_path, contact="alice@example.com")
    monkeypatch.setattr("communication.server.sys.platform", "darwin")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/imessage/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert body["contact"] == "alice@example.com"
    assert body["platform"] == "darwin"
