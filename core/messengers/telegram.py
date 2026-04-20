"""Telegram long-polling bridge.

Constructible without a running event loop so unit tests can exercise
``start()`` / ``stop()`` semantics without a real Telegram connection.
The polling coroutine (the one that hits the Bot API) is overridable via
``_polling_factory`` so tests monkeypatch it with ``asyncio.sleep(0)``.

Inbound ``/pair CODE`` captures a single user_id the first time a valid
nonce is presented. After pairing, only the paired user_id is honored.

Inbound ``/ask <agent> <text>`` is the main command: ensure the role is
active (``orchestrator.spawn_role``) then forward ``<text>`` to that role's
pane via the shared ``ProcessBackend.send_text`` path — same route the WS
server uses for ``message`` frames. When ``chat_id`` is supplied (from the
Telegram update) the bridge echoes a confirmation back to that chat.
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


def read_state_file(path: Path) -> dict[str, Any]:
    """Load persisted Telegram state from ``path``; empty dict on any error.

    Shared between the bridge (for paired_user_id persistence) and the main
    process boot hook (to decide whether to construct a bridge at all).
    Kept best-effort because the file is regenerable by re-running the
    configure flow.
    """
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("telegram state unreadable path=%s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def load_paired_user_id(path: Path) -> int | None:
    """Extract ``paired_user_id`` from the state file, or None if unset."""
    data = read_state_file(path)
    value = data.get("paired_user_id")
    return value if isinstance(value, int) else None


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
        # paired_user_id is the single operator bound via /pair. Distinct from
        # the allowlist so handlers can ask "is this the paired user?" without
        # iterating a set (and to make the on-disk surface explicit).
        # Seeded from allowlist when exactly one entry is provided so tests /
        # callers with a pre-populated allowlist still get the "paired" shape.
        self._paired_user_id: int | None = (
            next(iter(self._allowlist)) if len(self._allowlist) == 1 else None
        )
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
        # trivial coroutine. Default implementation is ``_default_polling``.
        self._polling_factory = polling_factory or self._default_polling
        # PTB Application handle, tracked here so ``stop()`` can unwind the
        # updater + application cleanly even if the polling coroutine is
        # mid-await on a stop signal.
        self._application: Any | None = None

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
        # Tear down the PTB Application first so the polling coroutine exits
        # its updater loop on its own. If the polling task is the default one
        # it will return once updater/app stop; if it's a test fake it will
        # see ``self._running == False`` and fall out of the loop.
        app = self._application
        self._application = None
        if app is not None:
            try:
                updater = getattr(app, "updater", None)
                if updater is not None and getattr(updater, "running", False):
                    await updater.stop()
            except Exception:
                log.warning("telegram bridge: updater.stop failed", exc_info=True)
            try:
                if getattr(app, "running", False):
                    await app.stop()
            except Exception:
                log.warning("telegram bridge: app.stop failed", exc_info=True)
            try:
                await app.shutdown()
            except Exception:
                log.warning("telegram bridge: app.shutdown failed", exc_info=True)
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

    @property
    def paired_user_id(self) -> int | None:
        return self._paired_user_id

    # -------- pairing --------

    def register_pairing_code(self, code: str, ts: float) -> None:
        """Store a nonce with its creation timestamp (loop-time seconds)."""
        self._pending_pairs[code] = ts

    def accept_pairing(self, code: str, user_id: int, now: float, ttl: float = 300.0) -> bool:
        """Consume a nonce and bind ``user_id`` to the allowlist.

        Expired nonces (> ``ttl`` seconds old) are rejected and evicted.
        Unknown nonces return False. On success the code is removed,
        ``user_id`` is stored as ``paired_user_id`` and appended to the
        in-memory allowlist, and the ID is persisted to disk (best-effort).
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
        self._paired_user_id = user_id
        self._allowlist.add(user_id)
        self._persist_paired(user_id)
        return True

    @property
    def allowlist(self) -> frozenset[int]:
        return frozenset(self._allowlist)

    def _persist_paired(self, user_id: int) -> None:
        """Append paired_user_id to the state file on disk, best-effort.

        Preserves any existing keys (token, username) so configure-then-pair
        leaves a single coherent file rather than clobbering on either side.
        """
        if self._state_path is None:
            return
        path = self._state_path
        try:
            data = read_state_file(path)
            data["paired_user_id"] = user_id
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # State is recoverable (re-pair) — never fail the inbound handler.
            log.warning("failed to persist paired user_id", exc_info=True)

    # -------- inbound dispatch (called by polling handlers) --------

    async def handle_ask(
        self, agent: str, text: str, *, chat_id: int | None = None
    ) -> bool:
        """Ensure ``agent`` is spawned and forward ``text`` to its pane.

        Returns False if the role is unknown (orchestrator.spawn_role
        rejected it) or no pane target is registered for delivery.
        Network errors during spawn propagate; callers log.

        When ``chat_id`` is provided, echo a brief confirmation back to the
        originating Telegram chat so the operator sees their message landed
        (or didn't). The echo is best-effort — failures are logged but never
        propagate.
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
                await self._echo(chat_id, f"[{agent}] spawn rejected")
                return False
        if self._backend is None:
            log.info(
                "telegram /ask: no backend wired; skipping pane forward agent=%s", agent
            )
            await self._echo(chat_id, f"[{agent}] no backend")
            return False
        target = self._backend.list_targets().get(agent)
        if target is None:
            log.warning("telegram /ask: no pane target for agent=%s", agent)
            await self._echo(chat_id, f"[{agent}] no pane target")
            return False
        ok = await self._backend.send_text(target, text)
        if ok:
            # First line only — the real agent response streaming is a
            # follow-up PR; for now we just acknowledge delivery.
            first_line = text.splitlines()[0] if text else ""
            await self._echo(chat_id, f"[{agent}] sent: {first_line}")
        else:
            await self._echo(chat_id, f"[{agent}] send failed")
        return ok

    async def _echo(self, chat_id: int | None, text: str) -> None:
        """Send a reply to the originating chat via PTB, if available."""
        if chat_id is None:
            return
        app = self._application
        if app is None:
            return
        bot = getattr(app, "bot", None)
        if bot is None:
            return
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            log.warning(
                "telegram echo failed chat_id=%s text=%r", chat_id, text, exc_info=True
            )

    # -------- PTB handler callbacks --------

    async def _on_pair(self, update: Any, context: Any) -> None:
        """``/pair <code>`` — bind the issuing user_id to the paired slot.

        Arg validation is liberal: any argv beyond the first is ignored;
        missing argv produces a friendly usage reply. Timestamps use the
        running loop's monotonic clock so they match the nonce source of
        truth (the REST endpoint).
        """
        args = getattr(context, "args", None) or []
        message = getattr(update, "effective_message", None) or getattr(
            update, "message", None
        )
        user = getattr(update, "effective_user", None)
        if not args:
            if message is not None:
                try:
                    await message.reply_text("Usage: /pair <code>")
                except Exception:
                    log.warning("telegram /pair usage reply failed", exc_info=True)
            return
        code = str(args[0]).strip().upper()
        user_id = getattr(user, "id", None)
        if not isinstance(user_id, int):
            return
        loop = asyncio.get_running_loop()
        ok = self.accept_pairing(code, user_id, now=loop.time())
        reply = "Paired \u2713" if ok else "Invalid/expired code"
        if message is not None:
            try:
                await message.reply_text(reply)
            except Exception:
                log.warning("telegram /pair reply failed", exc_info=True)

    async def _on_ask(self, update: Any, context: Any) -> None:
        """``/ask <agent> <text...>`` — dispatch to ``handle_ask``.

        Allowlist: only the paired user_id is accepted. Unpaired users and
        strangers are silently dropped (we don't leak existence of the bot
        via an error reply).
        """
        user = getattr(update, "effective_user", None)
        user_id = getattr(user, "id", None)
        message = getattr(update, "effective_message", None) or getattr(
            update, "message", None
        )
        chat = getattr(update, "effective_chat", None)
        chat_id = getattr(chat, "id", None)
        paired = self._paired_user_id
        if paired is None or user_id != paired:
            log.info(
                "telegram /ask: dropping unpaired user_id=%s (paired=%s)",
                user_id,
                paired,
            )
            return
        args = getattr(context, "args", None) or []
        if len(args) < 2:
            if message is not None:
                try:
                    await message.reply_text("Usage: /ask <agent> <text>")
                except Exception:
                    log.warning("telegram /ask usage reply failed", exc_info=True)
            return
        agent = str(args[0]).strip()
        text = " ".join(str(a) for a in args[1:]).strip()
        if not agent or not text:
            if message is not None:
                try:
                    await message.reply_text("Usage: /ask <agent> <text>")
                except Exception:
                    log.warning("telegram /ask usage reply failed", exc_info=True)
            return
        try:
            ok = await self.handle_ask(
                agent, text, chat_id=chat_id if isinstance(chat_id, int) else None
            )
        except Exception:
            log.exception("telegram /ask handler crashed agent=%s", agent)
            if message is not None:
                try:
                    await message.reply_text(f"[{agent}] internal error")
                except Exception:
                    log.warning("telegram /ask error reply failed", exc_info=True)
            return
        # handle_ask already echoes via _echo; the reply_text here is a
        # fallback for cases where chat_id wasn't available.
        if message is not None and chat_id is None:
            reply = f"Sent to {agent}" if ok else f"Failed to reach {agent}"
            try:
                await message.reply_text(reply)
            except Exception:
                log.warning("telegram /ask fallback reply failed", exc_info=True)

    async def _on_fallback(self, update: Any, context: Any) -> None:
        """Non-command text — remind the user what's supported."""
        message = getattr(update, "effective_message", None) or getattr(
            update, "message", None
        )
        if message is None:
            return
        try:
            await message.reply_text(
                "Use /ask <agent> <text> or /pair <code>."
            )
        except Exception:
            log.warning("telegram fallback reply failed", exc_info=True)

    # -------- default polling (real Telegram path) --------

    async def _default_polling(self, bridge: "TelegramBridge") -> None:
        """Real long-polling loop. Lazy-imports python-telegram-bot.

        Kept thin — test suite replaces this via ``polling_factory`` so the
        dependency never has to load during unit tests. We catch the import
        error and log + exit so a missing dep doesn't crash the server task.

        PTB 21+ pattern: build Application, register handlers, then run the
        explicit initialize/start/updater.start_polling triad. ``stop()``
        drives the matching teardown; we park on a Future here until then.
        """
        try:
            # Lazy import: keeps the dep out of the import path for tests and
            # for users who never configure Telegram.
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
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

        try:
            application = Application.builder().token(bridge._token).build()
        except Exception:
            log.exception("telegram Application build failed; bridge idle")
            try:
                while bridge._running:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return
            return

        application.add_handler(CommandHandler("pair", bridge._on_pair))
        application.add_handler(CommandHandler("ask", bridge._on_ask))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, bridge._on_fallback)
        )
        bridge._application = application

        try:
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
        except Exception:
            log.exception("telegram polling start failed")
            # Best-effort cleanup before exiting the task.
            try:
                await application.shutdown()
            except Exception:
                log.warning(
                    "telegram shutdown after failed start raised",
                    exc_info=True,
                )
            bridge._application = None
            return

        # Park the task until stop() is called. ``stop()`` drives the
        # updater/app teardown, which flips ``_running`` to False; we just
        # wait for that signal here. CancelledError is the graceful exit.
        try:
            while bridge._running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return


async def build_and_start_bridge(
    token: str,
    orchestrator: "Orchestrator",
    backend: "ProcessBackend | None",
    state_path: Path,
    *,
    allowlist: set[int] | None = None,
) -> "TelegramBridge | None":
    """Construct + start a bridge. Returns None on any failure (logged)."""
    if not is_valid_token_format(token):
        log.warning("build_and_start_bridge: invalid token format")
        return None
    try:
        bridge = TelegramBridge(
            token,
            orchestrator,
            allowlist=allowlist,
            backend=backend,
            state_path=state_path,
        )
    except ValueError:
        log.warning("build_and_start_bridge: token rejected as malformed")
        return None
    except Exception:
        log.exception("build_and_start_bridge: construction failed")
        return None
    try:
        await bridge.start()
    except Exception:
        log.exception("build_and_start_bridge: start failed")
        return None
    return bridge
