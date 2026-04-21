#!/usr/bin/env python3
"""Rule #7 (hard-deny): always-forbidden sensitive paths.

PreToolUse hook that blocks access to secret stores the orchestrator
should never touch, no matter the task:

  - Read/Edit/Write on a hard-denied path  → deny
  - Bash command that cats/greps/xxd's one → deny

Unlike Rule #5 (destructive commands), there is *no* override marker for
Rule #7 hard-denies. If the user genuinely needs to touch `~/.ssh/id_rsa`
they can do it themselves in a terminal — orchestrating coding work
doesn't require private keys.
"""
from __future__ import annotations

import sys

from _common import read_event, write_response
from core.constitution import deny_response
from core.secrets_detection import bash_reads_sensitive_file, is_hard_deny_path


_FILE_TOOLS = {"Read", "Edit", "Write", "NotebookEdit"}


def _reason(path: str, pattern: str, via: str) -> str:
    return (
        f"❌ Rule #7 (hard-deny): `{path}` matches sensitive path pattern "
        f"`{pattern}` and cannot be accessed via {via}. "
        "Orchestrating coding work does not require secret-store files "
        "(SSH keys, cloud credentials, .env). No override available — "
        "if you genuinely need this, run the command yourself in a shell."
    )


def main() -> int:
    event = read_event()
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}

    if tool_name in _FILE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        if path:
            matched = is_hard_deny_path(path)
            if matched:
                write_response(deny_response(_reason(path, matched, tool_name)))
                return 0

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        hit = bash_reads_sensitive_file(command)
        if hit:
            tool, target = hit
            matched = is_hard_deny_path(target) or "sensitive-path"
            write_response(deny_response(_reason(target, matched, f"Bash `{tool}`")))
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
