from __future__ import annotations

import asyncio
import signal
import threading
from typing import Awaitable, Callable

_CONFIRM_PROMPT = "Агенты работают. Уверен что хочешь остановить? (y/n) "
_STOP_SIGNALS: tuple[int, ...] = tuple(
    s for s in (
        getattr(signal, "SIGINT", None),
        getattr(signal, "SIGTERM", None),
        # SIGHUP is POSIX-only; absent on Windows
        getattr(signal, "SIGHUP", None),
    )
    if s is not None
)


class ProcessGuard:
    def __init__(self) -> None:
        self._agents: set[str] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._installed_signals: list[int] = []
        self._shutdown_event: asyncio.Event | None = None
        self._stopped_future: asyncio.Future[None] | None = None
        self._checkpoint_cb: Callable[[], Awaitable[None]] | None = None
        self._agent_stop_cb: Callable[[], Awaitable[None]] | None = None
        self._confirming: bool = False

    def install(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if loop is None:
            loop = asyncio.get_running_loop()
        self._loop = loop
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        if self._stopped_future is None or self._stopped_future.done():
            self._stopped_future = loop.create_future()
        for sig in _STOP_SIGNALS:
            try:
                loop.add_signal_handler(sig, self._on_signal, sig)
                self._installed_signals.append(sig)
            except NotImplementedError:
                continue

    def uninstall(self) -> None:
        if self._loop is None:
            return
        for sig in self._installed_signals:
            try:
                self._loop.remove_signal_handler(sig)
            except (NotImplementedError, ValueError):
                continue
        self._installed_signals.clear()

    def register_agent(self, name: str) -> None:
        with self._lock:
            self._agents.add(name)

    def unregister_agent(self, name: str) -> None:
        with self._lock:
            self._agents.discard(name)

    def has_active_agents(self) -> bool:
        with self._lock:
            return bool(self._agents)

    def set_checkpoint_callback(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._checkpoint_cb = fn

    def set_agent_stop_callback(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._agent_stop_cb = fn

    async def wait_for_stop(self) -> None:
        if self._stopped_future is None:
            raise RuntimeError("ProcessGuard not installed")
        await asyncio.shield(self._stopped_future)

    @property
    def shutdown_event(self) -> asyncio.Event:
        if self._shutdown_event is None:
            raise RuntimeError("ProcessGuard not installed")
        return self._shutdown_event

    def _on_signal(self, signum: int) -> None:
        if self._loop is None:
            return
        self._loop.create_task(self._handle_signal(signum))

    async def _handle_signal(self, signum: int) -> None:
        # re-entry guard: a second Ctrl-C while prompting must not stack prompts
        if self._confirming:
            return
        if self.has_active_agents():
            self._confirming = True
            try:
                assert self._loop is not None
                answer = await self._loop.run_in_executor(None, self._read_confirmation)
            except (EOFError, KeyboardInterrupt):
                answer = ""
            finally:
                self._confirming = False
            if answer.strip().lower() != "y":
                return
        await self._shutdown()

    @staticmethod
    def _read_confirmation() -> str:
        try:
            return input(_CONFIRM_PROMPT)
        except EOFError:
            return ""

    async def _shutdown(self) -> None:
        if self._checkpoint_cb is not None:
            await self._checkpoint_cb()
        if self._agent_stop_cb is not None:
            await self._agent_stop_cb()
        else:
            with self._lock:
                self._agents.clear()
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        if self._stopped_future is not None and not self._stopped_future.done():
            self._stopped_future.set_result(None)
