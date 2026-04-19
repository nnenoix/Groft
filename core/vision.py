"""Vision helpers — screen capture + Anthropic multimodal Q&A.

Phase 7 experiment: give sub-agents a way to "see" either the user's
screen or another agent's tmux pane. The screenshot is taken in
Python (``mss``) rather than routed through Tauri so everything lives
on one process boundary — MCP exposure stays trivial.

Three public coroutines:

- :func:`capture_screen` — PNG bytes for a given monitor index via mss,
  wrapped in a thread because mss is a synchronous library.
- :func:`ask_about_image` — send image + question to Anthropic's
  multimodal messages API, return the assistant's text answer.
- :func:`ask_about_text` — text-only variant; used by ``see_agent_pane``
  where the pane content is already textual via tmux capture, and the
  multimodal detour would just burn image tokens for no gain.

All three raise :class:`VisionError` on failure so callers can
distinguish expected vision problems (no API key, 5xx, malformed
response, display missing) from unrelated exceptions.

Model choice — :data:`VISION_MODEL` is pinned to ``claude-sonnet-4-6``
because Haiku's multimodal support hasn't been verified for this
workflow; using Sonnet here is a conscious cost tradeoff the caller
accepts every time they invoke a vision tool. The MCP tool descriptions
(see :mod:`communication.mcp_server`) warn the operator about the ~5-10x
price bump relative to a plain Haiku text call.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Pinned to Sonnet: Haiku's vision support isn't verified for this flow,
# and silently falling back would make cost estimates for the operator
# unreliable. Keep this constant — callers pattern-match on it in tests.
VISION_MODEL = "claude-sonnet-4-6"

# Anthropic messages API — hardcoded endpoint + version. We call the HTTP
# API directly instead of pulling in the official ``anthropic`` SDK; the
# SDK is heavy (tokenizer, streaming glue, httpx pinning) and we only
# need one POST shape. Version pin matches what the Anthropic docs
# recommend for the messages API as of 2026.
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

# 30s is long enough for a single Sonnet vision round-trip on a slow
# network, but short enough that a stalled request doesn't wedge the
# caller's event loop for minutes.
_TIMEOUT = 30.0

# max_tokens for the response. 1024 comfortably fits a paragraph-or-two
# answer for "what do you see here" without letting the model ramble
# through the entire token budget.
_MAX_TOKENS = 1024


class VisionError(Exception):
    """Raised on any vision-related failure.

    Wraps: missing ANTHROPIC_API_KEY, non-2xx responses, malformed
    response bodies, and underlying httpx transport errors. Callers
    catch this specifically so they can surface a shaped 500 to the
    UI / MCP client instead of leaking a raw httpx exception.
    """


# Prompts kept as module-level constants so tests can assert the exact
# string the model sees — we want "agent_label" and the pane text to
# land inside the prompt at predictable positions, and accidentally
# re-wording these prompts is exactly the kind of silent behaviour
# change worth flagging in review.
_IMAGE_PROMPT_TEMPLATE = (
    "You are looking at a screenshot. Answer the question below based only on\n"
    "what you can see. If you can't tell from the image, say so.\n"
    "\n"
    "Question: {question}"
)

_TEXT_PROMPT_TEMPLATE = (
    "You are reading the terminal output of agent {agent_label}.\n"
    "Answer the question based on this output.\n"
    "\n"
    "--- OUTPUT ---\n"
    "{text}\n"
    "--- END OUTPUT ---\n"
    "\n"
    "Question: {question}"
)


def _require_api_key() -> str:
    """Fetch ANTHROPIC_API_KEY or raise VisionError.

    Kept private because the only legitimate caller is inside this
    module; callers shouldn't reach past our abstraction to pluck the
    env var themselves.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise VisionError("ANTHROPIC_API_KEY not set in environment")
    return key


def _capture_screen_sync(monitor_idx: int) -> bytes:
    """Synchronous mss capture. Meant to be run in a thread.

    mss is a C-ish synchronous library — calling it in an executor keeps
    the event loop responsive. monitor_idx is 1-based in mss (index 0 is
    the "all monitors" virtual screen); we expose a 0-based API where
    0 = primary display, matching the operator's mental model.

    Raises VisionError on import failure (mss not installed) or mss
    itself raising (no display available, invalid monitor index).
    """
    try:
        import mss  # lazy: tests on CI skip the capture path entirely
        import mss.tools
    except ImportError as exc:
        raise VisionError(f"mss not installed: {exc}") from exc
    try:
        with mss.mss() as sct:
            # mss.monitors[0] is the virtual "span of all monitors"; real
            # displays start at index 1. Our public API calls the primary
            # display 0, so we offset by one. Out-of-range indices raise
            # IndexError → wrap into VisionError for a consistent type.
            monitors = sct.monitors
            real_idx = monitor_idx + 1
            if real_idx < 1 or real_idx >= len(monitors):
                raise VisionError(
                    f"monitor_idx={monitor_idx} out of range "
                    f"(available: 0..{len(monitors) - 2})"
                )
            shot = sct.grab(monitors[real_idx])
            return mss.tools.to_png(shot.rgb, shot.size)
    except VisionError:
        raise
    except Exception as exc:
        # Most commonly: "XOpenDisplay failed" on headless Linux, or
        # "CGDisplayCreateImage failed" on macOS without screen-recording
        # permission. Propagate as VisionError so the caller's error
        # handling is uniform.
        raise VisionError(f"screen capture failed: {exc}") from exc


