"""ProcessBackend Protocol — abstraction over OS-specific process spawning.

Backends implement this Protocol so callers (spawner, server, watchdog,
session_manager, recovery) stay platform-agnostic. Linux uses tmux windows,
Windows will use child processes (PR 2).
"""
from __future__ import annotations

from typing import Mapping, Protocol

# Opaque target handle. tmux backend uses "claudeorch:<agent>"; Windows backend
# will use "pid:<pid>". Callers never construct Targets — they pass back what
# spawn() returned or look up via backend.list_targets().
Target = str


class ProcessBackend(Protocol):
    async def spawn(
        self,
        name: str,
        cmd: list[str],
        env: Mapping[str, str] | None = None,
    ) -> Target | None:
        """Create an isolated process/window for `name` running `cmd`.

        `env` is merged on top of the inherited environment. Returns the
        Target handle, or None on failure.
        """
        ...

    async def send_text(
        self,
        target: Target,
        text: str,
        *,
        press_enter: bool = True,
    ) -> bool:
        """Send multi-line text to the target's stdin/pane.

        Backend implementations are responsible for shell-injection safety
        (tmux uses `send-keys -l --`; Windows writes raw to stdin).
        `press_enter=False` skips the trailing Enter (rarely needed).
        """
        ...

    async def kill(self, target: Target) -> bool:
        """Atomically kill the process tree at `target`. True if it existed."""
        ...

    async def capture_output(self, target: Target, lines: int = 50) -> str:
        """Return the last N lines of output (semantics match
        `tmux capture-pane -p -S -<lines>`). Non-blocking.
        """
        ...

    async def is_alive(self, target: Target) -> bool:
        """O(1) liveness check — avoid I/O where possible."""
        ...

    def list_targets(self) -> dict[str, Target]:
        """Snapshot mapping agent_name -> Target. For checkpoints/UI."""
        ...
