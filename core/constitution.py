"""Groft Constitution: shared detection/state helpers for rule-enforcement hooks.

Each of the six product rules is enforced by a Claude Code hook under
scripts/hooks/. Those scripts are thin stdin-JSON → stdout-JSON adapters;
all the actual logic lives here so it is unit-testable without running
Claude Code.

State shared across hook invocations (e.g. "how many Edit/Write calls
since the last set_plan") is persisted under `.claudeorch/hook_state.json`
because hook processes are short-lived and do not share memory.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---- Rule #5: destructive commands --------------------------------

# Patterns matched against Bash tool_input.command. Case-sensitive on
# keywords, but whitespace is flexible. Each pattern captures a category
# used in the block reason.
_DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rm -rf", re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*|--recursive|--force)")),
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+(--hard|--merge)\b")),
    ("git push --force", re.compile(r"\bgit\s+push\s+.*(--force(-with-lease)?|-f)\b")),
    ("git clean -f", re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fF][a-zA-Z]*")),
    ("git checkout --", re.compile(r"\bgit\s+checkout\s+--\s")),
    ("git branch -D", re.compile(r"\bgit\s+branch\s+-D\b")),
    ("DROP TABLE", re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE)),
    ("dd of=", re.compile(r"\bdd\s+.*\bof=")),
    ("mkfs", re.compile(r"\bmkfs\.")),
]


def detect_destructive_command(command: str) -> str | None:
    """Return the category label for a destructive command, or None.

    Empty or whitespace-only input returns None.
    """
    if not command or not command.strip():
        return None
    for label, pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(command):
            return label
    return None


# ---- Rule #6: user corrections ------------------------------------

# Multiline messages: match anywhere in the prompt. Russian + English.
# We err on the side of precision (single keywords like "нет" alone are
# too noisy), requiring at least a short phrase that carries correction
# semantics.
_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bне\s+(так|надо|нужно|стоит|делай)\b", re.IGNORECASE),
    re.compile(r"\b(стоп|хватит)\b", re.IGNORECASE),
    re.compile(r"\bты\s+(не\s+прав|ошиб)", re.IGNORECASE),
    re.compile(r"\b(don'?t|stop|wrong|nope|no,?\s+that)\b", re.IGNORECASE),
    re.compile(r"\b(that'?s\s+wrong|that\s+is\s+wrong)\b", re.IGNORECASE),
    re.compile(r"\b(плохо|неправильно|странно)\b", re.IGNORECASE),
    re.compile(r"\b(why\s+(did|are))\b", re.IGNORECASE),
]


def detect_user_correction(prompt: str) -> bool:
    """True if the prompt looks like a correction / pushback signal."""
    if not prompt or not prompt.strip():
        return False
    return any(p.search(prompt) for p in _CORRECTION_PATTERNS)


# ---- Rule #2: confident claims without grounding ------------------

# Phrases that read as "I'm sure" or assertive factual claims. Pairing
# any of these with a turn that had zero Read/Grep/get_relevant_context
# tool calls is a red flag for hallucination.
_CONFIDENT_CLAIM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b100\s*%", re.IGNORECASE),
    re.compile(r"\b(definitely|certainly|guaranteed)\b", re.IGNORECASE),
    re.compile(r"\b(я\s+уверен|точно|гарантирую)\b", re.IGNORECASE),
    re.compile(r"\b(всегда|никогда)\s+(делает|работает|возвращает)", re.IGNORECASE),
    re.compile(r"\balways\s+(returns|raises|does)", re.IGNORECASE),
]

# Evidence tools: if any of these ran this turn, the claim is considered
# grounded. Covers both direct reads and MCP-mediated memory lookup.
GROUNDING_TOOLS: frozenset[str] = frozenset({
    "Read", "Grep", "Glob",
    "mcp__claudeorch-comms__get_relevant_context",
})


def detect_confident_claim(text: str) -> str | None:
    """Return the matched phrase that looks like a confident claim, or None."""
    if not text or not text.strip():
        return None
    for pat in _CONFIDENT_CLAIM_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


# ---- Rule #4: plan-less edit streak -------------------------------

@dataclass
class EditStreakState:
    """Count of Edit/Write tool calls since the last set_plan."""

    edits_since_plan: int = 0
    last_plan_ts: str | None = None


EDIT_STREAK_NUDGE_THRESHOLD = 5


# ---- State persistence --------------------------------------------

def _state_path(claudeorch_dir: Path) -> Path:
    return claudeorch_dir / "hook_state.json"


def load_state(claudeorch_dir: Path) -> dict[str, Any]:
    path = _state_path(claudeorch_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(claudeorch_dir: Path, state: dict[str, Any]) -> None:
    claudeorch_dir.mkdir(parents=True, exist_ok=True)
    tmp = _state_path(claudeorch_dir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_state_path(claudeorch_dir))


def bump_edit_streak(claudeorch_dir: Path) -> int:
    state = load_state(claudeorch_dir)
    current = int(state.get("edits_since_plan", 0)) + 1
    state["edits_since_plan"] = current
    save_state(claudeorch_dir, state)
    return current


def reset_edit_streak(claudeorch_dir: Path) -> None:
    state = load_state(claudeorch_dir)
    state["edits_since_plan"] = 0
    save_state(claudeorch_dir, state)


# ---- Hook output helpers ------------------------------------------

def deny_response(reason: str) -> dict[str, Any]:
    """JSON payload that asks Claude Code to deny a tool call."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def context_response(text: str) -> dict[str, Any]:
    """JSON payload to inject additional context at SessionStart/UserPromptSubmit."""
    return {"additionalContext": text}
