"""WebhookBridge + REST endpoint coverage.

Covers:
- ``WebhookBridge`` constructor: happy-path, template-not-JSON rejection,
  template-without-tokens rejection. The ctor probes with sentinel
  substitutions before accepting; these tests pin that contract.
- ``WebhookBridge.notify``: httpx.MockTransport injection so we never
  touch the network; assert method, URL, header, and body shape match
  the rendered template byte-for-byte.
- ``POST /messenger/webhook/configure``: valid body writes state file,
  non-http URL → 400, bad template → 400.
- ``POST /messenger/webhook/test``: mock responses map 2xx → ok:true,
  5xx → ok:false, connection error → ok:false with error string.
- ``GET /messenger/webhook/status``: reflects the on-disk state file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from communication.server import CommunicationServer  # noqa: E402
from core.messengers.webhook import WebhookBridge  # noqa: E402


# ------------------------------------------------------------------
# shared helpers
# ------------------------------------------------------------------


GOOD_TEMPLATE = (
    '{"event":"{event}","from":"{agent}","content":"{text}"}'
)


def _build_server() -> CommunicationServer:
    # Isolated in-memory DB + ephemeral ports — tests never bind for real.
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


def _webhook_state_file(tmp_path: Path) -> Path:
    return tmp_path / ".claudeorch" / "messenger-webhook.json"


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route CLAUDEORCH_USER_DATA to tmp_path; reset path caches.

    Identical pattern to test_telegram_bridge.py — the two files could
    share a fixture module, but keeping it local keeps the test file
    self-contained for reviewers.
    """
    import core.paths as paths

    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
    yield
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: "httpx._types.SyncByteStream | Any",
) -> list[httpx.Request]:
    """Wire up httpx.MockTransport so any fresh AsyncClient uses it.

    Returns a list the handler appends to (captured via closure) so
    tests can assert on the requests that flew. Matches the pattern
    used by test_telegram_bridge.py's configure tests.
    """
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    transport = httpx.MockTransport(_handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", transport)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
    return captured


# ------------------------------------------------------------------
# WebhookBridge constructor
# ------------------------------------------------------------------


def test_bridge_accepts_good_template() -> None:
    b = WebhookBridge(
        url="https://example.com/hook", secret="s3cret", template=GOOD_TEMPLATE
    )
    assert b.url == "https://example.com/hook"


def test_bridge_accepts_template_with_only_one_token() -> None:
    # Spec says "at least one of event/agent/text" is required. A template
    # with just {text} is enough — pin this so a future over-strict change
    # doesn't accidentally require all three.
    WebhookBridge(
        url="https://x.invalid/hook",
        secret="",  # empty secret is legal; the header just goes out empty
        template='{"msg":"{text}"}',
    )


def test_bridge_rejects_template_with_no_tokens() -> None:
    # Static body = pointless + almost certainly user error.
    with pytest.raises(ValueError) as exc:
        WebhookBridge(
            url="https://x.invalid/hook",
            secret="s",
            template='{"static":"no tokens here"}',
        )
    # Error should name the required tokens so the operator knows how to fix it.
    msg = str(exc.value)
    assert "{event}" in msg or "{agent}" in msg or "{text}" in msg


def test_bridge_rejects_template_invalid_json_after_substitution() -> None:
    # Missing closing brace — won't parse even with sentinel substitutions.
    with pytest.raises(ValueError) as exc:
        WebhookBridge(
            url="https://x.invalid/hook",
            secret="s",
            template='{"text":"{text}"',
        )
    assert "JSON" in str(exc.value) or "json" in str(exc.value)


def test_bridge_rejects_empty_url() -> None:
    with pytest.raises(ValueError):
        WebhookBridge(url="", secret="s", template=GOOD_TEMPLATE)


def test_bridge_rejects_empty_template() -> None:
    with pytest.raises(ValueError):
        WebhookBridge(url="https://x.invalid", secret="s", template="")


def test_bridge_rendering_does_not_crash_on_curly_braces_in_text() -> None:
    # Regression guard: we use str.replace (not format()), so literal
    # braces in user-supplied `text` must pass through untouched.
    b = WebhookBridge(
        url="https://x.invalid", secret="s", template=GOOD_TEMPLATE
    )
    rendered = b._render_for_test(
        event="msg", agent="opus", text="hello {world}"
    )
    # Still valid JSON despite the braces inside the content.
    parsed = json.loads(rendered)
    assert parsed["content"] == "hello {world}"


# ------------------------------------------------------------------
# WebhookBridge.notify
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_posts_rendered_body_with_secret_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Capture the outgoing request and assert method/URL/headers/body.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://example.com/hook"
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["X-Webhook-Secret"] == "topsecret"
        parsed = json.loads(request.content.decode("utf-8"))
        assert parsed == {
            "event": "deploy",
            "from": "backend-dev",
            "content": "shipped",
        }
        return httpx.Response(200, json={"delivered": True})

    _install_mock_transport(monkeypatch, handler)
    b = WebhookBridge(
        url="https://example.com/hook",
        secret="topsecret",
        template=GOOD_TEMPLATE,
    )
    resp = await b.notify("deploy", "backend-dev", "shipped")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_test_method_returns_true_on_2xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Also sanity-check the canned payload fields.
        parsed = json.loads(request.content.decode("utf-8"))
        assert parsed["event"] == "test"
        assert parsed["from"] == "groft"
        return httpx.Response(201)

    _install_mock_transport(monkeypatch, handler)
    b = WebhookBridge("https://x.invalid/hk", "s", GOOD_TEMPLATE)
    assert await b.test() is True


@pytest.mark.asyncio
async def test_test_method_returns_false_on_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    _install_mock_transport(monkeypatch, handler)
    b = WebhookBridge("https://x.invalid/hk", "s", GOOD_TEMPLATE)
    assert await b.test() is False


@pytest.mark.asyncio
async def test_test_method_swallows_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    _install_mock_transport(monkeypatch, handler)
    b = WebhookBridge("https://x.invalid/hk", "s", GOOD_TEMPLATE)
    # Must return False, not raise — test() is a best-effort probe.
    assert await b.test() is False


# ------------------------------------------------------------------
# /configure endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_success_writes_state(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/webhook/configure",
            json={
                "url": "https://example.com/hook",
                "secret": "s3cret",
                "template": GOOD_TEMPLATE,
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    state_file = _webhook_state_file(tmp_path)
    assert state_file.exists()
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted == {
        "url": "https://example.com/hook",
        "secret": "s3cret",
        "template": GOOD_TEMPLATE,
    }


@pytest.mark.asyncio
async def test_configure_rejects_non_http_url(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/webhook/configure",
            json={
                "url": "file:///etc/passwd",
                "secret": "s",
                "template": GOOD_TEMPLATE,
            },
        )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "http" in body["error"].lower()
    # No state written on reject.
    assert not _webhook_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_url_without_host(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/webhook/configure",
            json={
                "url": "https://",  # scheme but no netloc
                "secret": "s",
                "template": GOOD_TEMPLATE,
            },
        )
    assert resp.status_code == 400
    assert not _webhook_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_bad_template(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post(
            "/messenger/webhook/configure",
            json={
                "url": "https://example.com/hook",
                "secret": "s",
                # Missing closing brace — ctor rejects, 400 propagates.
                "template": '{"content":"{text}"',
            },
        )
    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert not _webhook_state_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_configure_rejects_missing_fields(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/webhook/configure", json={})
    assert resp.status_code == 400


# ------------------------------------------------------------------
# /test endpoint
# ------------------------------------------------------------------


def _seed_webhook_config(tmp_path: Path, url: str = "https://example.com/hook") -> None:
    """Write a minimal valid config file so /test has something to read."""
    state_file = _webhook_state_file(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {"url": url, "secret": "s3cret", "template": GOOD_TEMPLATE}
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_test_endpoint_returns_ok_on_2xx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_webhook_config(tmp_path)
    srv = _build_server()

    def handler(request: httpx.Request) -> httpx.Response:
        # Same header + payload shape /notify uses.
        assert request.headers["X-Webhook-Secret"] == "s3cret"
        return httpx.Response(200, json={"ok": True})

    _install_mock_transport(monkeypatch, handler)

    async with _client(srv) as c:
        resp = await c.post("/messenger/webhook/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True, "status": 200, "error": None}


@pytest.mark.asyncio
async def test_test_endpoint_reports_false_on_5xx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_webhook_config(tmp_path)
    srv = _build_server()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _install_mock_transport(monkeypatch, handler)
    async with _client(srv) as c:
        resp = await c.post("/messenger/webhook/test")
    assert resp.status_code == 200  # endpoint itself succeeded
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == 503
    assert body["error"] == "HTTP 503"


@pytest.mark.asyncio
async def test_test_endpoint_reports_network_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_webhook_config(tmp_path)
    srv = _build_server()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failed")

    _install_mock_transport(monkeypatch, handler)
    async with _client(srv) as c:
        resp = await c.post("/messenger/webhook/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] is None
    assert isinstance(body["error"], str) and body["error"]
    assert "ConnectError" in body["error"] or "dns" in body["error"]


@pytest.mark.asyncio
async def test_test_endpoint_400_when_not_configured(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.post("/messenger/webhook/test")
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "not configured" in body["error"]


# ------------------------------------------------------------------
# /status endpoint
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_not_connected_when_no_file(tmp_path: Path) -> None:
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/webhook/status")
    assert resp.status_code == 200
    assert resp.json() == {"status": "not-connected", "url": None}


@pytest.mark.asyncio
async def test_status_connected_when_file_present(tmp_path: Path) -> None:
    _seed_webhook_config(tmp_path, url="https://ex.invalid/hk")
    srv = _build_server()
    async with _client(srv) as c:
        resp = await c.get("/messenger/webhook/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "connected",
        "url": "https://ex.invalid/hk",
    }
