#!/usr/bin/env python3
"""Rule #4: visible progress — nudge when many edits pile up without a plan.

PostToolUse hook: every successful Edit/Write increments a counter.
Every set_plan call resets it. When the counter crosses a threshold,
stderr emits a reminder that makes its way into Claude's next turn,
prompting opus to call set_plan.

This is a nudge, not a block — opus may be doing atomic work that
doesn't warrant a formal plan. The reminder just keeps rule #4 honest.
"""
from __future__ import annotations

import sys

from _common import claudeorch_dir, read_event
from core.constitution import (
    EDIT_STREAK_NUDGE_THRESHOLD,
    bump_edit_streak,
    reset_edit_streak,
)


_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
_PLAN_TOOLS = {
    "mcp__claudeorch-comms__set_plan",
    "mcp__claudeorch-comms__advance_step",
}


def main() -> int:
    event = read_event()
    tool_name = event.get("tool_name") or ""
    response = event.get("tool_response") or {}
    if response and response.get("success") is False:
        return 0

    dir_ = claudeorch_dir()

    if tool_name in _PLAN_TOOLS:
        reset_edit_streak(dir_)
        return 0

    if tool_name not in _EDIT_TOOLS:
        return 0

    streak = bump_edit_streak(dir_)
    if streak == EDIT_STREAK_NUDGE_THRESHOLD:
        sys.stderr.write(
            f"⚠ Rule #4: {streak} edits since last set_plan. "
            "If this is multi-step work, call set_plan(goal, steps) now so "
            "the user sees step N of M instead of silence.\n"
        )
        return 2  # non-zero makes stderr visible to Claude as feedback
    return 0


if __name__ == "__main__":
    sys.exit(main())
