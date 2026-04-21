#!/usr/bin/env python3
"""Rule #2: don't hallucinate — flag confident claims made without grounding.

Stop hook: scans the last assistant message for "confident claim"
phrasings ("100% certain", "всегда возвращает", "guaranteed", etc) and
checks the transcript for Read/Grep/get_relevant_context calls in the
current turn. If a confident claim appears without grounding tool use,
blocks the Stop with a reason that asks opus to verify before ending.

Blocking a Stop means opus must continue the turn — in practice it will
do the grounding call and re-emit the claim with citations, or soften
the assertion. False positives are possible; the override is to re-emit
the claim paraphrased to avoid the trigger words.

`stop_hook_active` is checked to prevent infinite loops where the hook
itself triggers another Stop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import read_event, write_response
from core.constitution import GROUNDING_TOOLS, detect_confident_claim


def _this_turn_used_grounding_tools(transcript_path: str) -> bool:
    """Walk the transcript backwards until the last user message; any
    grounding tool use in that range counts as "this turn"."""
    path = Path(transcript_path)
    if not path.exists():
        return True  # fail open — cannot verify, don't block

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return True

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "user":
            return False  # reached the turn boundary without finding grounding
        if entry.get("type") == "assistant":
            message = entry.get("message") or {}
            content = message.get("content") or []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = block.get("name")
                    if name in GROUNDING_TOOLS:
                        return True
    return False


def main() -> int:
    event = read_event()
    if event.get("stop_hook_active"):
        return 0
    last_msg = event.get("last_assistant_message") or ""
    match = detect_confident_claim(last_msg)
    if not match:
        return 0
    if _this_turn_used_grounding_tools(event.get("transcript_path", "")):
        return 0
    write_response({
        "decision": "block",
        "reason": (
            "⚠ Rule #2 (no hallucination): your response contains a confident "
            f"claim (matched `{match}`) without any Read/Grep/get_relevant_context "
            "call this turn. Before ending the turn, verify the claim by "
            "reading the relevant file or searching memory, or soften the "
            "language to match your actual confidence level."
        ),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
