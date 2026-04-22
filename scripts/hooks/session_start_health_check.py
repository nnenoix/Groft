#!/usr/bin/env python3
"""Phase 20 — startup observability.

SessionStart hook: runs the constitution's health checks (hooks, MCP,
gitignore, state), persists the report to `.claudeorch/health.json` for
the UI to read, and injects a short banner when anything is off-green.

Replaces the narrower `session_start_gitignore_audit.py` — gitignore is
now one of four checks inside `core.startup_health`.
"""
from __future__ import annotations

import sys

from _common import PROJECT_ROOT, read_event, write_response
from core.constitution import context_response
from core.startup_health import format_banner, run_all_checks, write_report


def main() -> int:
    _event = read_event()
    report = run_all_checks(PROJECT_ROOT)
    try:
        write_report(report)
    except OSError:
        # Non-fatal: banner still injected even if we can't persist the file.
        pass
    banner = format_banner(report)
    if banner is not None:
        write_response(context_response(banner))
    return 0


if __name__ == "__main__":
    sys.exit(main())
