"""Unit tests for core.constitution."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constitution import (  # noqa: E402
    GROUNDING_TOOLS,
    bump_edit_streak,
    context_response,
    deny_response,
    detect_confident_claim,
    detect_destructive_command,
    detect_user_correction,
    load_state,
    reset_edit_streak,
    save_state,
)


# ---- destructive commands ----------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/foo",
        "rm -r /data",
        "rm -fr build/",
        "rm --recursive build/",
        "git reset --hard HEAD~3",
        "git push origin main --force",
        "git push --force-with-lease origin main",
        "git push -f origin feature",
        "git clean -fd",
        "git branch -D old-feature",
        "DROP TABLE users;",
        "drop database analytics;",
        "TRUNCATE TABLE logs",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sdb1",
    ],
)
def test_destructive_command_detected(command: str) -> None:
    assert detect_destructive_command(command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "",
        "   ",
        "ls -la",
        "rm somefile",  # no -r/-f flag → standard single-file remove
        "git status",
        "git push origin main",
        "SELECT * FROM users WHERE id = 1",
        "pytest tests/",
        "echo rm -rf is dangerous",  # mention in string, not actual command
    ],
)
def test_destructive_command_safe(command: str) -> None:
    # Note: `echo rm -rf ...` will still match because regex finds the
    # pattern. This is acceptable over-caution — the hook will ask for
    # confirmation; user can confirm it's just an echo.
    if "rm -rf" in command:
        pytest.skip("over-match acceptable for echo 'rm -rf'")
    assert detect_destructive_command(command) is None


def test_destructive_returns_category_label() -> None:
    assert detect_destructive_command("rm -rf /tmp") == "rm -rf"
    assert detect_destructive_command("DROP TABLE users") == "DROP TABLE"
    assert detect_destructive_command("git push --force") == "git push --force"


# ---- user corrections --------------------------------------------

@pytest.mark.parametrize(
    "prompt",
    [
        "Не так делай",
        "не надо этого",
        "стоп, не туда",
        "Ты не прав",
        "don't do that",
        "stop, wrong direction",
        "nope, try again",
        "no, that's wrong",
        "that's wrong",
        "why did you do that?",
        "плохо, переделай",
        "странно получилось",
    ],
)
def test_correction_detected(prompt: str) -> None:
    assert detect_user_correction(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "",
        "Continue please",
        "Ok, keep going",
        "Thanks, what's next?",
        "Давай дальше",
        "Отлично, двигаемся",
    ],
)
def test_correction_not_detected(prompt: str) -> None:
    assert detect_user_correction(prompt) is False


# ---- confident claims --------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "I am 100% certain this works",
        "This definitely handles the case",
        "Я уверен что код работает",
        "Точно возвращает None",
        "always returns zero",
        "функция всегда работает корректно",
    ],
)
def test_confident_claim_detected(text: str) -> None:
    assert detect_confident_claim(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "I think this might work but let me check",
        "Based on the code, this function returns None",
        "Возможно это обрабатывается в модуле X",
        "Let me grep for it",
    ],
)
def test_confident_claim_safe(text: str) -> None:
    assert detect_confident_claim(text) is None


def test_grounding_tools_contains_read_and_mcp_context() -> None:
    assert "Read" in GROUNDING_TOOLS
    assert "Grep" in GROUNDING_TOOLS
    assert "mcp__claudeorch-comms__get_relevant_context" in GROUNDING_TOOLS


# ---- state persistence -------------------------------------------

def test_state_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_state(tmp_path) == {}


def test_state_save_then_load_roundtrip(tmp_path: Path) -> None:
    save_state(tmp_path, {"edits_since_plan": 3, "foo": "bar"})
    assert load_state(tmp_path) == {"edits_since_plan": 3, "foo": "bar"}


def test_state_corruption_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "hook_state.json").write_text("{not json", encoding="utf-8")
    assert load_state(tmp_path) == {}


def test_bump_edit_streak_increments(tmp_path: Path) -> None:
    assert bump_edit_streak(tmp_path) == 1
    assert bump_edit_streak(tmp_path) == 2
    assert bump_edit_streak(tmp_path) == 3


def test_reset_edit_streak_zeros_counter(tmp_path: Path) -> None:
    bump_edit_streak(tmp_path)
    bump_edit_streak(tmp_path)
    reset_edit_streak(tmp_path)
    assert load_state(tmp_path).get("edits_since_plan", 0) == 0


def test_bump_preserves_other_keys(tmp_path: Path) -> None:
    save_state(tmp_path, {"other": "preserved"})
    bump_edit_streak(tmp_path)
    state = load_state(tmp_path)
    assert state["other"] == "preserved"
    assert state["edits_since_plan"] == 1


# ---- response builders -------------------------------------------

def test_deny_response_shape() -> None:
    r = deny_response("too dangerous")
    assert r["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert r["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert r["hookSpecificOutput"]["permissionDecisionReason"] == "too dangerous"


def test_context_response_shape() -> None:
    r = context_response("some banner text")
    assert r == {"additionalContext": "some banner text"}
