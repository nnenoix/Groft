#!/usr/bin/env python3
"""Rule #3: do not break what works — pytest gate on git commit/push.

PreToolUse hook: when the tool is Bash and the command is `git commit`
or `git push`, run pytest first. If any test fails, deny the call with
a reason that tells opus exactly which tests are red.

Fails open on unexpected errors (if pytest itself cannot start, we allow
the commit rather than block everyone — a broken hook should not brick
the workflow).
"""
from __future__ import annotations

import re
import subprocess
import sys

from _common import PROJECT_ROOT, read_event, write_response
from core.constitution import deny_response


_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")
_PUSH_RE = re.compile(r"^\s*git\s+push\b")


def _is_gated_command(command: str) -> bool:
    return bool(_COMMIT_RE.search(command) or _PUSH_RE.search(command))


def _run_pytest() -> tuple[bool, str]:
    """Return (passed, summary)."""
    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", "-q", "--tb=short"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return True, f"hook could not run pytest cleanly ({exc}); failing open"

    if proc.returncode == 0:
        tail = proc.stdout.strip().splitlines()[-1:] if proc.stdout else []
        return True, " ".join(tail)
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # Keep last ~30 lines — enough for failing test list + summary
    lines = combined.strip().splitlines()[-30:]
    return False, "\n".join(lines)


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if not _is_gated_command(command):
        return 0

    passed, summary = _run_pytest()
    if passed:
        return 0

    reason = (
        "❌ Rule #3 (don't break what works): pytest failed — cannot "
        f"proceed with `{command.strip()[:80]}...`.\n\n"
        "Fix the failing tests first, then retry.\n\n"
        f"```\n{summary}\n```"
    )
    write_response(deny_response(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
