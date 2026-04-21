#!/usr/bin/env python3
"""Rule #6: learn from corrections — nudge to save_feedback_rule.

UserPromptSubmit hook: if the prompt matches correction patterns ("не
так", "stop", "wrong", "don't", etc), inject a reminder that the next
response should begin with a save_feedback_rule call. Does NOT block
the prompt.
"""
from __future__ import annotations

import sys

from _common import read_event, write_response
from core.constitution import context_response, detect_user_correction


_REMINDER = (
    "⚠ Rule #6 (learn from corrections): the user's prompt looks like "
    "a correction. Before answering, call "
    "`mcp__claudeorch-comms__save_feedback_rule(rule, why, how_to_apply)` "
    "to persist this lesson — otherwise it will be lost in the next session."
)


def main() -> int:
    event = read_event()
    prompt = event.get("prompt", "")
    if not detect_user_correction(prompt):
        return 0
    write_response(context_response(_REMINDER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
