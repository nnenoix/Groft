#!/usr/bin/env python3
"""Rule #7: do not leak secrets — pre-commit / pre-push secrets scanner.

PreToolUse hook: when the tool is Bash and the command is `git commit`
or `git push`, scan the content about to leave the repo for known
secret patterns. Deny with a pointer to the offending kind/line.

- git commit → scan the staged diff (`git diff --cached`)
- git push   → scan the range of commits about to be pushed
              (`git log @{u}..HEAD -p`; falls back to staged diff if no
              upstream is configured yet)

The scan is best-effort: on any subprocess failure we fail open (Rule #3
says don't brick the workflow). False positives are preferred over false
negatives — if in doubt, deny and let the user override by amending the
commit to remove the match.
"""
from __future__ import annotations

import re
import subprocess
import sys

from _common import PROJECT_ROOT, read_event, write_response
from core.constitution import deny_response
from core.secrets_detection import detect_secrets


_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")
_PUSH_RE = re.compile(r"^\s*git\s+push\b")


def _run_git(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _staged_diff() -> str:
    code, out = _run_git("diff", "--cached", "--no-color")
    return out if code == 0 else ""


def _push_range_diff() -> str:
    # Try the tracked upstream first.
    code, out = _run_git("log", "@{u}..HEAD", "-p", "--no-color")
    if code == 0 and out.strip():
        return out
    # No upstream yet → scan the whole history of the current branch minus
    # any merged commits from origin/main as a reasonable approximation.
    code, out = _run_git("log", "origin/main..HEAD", "-p", "--no-color")
    if code == 0 and out.strip():
        return out
    # Final fallback: just the staged diff.
    return _staged_diff()


def _format_hits(hits: list, max_items: int = 5) -> str:
    rows: list[str] = []
    for h in hits[:max_items]:
        line = f" (line {h.line})" if h.line is not None else ""
        rows.append(f"  - {h.kind}: {h.sample}{line}")
    if len(hits) > max_items:
        rows.append(f"  …and {len(hits) - max_items} more")
    return "\n".join(rows)


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    is_commit = bool(_COMMIT_RE.search(command))
    is_push = bool(_PUSH_RE.search(command))
    if not (is_commit or is_push):
        return 0

    blob = _push_range_diff() if is_push else _staged_diff()
    if not blob:
        return 0

    hits = detect_secrets(blob)
    if not hits:
        return 0

    scope = "about-to-push commit range" if is_push else "staged diff"
    reason = (
        f"❌ Rule #7 (don't leak secrets): {len(hits)} secret-shaped "
        f"match(es) found in {scope}.\n\n"
        f"{_format_hits(hits)}\n\n"
        "Remove / rotate the secret, re-stage, then retry. If this is a "
        "false positive, redact the sample so the pattern stops matching."
    )
    write_response(deny_response(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
