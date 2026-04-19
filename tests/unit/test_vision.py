"""Tests for core.vision + MCP vision tool wrappers.

Coverage strategy:

- ``capture_screen`` — we don't actually invoke mss on CI (no display,
  and Linux Wayland/X11 quirks would turn this into a flake factory).
  The test is explicitly skipped there; if you run it locally with a
  display, it does a single grab and asserts PNG magic bytes.
- ``ask_about_image`` / ``ask_about_text`` — full mocking of
  ``httpx.AsyncClient.post`` via MockTransport. We verify:
    * URL, headers (inc. ``x-api-key``), model constant, base64 payload
      present (for image path).
    * Successful parse of ``content[0].text``.
    * VisionError on 401, 500, and malformed bodies.
- MCP wrappers — monkeypatch both ``capture_screen``/``ask_about_image``
  and ``_capture_pane``/``ask_about_text`` with recorders, invoke the
  wrapper and assert it forwarded the right arguments.

No real network calls. No real subprocess. No real mss import on CI.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import vision  # noqa: E402
from core.vision import (  # noqa: E402
    VISION_MODEL,
    VisionError,
    ask_about_image,
    ask_about_text,
    capture_screen,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: "callable[[httpx.Request], httpx.Response]",
    recorder: list[httpx.Request] | None = None,
) -> None:
    """Patch httpx.AsyncClient so every instance uses a MockTransport.

    Same hook pattern as test_telegram_bridge.py uses for getMe — lets
    the production code call ``httpx.AsyncClient(timeout=...)`` unchanged
    and we intercept at the transport layer.
    """
    original_init = httpx.AsyncClient.__init__

    def _wrapped_handler(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped_handler)

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def _anthropic_ok(text: str = "I see a terminal.") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_xyz",
            "type": "message",
            "role": "assistant",
            "model": VISION_MODEL,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 42, "output_tokens": 7},
        },
    )


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a fake API key by default.

    The few tests that need to assert the "missing key" error path clear
    it explicitly via ``monkeypatch.delenv``.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-abc")


# ------------------------------------------------------------------
# capture_screen — skipped on CI / headless Linux
# ------------------------------------------------------------------


def _mss_available() -> bool:
    try:
        import mss  # noqa: F401
    except Exception:
        return False
    return True


@pytest.mark.skipif(
    "CI" in os.environ
    or (sys.platform == "linux" and not os.environ.get("DISPLAY"))
    or not _mss_available(),
    reason=(
        "capture_screen needs a real display AND mss installed; skipped on CI, "
        "headless WSL/Linux, and environments where mss isn't available."
    ),
)
async def test_capture_screen_returns_png_bytes() -> None:
    png = await capture_screen(0)
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------------
# ask_about_image — happy path + failure modes
# ------------------------------------------------------------------


async def test_ask_about_image_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    _install_mock_transport(
        monkeypatch, lambda req: _anthropic_ok("I see a cat."), captured
    )

    png = b"\x89PNG\r\n\x1a\nfakecontents"
    answer = await ask_about_image(png, "What do you see?")
    assert answer == "I see a cat."

    assert len(captured) == 1
    req = captured[0]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "test-key-abc"
    assert req.headers["anthropic-version"] == "2023-06-01"
    assert req.headers["content-type"].startswith("application/json")

    body = json.loads(req.content)
    assert body["model"] == VISION_MODEL
    assert body["max_tokens"] == 1024
    content = body["messages"][0]["content"]
    # Order matters: image first, then the question text — asserting the
    # shape directly catches an accidental swap (which would still "work"
    # but silently change the model's behaviour).
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"] == base64.b64encode(png).decode("ascii")
    assert content[1]["type"] == "text"
    assert "What do you see?" in content[1]["text"]
    # Prompt template must stay stable — asserting the full lead-in
    # protects against accidental rewording in review.
    assert "You are looking at a screenshot" in content[1]["text"]


async def test_ask_about_image_401_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(
            401, json={"type": "error", "error": {"message": "invalid key"}}
        ),
    )
    with pytest.raises(VisionError) as excinfo:
        await ask_about_image(b"\x89PNGxxx", "hi")
    assert "401" in str(excinfo.value)


async def test_ask_about_image_500_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(500, text="internal server error"),
    )
    with pytest.raises(VisionError) as excinfo:
        await ask_about_image(b"\x89PNGxxx", "hi")
    assert "500" in str(excinfo.value)


async def test_ask_about_image_malformed_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 200 OK but no ``content`` array — must surface as VisionError, not
    # KeyError / IndexError, so callers can catch just the one type.
    _install_mock_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json={"id": "msg_x", "role": "assistant"}),
    )
    with pytest.raises(VisionError):
        await ask_about_image(b"\x89PNGxxx", "hi")


async def test_ask_about_image_missing_api_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(VisionError) as excinfo:
        await ask_about_image(b"\x89PNGxxx", "hi")
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


async def test_ask_about_image_rejects_empty_bytes() -> None:
    with pytest.raises(VisionError):
        await ask_about_image(b"", "what")


async def test_ask_about_image_rejects_empty_question() -> None:
    with pytest.raises(VisionError):
        await ask_about_image(b"\x89PNG", "  ")


# ------------------------------------------------------------------
# ask_about_text — happy path + prompt body
# ------------------------------------------------------------------


async def test_ask_about_text_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []
    _install_mock_transport(
        monkeypatch,
        lambda req: _anthropic_ok("Pane shows a prompt."),
        captured,
    )

    pane = "backend-dev $ npm test\nPASS tests/foo.spec.ts"
    answer = await ask_about_text(
        pane, "What did the last command do?", agent_label="backend-dev"
    )
    assert answer == "Pane shows a prompt."

    req = captured[0]
    body = json.loads(req.content)
    assert body["model"] == VISION_MODEL
    content = body["messages"][0]["content"]
    # Text-only: a single ``text`` block, no ``image`` block.
    assert len(content) == 1
    assert content[0]["type"] == "text"
    text = content[0]["text"]
    assert "agent backend-dev" in text
    assert pane in text
    assert "What did the last command do?" in text


async def test_ask_about_text_defaults_label_to_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []
    _install_mock_transport(monkeypatch, lambda req: _anthropic_ok(), captured)
    await ask_about_text("some pane text", "question?", agent_label=None)
    body = json.loads(captured[0].content)
    text = body["messages"][0]["content"][0]["text"]
    # agent_label=None → the prompt falls back to "unknown" so the model
    # still has a grammatical sentence.
    assert "agent unknown" in text


async def test_ask_about_text_empty_label_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []
    _install_mock_transport(monkeypatch, lambda req: _anthropic_ok(), captured)
    await ask_about_text("pane", "q?", agent_label="")
    text = json.loads(captured[0].content)["messages"][0]["content"][0]["text"]
    assert "agent unknown" in text


async def test_ask_about_text_401_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mock_transport(
        monkeypatch, lambda req: httpx.Response(401, text="nope")
    )
    with pytest.raises(VisionError):
        await ask_about_text("pane", "q?", agent_label="x")


async def test_ask_about_text_rejects_empty_question() -> None:
    with pytest.raises(VisionError):
        await ask_about_text("pane", "", agent_label="x")


# ------------------------------------------------------------------
# MCP wrappers — assert forwarding contract
# ------------------------------------------------------------------


async def test_see_screen_forwards_to_capture_and_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reach through the already-imported module so monkeypatches hit the
    # same names the tool closure looks up.
    from communication import mcp_server

    calls: dict[str, Any] = {}

    async def fake_capture_screen(monitor_idx: int) -> bytes:
        calls["capture"] = monitor_idx
        return b"\x89PNG-fake"

    async def fake_ask_about_image(png: bytes, question: str) -> str:
        calls["ask"] = (png, question)
        return "fake answer"

    monkeypatch.setattr(mcp_server, "capture_screen", fake_capture_screen)
    monkeypatch.setattr(mcp_server, "ask_about_image", fake_ask_about_image)

    # FastMCP tool objects expose the underlying function differently
    # across versions; the plain name resolves in the module namespace
    # via the tool registry, so call the raw callable the decorator
    # wrapped.
    result = await mcp_server.see_screen(2, "which window is focused?")
    assert result == "fake answer"
    assert calls["capture"] == 2
    assert calls["ask"] == (b"\x89PNG-fake", "which window is focused?")


async def test_see_screen_wraps_vision_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from communication import mcp_server

    async def fake_capture_screen(monitor_idx: int) -> bytes:
        raise VisionError("no display")

    monkeypatch.setattr(mcp_server, "capture_screen", fake_capture_screen)

    result = await mcp_server.see_screen(0, "?")
    # MCP tools return strings, not raise — the wrapper collapses the
    # error to a human-readable marker the agent can act on.
    assert result.startswith("Vision error:")
    assert "no display" in result


async def test_see_agent_pane_forwards_to_capture_and_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from communication import mcp_server

    calls: dict[str, Any] = {}

    async def fake_capture_pane(agent_name: str) -> str:
        calls["capture"] = agent_name
        return "(pretend pane contents)"

    async def fake_ask_about_text(
        text: str, question: str, *, agent_label: str | None = None
    ) -> str:
        calls["ask"] = (text, question, agent_label)
        return "fake text answer"

    monkeypatch.setattr(mcp_server, "_capture_pane", fake_capture_pane)
    monkeypatch.setattr(mcp_server, "ask_about_text", fake_ask_about_text)

    result = await mcp_server.see_agent_pane(
        "backend-dev", "what tool did they just call?"
    )
    assert result == "fake text answer"
    assert calls["capture"] == "backend-dev"
    assert calls["ask"] == (
        "(pretend pane contents)",
        "what tool did they just call?",
        "backend-dev",
    )


async def test_see_agent_pane_wraps_vision_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from communication import mcp_server

    async def fake_capture_pane(agent_name: str) -> str:
        raise VisionError("tmux session missing")

    monkeypatch.setattr(mcp_server, "_capture_pane", fake_capture_pane)

    result = await mcp_server.see_agent_pane("ghost", "?")
    assert result.startswith("Vision error:")
    assert "tmux session missing" in result


# ------------------------------------------------------------------
# Internal helpers — light regression guard on _extract_text
# ------------------------------------------------------------------


def test_extract_text_rejects_non_dict() -> None:
    with pytest.raises(VisionError):
        vision._extract_text([])


def test_extract_text_rejects_empty_content() -> None:
    with pytest.raises(VisionError):
        vision._extract_text({"content": []})


def test_extract_text_rejects_non_string_text() -> None:
    with pytest.raises(VisionError):
        vision._extract_text({"content": [{"type": "text", "text": 42}]})
