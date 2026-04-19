"""Windows-native ProcessBackend.

Implements `ProcessBackend` via `subprocess.Popen` with CREATE_NEW_CONSOLE
so each agent gets its own visible console window (the Windows equivalent of
a tmux pane) — good for interactive debugging. stdout/stderr are duplicated
to `.claudeorch/panes/<agent>.log` so `capture_output` can tail the file
without scraping the console buffer.

Import-safety contract
----------------------
This module MUST be importable on Linux. `subprocess.CREATE_NEW_CONSOLE`
and `subprocess.CREATE_NEW_PROCESS_GROUP` only exist on Windows, so we
resolve them through `getattr(subprocess, ..., 0)`. On POSIX the flags
collapse to 0 which is a no-op — the backend is only *used* on Windows
(the factory picks `TmuxBackend` on POSIX), but unit tests still need to
import the module to run on Linux CI.

Known limitations
-----------------
The `claude` CLI expects a TTY on its stdin. A bare `Popen(..., stdin=PIPE)`
provides a pipe, not a pty — some interactive prompts may not render
correctly and some TUI features may degrade. If a future use case needs a
real PTY on Windows, the path is `pywinpty` behind a config flag (e.g.
`process.windows.use_pty: true`) — out of scope for this PR.

Security note
-------------
`send_text` writes raw bytes to `proc.stdin`. There is no shell in the path
so the tmux-specific `-l --` literal-typing guard is not needed here. The
injection surface is the child process itself, not the OS shell.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Mapping

from core.process.backend import Target

log = logging.getLogger(__name__)

# Resolve Windows-only creation flags via getattr so this module imports on
# POSIX. `0` is a valid (no-op) creationflags value on Windows too.
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class WindowsBackend:
    def __init__(self, log_dir: Path | None = None) -> None:
        # log_dir override is handy for tests; production path is relative to
        # cwd so it lands next to `.claudeorch/` where checkpoints live.
        self._log_dir: Path = log_dir or Path(".claudeorch") / "panes"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        # name -> (Popen, log_path, log_fh). log_fh is kept open so we can
        # close it cleanly in kill(); the child writes into it via stdout.
        self._procs: dict[str, tuple[subprocess.Popen, Path, "object"]] = {}
        self._targets: dict[str, Target] = {}

    async def spawn(
        self,
        name: str,
        cmd: list[str],
        env: Mapping[str, str] | None = None,
    ) -> Target | None:
        return await asyncio.to_thread(self._spawn_sync, name, cmd, env)

    def _spawn_sync(
        self,
        name: str,
        cmd: list[str],
        env: Mapping[str, str] | None,
    ) -> Target | None:
        log_path = self._log_dir / f"{name}.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # unbuffered binary write — child writes via OS pipe so Python-side
            # buffering would only delay log availability to capture_output.
            log_fh = open(log_path, "wb", buffering=0)
        except OSError:
            log.warning("cannot open log file %s for agent=%s", log_path, name, exc_info=True)
            return None

        merged_env = {**os.environ, **(dict(env) if env else {})}
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=merged_env,
                creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP,
            )
        except (FileNotFoundError, OSError):
            log.warning("Popen failed for agent=%s cmd=%s", name, cmd, exc_info=True)
            try:
                log_fh.close()
            except Exception:
                pass
            return None

        target = f"pid:{proc.pid}"
        self._procs[name] = (proc, log_path, log_fh)
        self._targets[name] = target
        return target

    async def send_text(
        self,
        target: Target,
        text: str,
        *,
        press_enter: bool = True,
    ) -> bool:
        return await asyncio.to_thread(self._send_text_sync, target, text, press_enter)

    def _send_text_sync(self, target: Target, text: str, press_enter: bool) -> bool:
        entry = self._find_entry(target)
        if entry is None:
            log.warning("send_text: unknown target=%s", target)
            return False
        proc, _log_path, _log_fh = entry

        # Windows convention: stdin pipes are NOT auto-translated to CRLF (that
        # only happens on text-mode TTY). Since we opened stdin as PIPE/bytes,
        # translate every bare LF to CRLF so the child sees proper Windows
        # line endings. \r\n stays \r\n (the replace targets bare \n only
        # through a two-pass: normalise \r\n to \n, then expand \n to \r\n).
        normalised = text.replace("\r\n", "\n")
        payload = normalised.replace("\n", "\r\n")
        if press_enter and not text.endswith("\n"):
            payload += "\r\n"

        try:
            assert proc.stdin is not None  # spawn opens stdin=PIPE, should never be None
            proc.stdin.write(payload.encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            log.warning("send_text failed target=%s", target, exc_info=True)
            return False
        return True

    async def kill(self, target: Target) -> bool:
        return await asyncio.to_thread(self._kill_sync, target)

    def _kill_sync(self, target: Target) -> bool:
        entry_name = self._find_name(target)
        if entry_name is None:
            return False
        proc, _log_path, log_fh = self._procs[entry_name]

        # terminate() maps to TerminateProcess on Windows — clean-ish for
        # console apps; we still follow up with taskkill /T /F to nuke the
        # process tree (claude.exe spawns node.exe workers that terminate()
        # alone would orphan).
        try:
            proc.terminate()
        except Exception:
            log.warning("terminate failed pid=%s", proc.pid, exc_info=True)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log.warning("terminate timeout; escalating to kill pid=%s", proc.pid)
            try:
                proc.kill()
            except Exception:
                log.warning("kill failed pid=%s", proc.pid, exc_info=True)
        except Exception:
            log.warning("wait failed pid=%s", proc.pid, exc_info=True)

        # Insurance pass: grandchildren (node.exe workers, browser processes)
        # survive TerminateProcess of the parent. taskkill /T walks the tree.
        # Non-fatal — the process might already be fully dead.
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        except Exception:
            # taskkill absent (non-Windows test host) or blocked — ignore.
            pass

        try:
            log_fh.close()
        except Exception:
            pass

        del self._procs[entry_name]
        self._targets.pop(entry_name, None)
        return True

    async def capture_output(self, target: Target, lines: int = 50) -> str:
        return await asyncio.to_thread(self._capture_output_sync, target, lines)

    def _capture_output_sync(self, target: Target, lines: int) -> str:
        entry = self._find_entry(target)
        if entry is None:
            return ""
        _proc, log_path, _log_fh = entry
        if not log_path.exists():
            return ""
        # tail ~64KB — enough headroom for 50 lines of typical agent output,
        # cheap enough on disk that we don't need an incremental buffer.
        try:
            with open(log_path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                read_from = max(0, size - 64 * 1024)
                fh.seek(read_from, os.SEEK_SET)
                data = fh.read()
        except OSError:
            log.warning("capture_output read failed target=%s", target, exc_info=True)
            return ""
        if not data:
            return ""
        text = data.decode("utf-8", errors="replace")
        # Windows apps mix CRLF and bare LF (e.g. a Node.js child pipe).
        # Normalise before splitting so we don't emit empty lines on \r\n.
        text = text.replace("\r\n", "\n")
        split_lines = text.split("\n")
        tail = split_lines[-lines:] if lines > 0 else split_lines
        return "\n".join(tail)

    async def is_alive(self, target: Target) -> bool:
        entry = self._find_entry(target)
        if entry is None:
            return False
        proc, _log_path, _log_fh = entry
        return proc.poll() is None

    def list_targets(self) -> dict[str, Target]:
        # Purge entries whose process died since the last call — otherwise
        # watchdog sees a stale Target and the UI shows a phantom "stuck"
        # badge for a process that's already gone.
        for name in list(self._procs.keys()):
            proc, _log_path, log_fh = self._procs[name]
            if proc.poll() is not None:
                try:
                    log_fh.close()
                except Exception:
                    pass
                del self._procs[name]
                self._targets.pop(name, None)
        return dict(self._targets)

    # registry mutation hook — mirrors TmuxBackend.forget so the spawner
    # despawn path can drop a name without going through kill().
    def forget(self, name: str) -> None:
        self._procs.pop(name, None)
        self._targets.pop(name, None)

    async def shutdown(self) -> None:
        """Kill every live target. Called from orchestrator teardown so we
        don't leak console windows / node.exe grandchildren on exit.
        """
        for name in list(self._procs.keys()):
            target = self._targets.get(name)
            if target is None:
                continue
            try:
                await self.kill(target)
            except Exception:
                log.exception("shutdown kill failed agent=%s", name)

    # --- private helpers -------------------------------------------------

    def _find_name(self, target: Target) -> str | None:
        for name, tgt in self._targets.items():
            if tgt == target:
                return name
        return None

    def _find_entry(
        self, target: Target
    ) -> tuple[subprocess.Popen, Path, "object"] | None:
        name = self._find_name(target)
        if name is None:
            return None
        return self._procs.get(name)
