from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal

Status = Literal["active", "possibly_stuck", "stuck", "restarting"]


@dataclass
class AgentState:
    name: str
    tmux_target: str
    last_output: str = ""
    last_change_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: Status = "active"
    wake_fired: bool = False
    restart_fired: bool = False
    notification_fired: bool = False


class AgentWatchdog:
    def __init__(
        self,
        poll_interval: float = 5.0,
        possibly_stuck_after: float = 180.0,
        stuck_after: float = 300.0,
    ) -> None:
        self._poll_interval = poll_interval
        self._possibly_stuck_after = possibly_stuck_after
        self._stuck_after = stuck_after
        self._agents: dict[str, AgentState] = {}
        self._lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None
        self._wake_cb: Callable[[str], Awaitable[None]] | None = None
        self._restart_cb: Callable[[str], Awaitable[None]] | None = None
        self._notify_cb: Callable[[str], Awaitable[None]] | None = None

    def register_agent(self, name: str, tmux_target: str) -> None:
        with self._lock:
            self._agents[name] = AgentState(name=name, tmux_target=tmux_target)

    def unregister_agent(self, name: str) -> None:
        with self._lock:
            self._agents.pop(name, None)

    def set_wake_up_callback(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._wake_cb = fn

    def set_restart_callback(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._restart_cb = fn

    def set_notification_callback(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._notify_cb = fn

    def get_state(self, name: str) -> AgentState | None:
        with self._lock:
            return self._agents.get(name)

    async def get_snapshot(self, name: str) -> str:
        with self._lock:
            state = self._agents.get(name)
            target = state.tmux_target if state is not None else None
        if target is None:
            raise KeyError(name)
        return await self._capture(target)

    async def start(self) -> None:
        # idempotent: re-entry must not spawn a second monitor
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            with self._lock:
                items = [(s.name, s.tmux_target) for s in self._agents.values()]
            if not items:
                continue
            results = await asyncio.gather(
                *(self._capture(t) for _, t in items), return_exceptions=True
            )
            now = datetime.now(timezone.utc)
            for (name, _), result in zip(items, results):
                if isinstance(result, BaseException):
                    continue
                await self._process(name, result, now)

    async def _process(self, name: str, output: str, now: datetime) -> None:
        with self._lock:
            state = self._agents.get(name)
            if state is None:
                return
            if output != state.last_output:
                state.last_output = output
                state.last_change_time = now
                state.status = "active"
                state.wake_fired = False
                state.restart_fired = False
                state.notification_fired = False
                return
            elapsed = (now - state.last_change_time).total_seconds()
            fire_wake = False
            fire_restart = False
            fire_notify = False
            if state.status == "restarting":
                if elapsed >= self._stuck_after and not state.notification_fired:
                    state.notification_fired = True
                    fire_notify = True
            else:
                if elapsed >= self._stuck_after and not state.restart_fired:
                    state.status = "restarting"
                    state.restart_fired = True
                    # reset timer so the restart gets its own grace window
                    state.last_change_time = now
                    fire_restart = True
                elif elapsed >= self._possibly_stuck_after and not state.wake_fired:
                    state.status = "possibly_stuck"
                    state.wake_fired = True
                    fire_wake = True

        if fire_wake and self._wake_cb is not None:
            try:
                await self._wake_cb(name)
            except Exception:
                pass
        if fire_restart and self._restart_cb is not None:
            try:
                await self._restart_cb(name)
            except Exception:
                pass
        if fire_notify and self._notify_cb is not None:
            try:
                await self._notify_cb(name)
            except Exception:
                pass

    @staticmethod
    async def _capture(target: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "capture-pane",
            "-t",
            target,
            "-p",
            "-S",
            "-50",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace"))
        return stdout.decode(errors="replace")
