"""Generic outbound webhook bridge.

Turns a (URL, secret, template) tuple into a minimal notifier the
orchestrator can point at any HTTP endpoint — Zapier hooks, private
monitoring dashboards, a dev's self-hosted ingest, whatever. Outbound
only: inbound webhooks need auth/routing, and are a separate feature.

Template substitution is deliberately dumb ``str.replace`` on three
tokens — ``{event}``, ``{agent}``, ``{text}``. We do NOT use
``str.format``: user-supplied ``text`` frequently contains literal
``{`` / ``}`` (JSON snippets, code fragments), and format() would raise
``KeyError`` or mangle braces. Validation is "does the post-substitution
string parse as JSON?" — if yes, we're safe to POST with application/json.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Sentinel values used to probe the template at construction time. They
# must be JSON-safe strings (no embedded quotes, no control chars) so
# that a template like `"{\"text\":\"{text}\"}"` still parses after
# substitution. Distinct from any realistic user input so we don't
# accidentally collide on the probe path.
_PROBE_EVENT = "__probe_event__"
_PROBE_AGENT = "__probe_agent__"
_PROBE_TEXT = "__probe_text__"

# At least one of these tokens MUST appear in the template — otherwise
# every notification would produce the same byte-for-byte body and the
# recipient has no way to distinguish a test ping from a real event.
_REQUIRED_TOKENS: tuple[str, ...] = ("{event}", "{agent}", "{text}")


def _render(template: str, event: str, agent: str, text: str) -> str:
    """Substitute the three tokens into ``template`` via plain replace."""
    return (
        template
        .replace("{event}", event)
        .replace("{agent}", agent)
        .replace("{text}", text)
    )


class WebhookBridge:
    """Outbound-only webhook notifier.

    Stateless apart from the three config values — construct, call
    ``notify`` / ``test``, let it be GC'd. No background tasks, no
    persistent client; each ``notify`` opens a fresh ``httpx.AsyncClient``
    with a 10-second timeout.
    """

    # Timeout chosen long enough for slow-ish third-party endpoints
    # (Zapier ~2-5s cold) but short enough that the caller's loop
    # doesn't stall if the endpoint black-holes the request.
    DEFAULT_TIMEOUT = 10.0

    def __init__(self, url: str, secret: str, template: str) -> None:
        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")
        if not isinstance(secret, str):
            raise ValueError("secret must be a string")
        if not isinstance(template, str) or not template:
            raise ValueError("template must be a non-empty string")
        # Reject templates with none of the substitution tokens — a
        # static body is pointless and almost certainly a user mistake.
        if not any(tok in template for tok in _REQUIRED_TOKENS):
            raise ValueError(
                "template must contain at least one of {event}, {agent}, {text}"
            )
        # Probe the template with sentinel values. If the post-substitution
        # string doesn't parse as JSON, the template is broken (missing
        # comma, unbalanced brace, etc.) — reject now rather than on the
        # first real ``notify`` call in production.
        probed = _render(template, _PROBE_EVENT, _PROBE_AGENT, _PROBE_TEXT)
        try:
            json.loads(probed)
        except Exception as exc:
            raise ValueError(
                f"template does not produce valid JSON after substitution: {exc}"
            ) from exc
        self._url = url
        self._secret = secret
        self._template = template

    @property
    def url(self) -> str:
        return self._url

    async def notify(self, event: str, agent: str, text: str) -> httpx.Response:
        """POST the rendered template to the configured URL.

        Returns the raw ``httpx.Response`` so callers can decide how to
        react to non-2xx responses. Network errors propagate — ``test()``
        catches them; other callers should wrap per their own policy.
        """
        body = _render(self._template, event or "", agent or "", text or "")
        # We JSON-validated the template at construction, so ``body``
        # is already valid JSON. Send the bytes directly via ``content=``
        # so httpx doesn't re-serialize (and potentially re-encode the
        # payload in a way the receiver doesn't expect).
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Secret": self._secret,
        }
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            return await client.post(self._url, content=body, headers=headers)

    async def test(self) -> bool:
        """Send a canned ``test`` notification; return True on 2xx.

        Swallows network errors (returns False) so the UI can render a
        single red/green indicator without a try/except dance. Real
        network failures are logged so operators can diagnose.
        """
        try:
            resp = await self.notify(
                "test", "groft", "Webhook test from Groft"
            )
        except Exception:
            log.warning("webhook test: network error", exc_info=True)
            return False
        return bool(resp.is_success)

    # Debug helper — NOT for logging; use carefully. Mostly exists so
    # tests can assert the rendered body without reimplementing _render.
    def _render_for_test(self, event: str, agent: str, text: str) -> str:
        return _render(self._template, event, agent, text)


__all__ = ["WebhookBridge"]

# Re-exported so the server module can introspect the same constant
# when deciding whether a template is empty vs. invalid.
REQUIRED_TOKENS: tuple[str, ...] = _REQUIRED_TOKENS


def render_template(
    template: str, event: str, agent: str, text: str
) -> str:
    """Public re-export of the dumb str.replace renderer.

    Useful for any non-bridge caller that wants to preview how a
    template will look before constructing the bridge.
    """
    return _render(template, event, agent, text)


# Typed alias for the on-disk config shape. Not enforced at runtime —
# server-side persistence lives in communication/server.py and uses a
# plain dict — but documents the expected keys for reviewers.
ConfigDict = dict[str, Any]
