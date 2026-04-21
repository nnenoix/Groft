#!/usr/bin/env python3
"""Rule #7 (gitignore audit): warn at session start if .gitignore is
missing common secret-leak patterns.

SessionStart hook: reads the project .gitignore, computes gaps against
a recommended list (.env, *.pem, node_modules/, etc.), and if any are
missing, injects a one-shot reminder so opus can bring it up with the
user before touching secrets.

Non-blocking. If .gitignore doesn't exist, we suggest creating one.
"""
from __future__ import annotations

import sys

from _common import PROJECT_ROOT, read_event, write_response
from core.constitution import context_response
from core.secrets_detection import gitignore_gaps


def _read_gitignore() -> str | None:
    path = PROJECT_ROOT / ".gitignore"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def main() -> int:
    _event = read_event()
    content = _read_gitignore()
    gaps = gitignore_gaps(content if content is not None else "")
    if not gaps:
        return 0

    pretty = ", ".join(f"`{g}`" for g in gaps)
    if content is None:
        banner = (
            "## Rule #7 (.gitignore audit)\n\n"
            f"No `.gitignore` found in the project root. Recommended to add: {pretty}.\n"
            "If the user is okay with it, create `.gitignore` with these patterns."
        )
    else:
        banner = (
            "## Rule #7 (.gitignore audit)\n\n"
            f"`.gitignore` is missing common secret-leak guards: {pretty}.\n"
            "Flag this to the user and offer to add them."
        )
    write_response(context_response(banner))
    return 0


if __name__ == "__main__":
    sys.exit(main())
