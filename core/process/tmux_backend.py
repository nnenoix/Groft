"""tmux-backed ProcessBackend.

Encapsulates every `tmux` subprocess call previously scattered across the
codebase: window create/kill (spawner), send-keys (server, session_manager),
capture-pane (watchdog). Linux behaviour is bit-identical with the pre-refactor
implementation — same args, same logging, same return codes.

Security note: `send_text` uses the multi-line `send-keys -l --` + bare
`send-keys Enter` sequence. The `-l` flag types literal text instead of
interpreting it as a key sequence, which is what blocks shell-style injection
through chat content. Callers MUST NOT bypass this method.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Mapping

from core.process.backend import Target

log = logging.getLogger(__name__)

_SESSION = "claudeorch"


class TmuxBackend:
    def __init__(self) -> None:
        # name -> Target mapping built up by spawn(); list_targets() returns a
        # shallow copy so callers can iterate without races on the live dict.
        self._targets: dict[str, Target] = {}

    async def spawn(
        self,
        name: str,
        cmd: list[str],
        env: Mapping[str, str] | None = None,
    ) -> Target | None:
        target = f"{_SESSION}:{name}"
        if not await self._run_tmux(["new-window", "-t", _SESSION, "-n", name]):
            log.warning("tmux new-window failed for agent=%s; aborting spawn", name)
            return None
        # tmux send-keys takes a single shell line, not a list. Compose the
        # command with KEY=VAL prefixes so the spawned shell inherits env without
        # an extra `tmux setenv` round-trip.
        env_prefix = ""
        if env:
            env_prefix = " ".join(f"{k}={v}" for k, v in env.items()) + " "
        shell_line = env_prefix + " ".join(cmd)
        if not await self._run_tmux(["send-keys", "-t", target, shell_line, "Enter"]):
            log.warning(
                "tmux send-keys failed for agent=%s window=%s; aborting spawn",
                name,
                target,
            )
            # best-effort teardown of the orphan window so the pane map stays clean
            await self._run_tmux(["kill-window", "-t", target])
            return None
        self._targets[name] = target
        return target

    async def send_text(
        self,
        target: Target,
        text: str,
        *,
        press_enter: bool = True,
    ) -> bool:
        # split on newlines so literal typing per-line + Enter preserves multi-line payloads.
        # `-l --` makes tmux type each line as literal characters — this is the
        # injection guard the UI's allowlist regex relies on. Do not collapse
        # this into a single send-keys call.
        lines = text.split("\n")
        for index, line in enumerate(lines):
            if line:
                if not await self._tmux_send(target, ["-l", "--", line]):
                    log.warning(
                        "tmux forward aborted mid-payload: target=%s at line %d/%d",
                        target,
                        index + 1,
                        len(lines),
                    )
                    return False
            if index < len(lines) - 1:
                if not await self._tmux_send(target, ["Enter"]):
                    log.warning(
                        "tmux forward aborted at Enter: target=%s after line %d/%d",
                        target,
                        index + 1,
                        len(lines),
                    )
                    return False
        if press_enter:
            return await self._tmux_send(target, ["Enter"])
        return True

    async def kill(self, target: Target) -> bool:
        ok = await self._run_tmux(["kill-window", "-t", target])
        # drop from the registry regardless of tmux exit so a vanished window
        # doesn't keep claiming a live target.
        for name, tgt in list(self._targets.items()):
            if tgt == target:
                del self._targets[name]
        return ok

    async def capture_output(self, target: Target, lines: int = 50) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "capture-pane",
                "-t",
                target,
                "-p",
                "-S",
                f"-{lines}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            log.warning("tmux binary not found; cannot capture %s", target)
            raise
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace"))
        return stdout.decode(errors="replace")

    async def is_alive(self, target: Target) -> bool:
        # O(1)-ish: tmux has-session returns 0 if the target window exists.
        # We can't avoid the subprocess hop, but it's a single fast call.
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "has-session",
                "-t",
                target,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        except Exception:
            return False
        try:
            await proc.communicate()
        except Exception:
            return False
        return proc.returncode == 0

    def list_targets(self) -> dict[str, Target]:
        return dict(self._targets)

    # registry mutation hook — used when an external owner (spawner) discards
    # an agent. Keeps the in-process target map in sync with the pane state.
    def forget(self, name: str) -> None:
        self._targets.pop(name, None)

    @staticmethod
    async def _run_tmux(args: list[str]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            log.warning("tmux binary not found; cannot run %s", args)
            return False
        except Exception:
            log.warning("tmux spawn failed for args=%s", args, exc_info=True)
            return False
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.warning(
                "tmux exit=%s args=%s stderr=%s",
                proc.returncode,
                args,
                stderr.decode(errors="replace").strip(),
            )
            return False
        return True

    @staticmethod
    async def _tmux_send(target: str, extra: list[str]) -> bool:
        args = ["tmux", "send-keys", "-t", target, *extra]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("tmux binary not found; cannot forward to %s", target)
            return False
        except Exception:
            log.warning(
                "tmux spawn failed for target=%s", target, exc_info=True
            )
            return False
        try:
            await proc.communicate()
        except Exception:
            log.warning(
                "tmux communicate failed for target=%s", target, exc_info=True
            )
            return False
        return proc.returncode == 0
