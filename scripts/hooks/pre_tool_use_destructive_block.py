#!/usr/bin/env python3
"""Rule #5: user can intervene — confirm before destructive commands.

PreToolUse hook: when the tool is Bash and the command matches a
destructive pattern (rm -rf, git reset --hard, git push --force, DROP
TABLE, etc), deny the call with a reason that prompts opus to ask the
user for explicit confirmation before retrying.

This is strictly a pause, not a permanent block — once user confirms
and opus retries with the same command, opus can emit an override
marker in the command (e.g. `# confirmed-by-user` comment) which this
hook will recognize. Keeping the override intentionally awkward so it
isn't used by accident.
"""
from __future__ import annotations

import sys

from _common import read_event, write_response
from core.constitution import deny_response, detect_destructive_command


_OVERRIDE_MARKER = "# groft-user-confirmed"


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if _OVERRIDE_MARKER in command:
        return 0

    category = detect_destructive_command(command)
    if category is None:
        return 0

    reason = (
        f"⚠ Rule #5 (user can intervene): command matches destructive "
        f"pattern `{category}`. Pause and ask the user to confirm before "
        "running it. If confirmed, retry with "
        f"`{_OVERRIDE_MARKER}` comment appended to the command."
    )
    write_response(deny_response(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
