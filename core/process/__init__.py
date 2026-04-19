"""ProcessBackend factory.

`select_backend(config)` returns a ProcessBackend implementation per the
`process.backend` config key (`tmux` | `windows` | `auto`). Default `auto`
inspects `platform.system()`. The Windows path raises NotImplementedError
until PR 2 lands the `WindowsBackend` implementation.
"""
from __future__ import annotations

import platform
from typing import Any

from core.process.backend import ProcessBackend, Target
from core.process.tmux_backend import TmuxBackend

__all__ = ["ProcessBackend", "Target", "TmuxBackend", "select_backend"]


def select_backend(config: dict[str, Any] | None = None) -> ProcessBackend:
    cfg = config or {}
    process_section = cfg.get("process") if isinstance(cfg, dict) else None
    backend_name = "auto"
    if isinstance(process_section, dict):
        candidate = process_section.get("backend")
        if isinstance(candidate, str) and candidate:
            backend_name = candidate

    if backend_name == "auto":
        # auto-resolution: tmux on POSIX, windows backend on Windows. The
        # Windows path is intentionally a hard-stop until PR 2 ships the
        # implementation — surface this loudly rather than fall back to tmux
        # on a host where tmux is missing.
        if platform.system() == "Windows":
            raise NotImplementedError(
                "Windows backend lands in PR 2; "
                "set process.backend: tmux if you need to force"
            )
        return TmuxBackend()
    if backend_name == "tmux":
        return TmuxBackend()
    if backend_name == "windows":
        raise NotImplementedError(
            "Windows backend lands in PR 2; "
            "set process.backend: tmux if you need to force"
        )
    raise ValueError(f"unknown process.backend: {backend_name!r}")
