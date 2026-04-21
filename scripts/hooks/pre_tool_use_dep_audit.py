#!/usr/bin/env python3
"""Rule #7 (dep audit): block suspicious package installs.

PreToolUse hook on Bash: when the command is a pip/npm/yarn install,
run a typosquat check against a curated list of popular package names.
If the install target is one edit away from a popular name (but not
equal), deny with a pointer to the likely-intended target.

This is a heuristic, not a CVE database. CVE-level verification would
require network access and a fresh advisory feed — out of scope for a
pure-Python hook. The aim here is to catch the obvious foot-guns
(`requets` for `requests`, `axioss` for `axios`) before install.
"""
from __future__ import annotations

import sys

from _common import read_event, write_response
from core.constitution import deny_response
from core.secrets_detection import detect_package_install, typosquat_candidates


_OVERRIDE_MARKER = "# groft-user-confirmed"


def main() -> int:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if not command or _OVERRIDE_MARKER in command:
        return 0

    parsed = detect_package_install(command)
    if parsed is None:
        return 0
    ecosystem, packages = parsed
    if not packages:
        return 0

    hits = typosquat_candidates(ecosystem, packages)
    if not hits:
        return 0

    pretty = "\n".join(
        f"  - `{installed}` looks like a typosquat of `{target}`"
        for installed, target in hits
    )
    reason = (
        f"⚠ Rule #7 (dep audit): suspicious {ecosystem} install target(s):\n\n"
        f"{pretty}\n\n"
        "If you meant the popular package, fix the name. If this really is a "
        "different project you intend to install, retry with "
        f"`{_OVERRIDE_MARKER}` appended to the command."
    )
    write_response(deny_response(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
