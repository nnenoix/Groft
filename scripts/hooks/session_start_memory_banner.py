#!/usr/bin/env python3
"""Rule #1: user doesn't explain the project twice.

At every SessionStart Claude Code invokes this script; it injects a
banner with current plan + recent session-log blocks + MEMORY.md index
so opus starts the conversation already knowing where things stopped
and what's been decided. No more "продолжаем" leading to re-explanation.
"""
from __future__ import annotations

import sys
from pathlib import Path

from _common import project_memory_dir, read_event, write_response
from core.constitution import context_response


MEMORY_INDEX_HOME = (
    Path.home() / ".claude" / "projects" / "-mnt-d-orchkerstr" / "memory" / "MEMORY.md"
)
SESSION_LOG_MAX_BLOCKS = 3
SESSION_LOG_MAX_CHARS = 4000


def _read_current_plan(memory_root: Path) -> str:
    path = memory_root / "current-plan.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_recent_session_log(memory_root: Path, n: int) -> str:
    path = memory_root / "session-log.md"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    sep = "\n---\n\n"
    parts = [p for p in text.split(sep) if p.strip()]
    if len(parts) <= 1:
        return ""
    blocks = parts[-n:]
    joined = sep.join(blocks)
    if len(joined) > SESSION_LOG_MAX_CHARS:
        joined = "... (older blocks truncated) ...\n\n" + joined[-SESSION_LOG_MAX_CHARS:]
    return joined


def _read_memory_index() -> str:
    if not MEMORY_INDEX_HOME.exists():
        return ""
    try:
        return MEMORY_INDEX_HOME.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def build_banner(memory_root: Path) -> str:
    parts: list[str] = ["# Groft session context (auto-injected)\n"]

    plan = _read_current_plan(memory_root)
    if plan:
        parts.append("## Current plan\n\n" + plan)

    recent = _read_recent_session_log(memory_root, SESSION_LOG_MAX_BLOCKS)
    if recent:
        parts.append(
            f"## Last {SESSION_LOG_MAX_BLOCKS} subagent blocks\n\n" + recent
        )

    index = _read_memory_index()
    if index:
        parts.append("## Long-term memory index (~/.claude auto-memory)\n\n" + index)

    parts.append(
        "## Six-rule constitution\n"
        "1. No re-explain — consult memory first.\n"
        "2. No hallucination — call Read/Grep/get_relevant_context before factual claims.\n"
        "3. No breakage — pytest before commit.\n"
        "4. Visible progress — set_plan/advance_step; announce in chat.\n"
        "5. User can intervene — pause before destructive ops.\n"
        "6. Learn from corrections — save_feedback_rule on pushback."
    )
    return "\n\n".join(parts) + "\n"


def main() -> int:
    _event = read_event()
    banner = build_banner(project_memory_dir())
    write_response(context_response(banner))
    return 0


if __name__ == "__main__":
    sys.exit(main())
