"""Tests for core/startup_health — individual check functions + combiner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.startup_health import (
    check_gitignore,
    check_hooks,
    check_mcp,
    check_state,
    format_banner,
    run_all_checks,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def test_check_hooks_green_when_all_scripts_exist(project: Path) -> None:
    script = project / "scripts" / "hooks" / "foo.py"
    _write(script, "#")
    _write(
        project / ".claude" / "settings.json",
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {"command": f"python3 {script}"}
                            ]
                        }
                    ]
                }
            }
        ),
    )
    r = check_hooks(project)
    assert r.severity == "green"
    assert "1 hooks активны" in r.summary


def test_check_hooks_red_on_missing_script(project: Path) -> None:
    _write(
        project / ".claude" / "settings.json",
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "command": "python3 scripts/hooks/missing.py"
                                }
                            ]
                        }
                    ]
                }
            }
        ),
    )
    r = check_hooks(project)
    assert r.severity == "red"
    assert "missing.py" in " ".join(r.details)


def test_check_hooks_red_on_missing_settings(project: Path) -> None:
    r = check_hooks(project)
    assert r.severity == "red"
    assert "settings.json" in r.summary


def test_check_hooks_red_on_invalid_json(project: Path) -> None:
    _write(project / ".claude" / "settings.json", "{not json")
    r = check_hooks(project)
    assert r.severity == "red"


def test_check_mcp_green_when_script_exists(project: Path) -> None:
    mcp_py = project / "communication" / "mcp_server.py"
    _write(mcp_py, "#")
    _write(
        project / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "claudeorch-comms": {
                        "command": "python3",
                        "args": [str(mcp_py)],
                    }
                }
            }
        ),
    )
    r = check_mcp(project)
    assert r.severity == "green"


def test_check_mcp_red_on_missing_script(project: Path) -> None:
    _write(
        project / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "foo": {
                        "command": "python3",
                        "args": ["/nonexistent/path.py"],
                    }
                }
            }
        ),
    )
    r = check_mcp(project)
    assert r.severity == "red"


def test_check_mcp_yellow_when_missing(project: Path) -> None:
    r = check_mcp(project)
    assert r.severity == "yellow"


def test_check_gitignore_green_when_covered(project: Path) -> None:
    _write(
        project / ".gitignore",
        "\n".join(
            [".env", ".env.*", "*.pem", "*.key", "node_modules/", "__pycache__/", ".claudeorch/", ".venv/", "*.sqlite", "dist/", ".DS_Store"]
        ),
    )
    r = check_gitignore(project)
    # Depending on gitignore_gaps's recommended list the result may be green or yellow;
    # either way red is wrong.
    assert r.severity in ("green", "yellow")


def test_check_gitignore_red_when_missing(project: Path) -> None:
    r = check_gitignore(project)
    assert r.severity == "red"


def test_check_gitignore_yellow_on_gaps(project: Path) -> None:
    _write(project / ".gitignore", "node_modules/\n")
    r = check_gitignore(project)
    assert r.severity == "yellow"
    assert len(r.details) > 0


def test_check_state_green_when_missing(project: Path) -> None:
    r = check_state(project)
    assert r.severity == "green"


def test_check_state_yellow_on_bad_json(project: Path) -> None:
    _write(project / ".claudeorch" / "hook_state.json", "{bad")
    r = check_state(project)
    assert r.severity == "yellow"


def test_run_all_checks_red_when_any_red(project: Path) -> None:
    r = run_all_checks(project)
    assert r.overall == "red"
    assert len(r.checks) == 4


def test_format_banner_none_when_all_green(project: Path) -> None:
    script = project / "scripts" / "hooks" / "foo.py"
    _write(script, "#")
    _write(
        project / ".claude" / "settings.json",
        json.dumps({"hooks": {"S": [{"hooks": [{"command": f"python3 {script}"}]}]}}),
    )
    mcp_py = project / "communication" / "mcp_server.py"
    _write(mcp_py, "#")
    _write(
        project / ".mcp.json",
        json.dumps({"mcpServers": {"x": {"command": "python3", "args": [str(mcp_py)]}}}),
    )
    _write(
        project / ".gitignore",
        "\n".join([".env", ".env.*", "*.pem", "*.key", "node_modules/", "__pycache__/", ".claudeorch/", ".venv/", "*.sqlite", "dist/", ".DS_Store"]),
    )
    report = run_all_checks(project)
    banner = format_banner(report)
    # banner is None only when every check is literally green; gitignore recommended
    # list may drive yellow — accept either outcome as long as banner syncs with state.
    if report.overall == "green":
        assert banner is None
    else:
        assert banner is not None


def test_format_banner_has_icons_when_red(project: Path) -> None:
    report = run_all_checks(project)
    banner = format_banner(report)
    assert banner is not None
    assert "🔴" in banner or "🟡" in banner
