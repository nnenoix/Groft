from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path


@cache
def install_root() -> Path:
    """Read-only resource root. PyInstaller: sys._MEIPASS. Dev: repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


@cache
def user_data_root() -> Path:
    """Writable runtime data root. Honours CLAUDEORCH_USER_DATA; else install_root()."""
    env = os.environ.get("CLAUDEORCH_USER_DATA")
    if env:
        return Path(env).resolve()
    return install_root()


def claudeorch_dir() -> Path:
    """Writable .claudeorch directory — DBs, logs, panes."""
    path = user_data_root() / ".claudeorch"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """Log output directory under .claudeorch."""
    path = claudeorch_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def panes_dir() -> Path:
    """Per-agent pane log directory (Windows backend)."""
    path = claudeorch_dir() / "panes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def architecture_dir() -> Path:
    """Writable architecture docs directory."""
    path = user_data_root() / "architecture"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_dir() -> Path:
    """Writable per-agent memory directory."""
    path = user_data_root() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_archive_dir() -> Path:
    """Pre-compression memory archive directory."""
    path = memory_dir() / "archive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tasks_dir() -> Path:
    """Writable tasks directory (backlog/current/done)."""
    path = user_data_root() / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agents_dir() -> Path:
    """Writable .claude/agents directory watched by agents_watcher."""
    path = user_data_root() / ".claude" / "agents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def handoff_dir() -> Path:
    """Claude Design handoff drop directory. CLAUDEORCH_HANDOFF_DIR override."""
    env = os.environ.get("CLAUDEORCH_HANDOFF_DIR")
    path = Path(env).resolve() if env else user_data_root() / "ork-handoff"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    """Writable config.yml path."""
    return user_data_root() / "config.yml"


def default_config_path() -> Path:
    """Bundled read-only config.yml template."""
    return install_root() / "config.yml"
