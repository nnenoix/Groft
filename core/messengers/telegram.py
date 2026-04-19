"""Telegram long-polling bridge.

Constructible without a running event loop so unit tests can exercise
``start()`` / ``stop()`` semantics without a real Telegram connection.
The polling coroutine (the one that hits the Bot API) is overridable via
``_polling_factory`` so tests monkeypatch it with ``asyncio.sleep(0)``.

Inbound ``/pair CODE`` captures a single user_id the first time a valid
nonce is presented. After pairing, only allowlisted user_ids are honored.

Inbound ``/ask <agent> <text>`` is the main command: ensure the role is
active (``orchestrator.spawn_role``) then forward ``<text>`` to that role's
pane via the shared ``ProcessBackend.send_text`` path — same route the WS
server uses for ``message`` frames.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from core.orchestrator import Orchestrator
    from core.process import ProcessBackend

log = logging.getLogger(__name__)

# Telegram bot tokens look like "123456789:AA-ZZ_..." — server-side format check
# before we ever hit Telegram's API. Keeps bad input out of httpx calls.
TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")


def is_valid_token_format(token: str) -> bool:
    """Cheap sanity check — real validation is a ``getMe`` round-trip."""
    return bool(TOKEN_RE.match(token or ""))


class TelegramBridge:
    """Long-polling Telegram bridge that maps ``/ask`` to a live agent.

    ``start()`` and ``stop()`` are idempotent — calling either twice is a
    no-op. The polling task is tracked on ``self._task`` so tests can observe
    lifecycle without poking internals directly.
    """

    def __init__(
        self,
        token: str,
        orchestrator: "Orchestrator",
        *,
        allowlist: set[int] | None = None,
        backend: "ProcessBackend | None" = None,
        state_path: Path | None = None,
        polling_factory: Callable[["TelegramBridge"], Awaitable[None]] | None = None,
    ) -> None:
        if not is_valid_token_format(token):
            raise ValueError("invalid telegram token format")
        self._token = token
        self._orchestrator = orchestrator
        # allowlist mutates over a pairing so we never want the caller's set
        # aliased in. Copy on construction to isolate state.
        self._allowlist: set[int] = set(allowlist or ())
        self._backend = backend
        self._state_path = state_path
        self._task: asyncio.Task[None] | None = None
        self._running = False
        # Pairing nonces live in-process; ``start_pairing`` and
        # ``accept_pairing`` mutate this dict. Values are monotonic asyncio
        # loop timestamps (seconds-since-loop-epoch) so tests can fake a
        # clock by freezing ``loop.time``.
        self._pending_pairs: dict[str, float] = {}
        # Factory hook so tests can swap the real ``run_polling`` call with a
        # trivial coroutine. Default implementation is ``_run_polling``.
        self._polling_factory = polling_factory or self._default_polling

    # -------- lifecycle --------

    async def start(self) -> None:
        """Launch the polling task. Idempotent: returns early if running."""
        if self._running:
            return
        self._running = True
        coro = self._polling_factory(self)
        # create_task so ``start()`` returns immediately; the task is the
        # poller's lifetime handle stored for ``stop()``.
        self._task = asyncio.create_task(coro, name="telegram-bridge-polling")

    async def stop(self) -> None:
        """Cancel the polling task and wait for it. Idempotent."""
        if not self._running:
            return
        self._running = False
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            # Polling internals shouldn't take down stop() — log and move on.
            log.exception("telegram bridge polling task raised on stop")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    # -------- pairing --------

    def register_pairing_code(self, code: str, ts: float) -> None:
        """Store a nonce with its creation timestamp (loop-time seconds)."""
        self._pending_pairs[code] = ts

    def accept_pairing(self, code: str, user_id: int, now: float, ttl: float = 300.0) -> bool:
        """Consume a nonce and bind ``user_id`` to the allowlist.

        Expired nonces (> ``ttl`` seconds old) are rejected and evicted.
        Unknown nonces return False. On success the code is removed and
        ``user_id`` added to the in-memory allowlist; callers should
        persist ``paired_user_id`` to disk separately if desired.
        """
        # Sweep ancient nonces on every accept attempt — cheap + avoids a
        # background timer thread.
        expired = [c for c, t in self._pending_pairs.items() if now - t > ttl]
        for c in expired:
            self._pending_pairs.pop(c, None)
        ts = self._pending_pairs.get(code)
        if ts is None:
            return False
        if now - ts > ttl:
            self._pending_pairs.pop(code, None)
            return False
        self._pending_pairs.pop(code, None)
        self._allowlist.add(user_id)
        self._persist_paired(user_id)
        return True

    @property
    def allowlist(self) -> frozenset[int]:
        return frozenset(self._allowlist)

    def _persist_paired(self, user_id: int) -> None:
        """Append paired_user_id to the state file on disk, best-effort."""
        if self._state_path is None:
            return
        path = self._state_path
        try:
            data: dict[str, Any] = {}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            data["paired_user_id"] = user_id
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # State is recoverable (re-pair) — never fail the inbound handler.
            log.warning("failed to persist paired user_id", exc_info=True)

    # -------- inbound dispatch (called by polling handlers) --------

    async def handle_ask(self, agent: str, text: str) -> bool:
        """Ensure ``agent`` is spawned and forward ``text`` to its pane.

        Returns False if the role is unknown (orchestrator.spawn_role
        rejected it) or no pane target is registered for delivery.
        Network errors during spawn propagate; callers log.
        """
        agent = (agent or "").strip()
        text = text or ""
        if not agent:
            return False
        active = self._orchestrator.active()
        if agent not in active:
            spawned = await self._orchestrator.spawn_role(agent)
            if not spawned:
                log.warning("telegram /ask: spawn_role failed for %r", agent)
                return False
        if self._backend is None:
            log.info(
                "telegram /ask: no backend wired; skipping pane forward agent=%s", agent
            )
            return False
        target = self._backend.list_targets().get(agent)
        if target is None:
            log.warning("telegram /ask: no pane target for agent=%s", agent)
            return False
        return await self._backend.send_text(target, text)

    # -------- default polling (real Telegram path) --------

    async def _default_polling(self, bridge: "TelegramBridge") -> None:
        """Real long-polling loop. Lazy-imports python-telegram-bot.

        Kept thin — test suite replaces this via ``polling_factory`` so the
        dependency never has to load during unit tests. We catch the import
        error and log + exit so a missing dep doesn't crash the server task.
        """
        try:
            # Lazy import: keeps the dep out of the import path for tests and
            # for users who never configure Telegram.
            from telegram.ext import (  # noqa: F401
                Application,
                CommandHandler,
                ContextTypes,
            )
        except Exception:
            log.exception("python-telegram-bot not importable; bridge idle")
            # Park the task so cancel semantics still work cleanly.
            try:
                while bridge._running:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return
            return

        # Full handler wiring is intentionally out of scope for this PR —
        # see architecture/current-task.md. The skeleton exists so we can
        # extend it without touching the public shape.
        try:
            while bridge._running:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return