async def capture_screen(monitor_idx: int = 0) -> bytes:
    """Return PNG bytes for the given monitor.

    ``monitor_idx=0`` is the primary display. mss is synchronous, so we
    offload the actual grab to the default executor to avoid blocking
    the caller's event loop for the 50-200 ms a screenshot takes on a
    typical machine.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _capture_screen_sync, monitor_idx)


def _extract_text(response_body: Any) -> str:
    """Pull ``content[0].text`` out of an Anthropic messages response.

    Isolated so the "malformed response" failure mode has one clearly
    attributed raise site — easier to assert in tests and to grep for
    when Anthropic eventually changes the schema.
    """
    if not isinstance(response_body, dict):
        raise VisionError("Anthropic response is not a JSON object")
    content = response_body.get("content")
    if not isinstance(content, list) or not content:
        raise VisionError("Anthropic response missing content array")
    first = content[0]
    if not isinstance(first, dict):
        raise VisionError("Anthropic response content[0] is not an object")
    text = first.get("text")
    if not isinstance(text, str):
        raise VisionError("Anthropic response content[0].text missing")
    return text


async def _post_messages(payload: dict[str, Any]) -> dict[str, Any]:
    """POST to Anthropic messages API and return the decoded JSON.

    Shared hot-path for both ``ask_about_image`` and ``ask_about_text``.
    Any non-2xx is surfaced as VisionError with the response body so
    operators can diagnose (bad key → 401, overloaded → 529, etc.)
    without digging through logs.
    """
    api_key = _require_api_key()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_API_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        # Connection refused, TLS failure, timeout — collapse to a
        # single error type so the caller's catch block is trivial.
        raise VisionError(f"Anthropic request failed: {exc}") from exc
    if resp.status_code != 200:
        # Response body is bounded by Anthropic's own reply size and is
        # safe to surface to the operator; truncating risks hiding the
        # useful error ("invalid x-api-key").
        raise VisionError(
            f"Anthropic API error {resp.status_code}: {resp.text}"
        )
    try:
        return resp.json()
    except Exception as exc:
        raise VisionError(f"Anthropic response not JSON: {exc}") from exc


async def ask_about_image(png_bytes: bytes, question: str) -> str:
    """Send PNG + question to Anthropic multimodal, return the text.

    Uses the messages API with a mixed content array: one ``image``
    block (base64-encoded PNG) followed by one ``text`` block carrying
    the question. max_tokens capped at 1024 (see module-level constant).
    """
    if not isinstance(png_bytes, (bytes, bytearray)) or not png_bytes:
        raise VisionError("png_bytes must be non-empty bytes")
    if not isinstance(question, str) or not question.strip():
        raise VisionError("question must be a non-empty string")
    encoded = base64.b64encode(bytes(png_bytes)).decode("ascii")
    prompt = _IMAGE_PROMPT_TEMPLATE.format(question=question)
    payload = {
        "model": VISION_MODEL,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    body = await _post_messages(payload)
    return _extract_text(body)


async def ask_about_text(
    text: str, question: str, *, agent_label: str | None = None
) -> str:
    """Text-only variant — cheaper than the multimodal path.

    ``see_agent_pane`` uses this because tmux's capture is already text;
    paying the multimodal price to re-OCR it would be silly. The agent
    label is surfaced inside the prompt so the model knows which agent's
    output it's looking at — improves answers like "which tool did
    backend-dev just call?".
    """
    if not isinstance(text, str):
        raise VisionError("text must be a string")
    if not isinstance(question, str) or not question.strip():
        raise VisionError("question must be a non-empty string")
    label = agent_label if (isinstance(agent_label, str) and agent_label) else "unknown"
    prompt = _TEXT_PROMPT_TEMPLATE.format(
        agent_label=label, text=text, question=question
    )
    payload = {
        "model": VISION_MODEL,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    body = await _post_messages(payload)
    return _extract_text(body)


__all__ = [
    "VisionError",
    "VISION_MODEL",
    "ask_about_image",
    "ask_about_text",
    "capture_screen",
]
