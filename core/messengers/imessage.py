"""Outbound-only iMessage bridge (macOS).

Sending iMessage from Python on macOS is easiest through AppleScript's
``tell application "Messages"`` surface — the same API Apple exposes for
automation/Shortcuts. We shell out via ``osascript -e <script>`` rather
than talking to the SQLite chat.db or the private IMCore framework: the
former needs Full Disk Access; the latter is private and version-drifty.

Inbound (reading incoming iMessages) is deliberately out-of-scope for
this PR. It would need FDA on chat.db plus a polling/watch loop, and
Apple ships no public event-push hook. Shipping outbound first unlocks
the "notify my phone when the orchestrator needs me" use case without
the FDA-permissions rabbit hole.

Cross-platform note: this module imports cleanly on Linux/Windows so
tests (and server configure endpoints) don't blow up; any ``notify``
attempt there just logs + returns False. The intent is that an operator
can prep a config on a dev Linux box and sync it to their Mac where the
bridge actually runs.
"""
from __future__ import annotations

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

# Captured at import time so tests can monkeypatch by overriding this
# module attribute (``imessage.IS_MACOS = True``) without having to poke
# at ``sys.platform`` itself. The latter is read-only in spirit —
# setattr-ing it works but leaks across tests unless carefully reset.
IS_MACOS: bool = sys.platform == "darwin"

# 5 seconds matches the webhook/telegram probe timeouts. osascript's
# own startup is <200ms on a cold Mac; 5s is plenty unless Messages.app
# is stalled waiting on iCloud sync, in which case we'd rather fail fast
# and let the operator retry than block the event loop.
_OSASCRIPT_TIMEOUT = 5.0


def _escape_for_applescript(text: str) -> str:
    """Escape backslashes and double-quotes for AppleScript string literals.

    AppleScript string literals use ``"..."`` with backslash-escapes — so
    ``\\`` becomes ``\\\\`` and ``"`` becomes ``\\"``. Order matters:
    backslashes first, quotes second, otherwise the quote-escape's own
    backslash would get doubled by the first pass.

    Newlines and control characters are left as-is — AppleScript handles
    literal newlines inside a string, and ``osascript -e`` receives the
    whole script as a single argv entry so shell quoting isn't a concern.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


class IMessageBridge:
    """Outbound iMessage notifier via AppleScript.

    Stateless — construct with a contact (email or phone number used as
    the iMessage recipient), call ``notify`` / ``test``. There is no
    background connection; each ``notify`` spawns a fresh ``osascript``
    subprocess.

    On non-Darwin hosts the constructor still succeeds (so the server
    configure endpoint can persist a config prepared for later sync to
    a Mac), but ``notify`` short-circuits with a warning+False.
    """

    def __init__(self, contact: str) -> None:
        if not isinstance(contact, str) or not contact.strip():
            raise ValueError("contact must be a non-empty string")
        # Hard cap on contact length — a real phone/email is well under
        # 100 chars; anything longer is almost certainly user error or
        # an attempt to smuggle AppleScript into the buddy identifier.
        if len(contact) > 200:
            raise ValueError("contact too long (max 200 chars)")
        self._contact = contact.strip()

    @property
    def contact(self) -> str:
        return self._contact

    async def notify(self, event: str, agent: str, text: str) -> bool:
        """Send a single iMessage via ``osascript``.

        Returns True on ``returncode == 0``. Swallows all exceptions —
        osascript not found, timeout, encoding errors, Messages.app
        refused — and returns False so the caller can render a single
        red/green signal without a try/except dance.

        The body format ``[{event}] {agent}: {text}`` matches the
        webhook template's default shape so message-log consumers see
        a consistent prefix across channels.
        """
        if not IS_MACOS:
            # Log once per call so operators who misconfigured on the
            # wrong OS can trace why nothing delivered. We don't raise —
            # a no-op is friendlier to higher-level notify fan-outs.
            log.warning(
                "iMessage notify called on non-darwin platform=%s; skipping",
                sys.platform,
            )
            return False
        body = f"[{event}] {agent}: {text}"
        escaped_body = _escape_for_applescript(body)
        escaped_contact = _escape_for_applescript(self._contact)
        # ``service 1`` addresses the first enabled iMessage account in
        # Messages.app's preferences — usually the user's Apple ID. A
        # more robust path would enumerate ``services whose service type
        # is iMessage``, but that adds AppleScript complexity for a corner
        # case (multiple iCloud accounts) that almost never applies to a
        # single-user Mac.
        script = (
            f'tell application "Messages" to send "{escaped_body}" '
            f'to buddy "{escaped_contact}" of service 1'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                timeout=_OSASCRIPT_TIMEOUT,
                capture_output=True,
            )
        except FileNotFoundError:
            # osascript ships with every macOS install, so this really
            # should not happen — but if the user is on a stripped-down
            # image or inside a restricted container, fail soft.
            log.warning("osascript not found on PATH")
            return False
        except subprocess.TimeoutExpired:
            log.warning("osascript timed out after %.1fs", _OSASCRIPT_TIMEOUT)
            return False
        except Exception:
            log.warning("osascript invocation failed", exc_info=True)
            return False
        if result.returncode != 0:
            # stderr often contains Messages.app's own reason — "Can't
            # get buddy ..." when the contact isn't in the user's iMessage
            # address book, etc. Log the first 200 chars for diagnosis;
            # don't surface to the UI (might contain contact identifiers).
            stderr = (result.stderr or b"").decode("utf-8", errors="replace")
            log.warning(
                "osascript returncode=%d stderr=%s",
                result.returncode,
                stderr[:200],
            )
            return False
        return True

    async def test(self) -> dict:
        """Send a canned test notification; return a shaped dict.

        Response shape: ``{ok: bool, platform: str, error: str | None}``.
        ``platform`` is ``sys.platform`` so the UI can distinguish
        "not on macOS" from "on macOS but delivery failed" without a
        second round-trip.
        """
        platform = sys.platform
        if not IS_MACOS:
            return {
                "ok": False,
                "platform": platform,
                "error": "iMessage is only supported on macOS",
            }
        try:
            ok = await self.notify("test", "groft", "Groft iMessage test")
        except Exception as exc:
            log.warning("iMessage test: unexpected error", exc_info=True)
            return {
                "ok": False,
                "platform": platform,
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        return {
            "ok": ok,
            "platform": platform,
            "error": None if ok else "osascript send failed (see server log)",
        }


__all__ = ["IMessageBridge", "IS_MACOS"]
