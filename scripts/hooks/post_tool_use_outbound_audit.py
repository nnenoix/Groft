#!/usr/bin/env python3
"""Rule #7 (audit log): append a record for every action leaving the host.

PostToolUse hook on Bash: if the executed command was an outbound call
(curl/wget/scp/ssh/rsync/nc or git push), append a single line to
`.claudeorch/audit.log` with a timestamp, the command, and the exit
status. Append-only, never truncated — the user can tail it to see what
left the box.

Non-blocking: this hook never denies; audit logging is a side-effect,
and failure to log should not brick the workflow.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

from _common import claudeorch_dir, read_event
from core.secrets_detection import detect_outbound_command


_GIT_PUSH_RE = re.compile(r"\bgit\s+push\b")
_MAX_CMD_LEN = 200


def _should_log(command: str) -> str | None:
    """Return a category label if the command is outbound, else None."""
    if not command:
        return None
    if detect_outbound_command(command):
        return "outbound"
    if _GIT_PUSH_RE.search(command):
        return "git_push"
    return None


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    category = _should_log(command)
    if not category:
        return 0

    response = event.get("tool_response") or {}
    success = response.get("success")
    exit_status = (
        "ok" if success is True
        else "fail" if success is False
        else "unknown"
    )
    clipped = command if len(command) <= _MAX_CMD_LEN else command[: _MAX_CMD_LEN - 1] + "…"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}\t{category}\t{exit_status}\t{clipped}\n"

    try:
        log_path = claudeorch_dir() / "audit.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        # audit log failure is never fatal
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
