#!/usr/bin/env python3
"""Rule #7 (outbound guard): require explicit confirm before sending
data off-host.

PreToolUse hook on Bash: curl/wget/scp/sftp/ssh/rsync/nc/python-urlopen
calls are paused with a deny-until-confirmed message. Adding
`# groft-user-confirmed` to the command after the user says OK lets it
through (same override mechanism as Rule #5).

Localhost targets (`http://localhost`, `127.0.0.1`, …) are exempt —
calling a dev server on the host is not outbound.

Also flags `git push` to a URL-based remote (as opposed to a named
remote like `origin`). Named remotes are trusted because the user
configured them already — they are not opaque destinations.
"""
from __future__ import annotations

import re
import sys

from _common import read_event, write_response
from core.constitution import deny_response
from core.secrets_detection import detect_outbound_command


_OVERRIDE_MARKER = "# groft-user-confirmed"

_GIT_PUSH_RE = re.compile(r"\bgit\s+push\b\s+([^\s;|&]+)")
_URL_REMOTE_RE = re.compile(r"^(https?://|git@|ssh://|git://|file://)")


def _git_push_to_url(command: str) -> str | None:
    """If command is `git push <url>…`, return the URL, else None."""
    m = _GIT_PUSH_RE.search(command)
    if not m:
        return None
    target = m.group(1)
    if _URL_REMOTE_RE.match(target):
        return target
    return None


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if not command or _OVERRIDE_MARKER in command:
        return 0

    kind = detect_outbound_command(command)
    push_url = _git_push_to_url(command)

    if kind is None and push_url is None:
        return 0

    if push_url is not None:
        summary = f"git push to URL `{push_url}`"
    else:
        summary = f"outbound `{kind}`"

    reason = (
        f"⚠ Rule #7 (outbound guard): command contains {summary}. "
        "Pause and ask the user to confirm that this data leaving the "
        "host is intentional. If confirmed, retry with "
        f"`{_OVERRIDE_MARKER}` appended to the command."
    )
    write_response(deny_response(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
