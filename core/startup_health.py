"""Startup observability — verify the constitution's plumbing is alive.

Four checks, each green/yellow/red:
  - hooks:      every script referenced by `.claude/settings.json` exists
  - mcp:        `.mcp.json` parses and points at a real communication/mcp_server.py
  - gitignore:  secret-leak patterns present (delegates to gitignore_gaps)
  - state:      `.claudeorch/hook_state.json` either missing (fine) or valid

Python side is the single source of truth — a hook writes the report to
`.claudeorch/health.json` at SessionStart, and the UI reads that file
(instead of re-implementing the checks in Rust).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from core.paths import claudeorch_dir
from core.secrets_detection import gitignore_gaps

Severity = Literal["green", "yellow", "red"]

_SETTINGS_REL = Path(".claude") / "settings.json"
_MCP_REL = Path(".mcp.json")
_GITIGNORE_REL = Path(".gitignore")
_STATE_REL = Path(".claudeorch") / "hook_state.json"
_HEALTH_REL = Path(".claudeorch") / "health.json"


@dataclass(frozen=True)
class Check:
    name: str
    severity: Severity
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HealthReport:
    generated_at: str
    overall: Severity
    checks: list[Check]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "overall": self.overall,
            "checks": [asdict(c) for c in self.checks],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _combine(severities: list[Severity]) -> Severity:
    if "red" in severities:
        return "red"
    if "yellow" in severities:
        return "yellow"
    return "green"


def _collect_hook_paths(settings: dict) -> list[str]:
    """Walk the Claude Code hooks config, return every `command` value."""
    out: list[str] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event_hooks in hooks.values():
        if not isinstance(event_hooks, list):
            continue
        for matcher in event_hooks:
            if not isinstance(matcher, dict):
                continue
            inner = matcher.get("hooks")
            if not isinstance(inner, list):
                continue
            for h in inner:
                if isinstance(h, dict):
                    cmd = h.get("command")
                    if isinstance(cmd, str):
                        out.append(cmd)
    return out


def _script_paths_from_commands(commands: list[str], project_root: Path) -> list[Path]:
    """Best-effort extraction of script paths from the `command` strings.
    Matches `...scripts/hooks/<name>.py` anywhere in the command."""
    found: list[Path] = []
    seen: set[str] = set()
    marker = "scripts/hooks/"
    for cmd in commands:
        idx = cmd.find(marker)
        if idx < 0:
            continue
        rest = cmd[idx:]
        # terminate at whitespace, quote, or shell operator
        end = len(rest)
        for sep in (" ", '"', "'", "<", ">", "|", ";", "&"):
            pos = rest.find(sep)
            if 0 <= pos < end:
                end = pos
        script_rel = rest[:end]
        if script_rel in seen:
            continue
        seen.add(script_rel)
        found.append(project_root / script_rel)
    return found


def check_hooks(project_root: Path) -> Check:
    path = project_root / _SETTINGS_REL
    if not path.is_file():
        return Check(
            "hooks",
            "red",
            "`.claude/settings.json` не найден",
            [f"ожидался {path}"],
        )
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return Check("hooks", "red", "settings.json не парсится", [str(e)])

    commands = _collect_hook_paths(settings)
    if not commands:
        return Check("hooks", "yellow", "hooks в settings.json не зарегистрированы", [])

    scripts = _script_paths_from_commands(commands, project_root)
    missing = [str(s.relative_to(project_root)) for s in scripts if not s.is_file()]
    if missing:
        return Check(
            "hooks",
            "red",
            f"{len(missing)} hook-скриптов отсутствуют",
            missing,
        )
    return Check("hooks", "green", f"{len(scripts)} hooks активны", [])


def check_mcp(project_root: Path) -> Check:
    path = project_root / _MCP_REL
    if not path.is_file():
        return Check("mcp", "yellow", "`.mcp.json` отсутствует", [])
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return Check("mcp", "red", ".mcp.json не парсится", [str(e)])

    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return Check("mcp", "yellow", "MCP-серверы не настроены", [])

    missing: list[str] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        args = spec.get("args", [])
        if not isinstance(args, list):
            continue
        for arg in args:
            if isinstance(arg, str) and arg.endswith(".py"):
                p = Path(arg)
                if not p.is_absolute():
                    p = project_root / p
                if not p.is_file():
                    missing.append(f"{name}: {arg}")
    if missing:
        return Check(
            "mcp",
            "red",
            f"{len(missing)} MCP-скриптов отсутствуют",
            missing,
        )
    return Check("mcp", "green", f"{len(servers)} MCP-серверов настроено", [])


def check_gitignore(project_root: Path) -> Check:
    path = project_root / _GITIGNORE_REL
    if not path.is_file():
        return Check(
            "gitignore",
            "red",
            "`.gitignore` отсутствует",
            ["рекомендуется добавить `.env`, `*.pem`, `node_modules/`, …"],
        )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return Check("gitignore", "red", ".gitignore не читается", [str(e)])
    gaps = gitignore_gaps(content)
    if not gaps:
        return Check("gitignore", "green", "все секрет-патерны покрыты", [])
    return Check(
        "gitignore",
        "yellow",
        f"{len(gaps)} секрет-патернов не закрыто",
        list(gaps),
    )


def check_state(project_root: Path) -> Check:
    path = project_root / _STATE_REL
    if not path.is_file():
        return Check("state", "green", "hook state пуст (ожидаемо для свежей сессии)", [])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return Check("state", "yellow", "hook_state.json повреждён", [str(e)])
    if not isinstance(data, dict):
        return Check("state", "yellow", "hook_state.json — не объект", [])
    return Check("state", "green", f"hook state: {len(data)} ключей", [])


def run_all_checks(project_root: Path) -> HealthReport:
    checks = [
        check_hooks(project_root),
        check_mcp(project_root),
        check_gitignore(project_root),
        check_state(project_root),
    ]
    overall = _combine([c.severity for c in checks])
    return HealthReport(_now_iso(), overall, checks)


def write_report(report: HealthReport, project_root: Path | None = None) -> Path:
    """Persist the report to `.claudeorch/health.json`. Returns the path."""
    _ = project_root
    target = claudeorch_dir() / "health.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def format_banner(report: HealthReport) -> str | None:
    """Render a short SessionStart banner — None if everything is green."""
    bad = [c for c in report.checks if c.severity != "green"]
    if not bad:
        return None
    lines = ["## Startup observability"]
    sev_icon = {"red": "🔴", "yellow": "🟡"}
    for c in bad:
        lines.append(f"- {sev_icon.get(c.severity, '•')} **{c.name}** — {c.summary}")
        for d in c.details[:3]:
            lines.append(f"  - `{d}`")
        if len(c.details) > 3:
            lines.append(f"  - … ещё {len(c.details) - 3}")
    return "\n".join(lines)
