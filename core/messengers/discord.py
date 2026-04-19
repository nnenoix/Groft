"""Discord gateway bridge.

Modeled on ``core/messengers/telegram.py``: a Discord bot connects via
``discord.py``'s gateway, registers two slash commands — ``/pair`` and
``/ask`` — and routes ``/ask`` inbound to ``orchestrator.spawn_role`` +
``ProcessBackend.send_text``.

Pairing uses the same short-lived (5 min) single-use nonce pattern as
Telegram: the UI asks for a code, the operator invokes ``/pair <code>``
in the server where the bot lives, and the bridge binds the Discord
``user.id`` to the paired slot. Only the paired user is honored by
``/ask`` afterwards — strangers get a silent deferred ack so the bot
doesn't leak its existence.

The constructor does NOT touch the gateway; it just validates the token
shape + seeds state. ``start()`` builds a ``discord.Client`` with default
intents (sufficient for slash commands — no ``message_content`` needed),
wires an ``app_commands.CommandTree``, syncs commands globally, and
launches ``client.start(token)`` as a background task. ``stop()`` calls
``client.close()`` and awaits the task.

Note on slash-command propagation: ``tree.sync()`` with no ``guild``
argument registers commands globally, which Discord propagates across
the user's client caches within a few minutes. For faster iteration
during development, pass ``sync_guild_id`` so ``tree.sync(guild=...)``
hits a single guild and shows up instantly.
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

# Discord bot tokens are three base64url segments separated by dots:
# <bot_id>.<timestamp>.<hmac>. The exact lengths vary between tokens
# (especially the middle segment), so we match a conservative shape rather
# than hard-coded widths. Identical regex to the UI-side DISCORD_TOKEN_RE
# so client + server agree on what's "well-formed".
TOKEN_RE = re.compile(
    r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$"
)


def is_valid_token_format(token: str) -> bool:
    """Cheap sanity check — unlike Telegram, we can't cheaply ``getMe``
    here (discord.py's probe requires an actual gateway connect)."""
    return bool(TOKEN_RE.match(token or ""))


def read_state_file(path: Path) -> dict[str, Any]:
    """Load persisted Discord state from ``path``; empty dict on any error.

    Shared between the bridge (for paired_user_id persistence) and the
    main process boot hook (to decide whether to construct a bridge at
    all). Best-effort because the file is regenerable by re-running the
    configure flow.
    """
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("discord state unreadable path=%s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def load_paired_user_id(path: Path) -> int | None:
    """Extract ``paired_user_id`` from the state file, or None if unset."""
    data = read_state_file(path)
    value = data.get("paired_user_id")
    return value if isinstance(value, int) else None


class DiscordBridge:
    """Discord gateway bridge mapping ``/ask`` slash-commands to live agents.

    ``start()`` and ``stop()`` are idempotent — calling either twice is
    a no-op. The gateway task is tracked on ``self._task`` so tests can
    observe lifecycle without poking internals directly.
    """

    def __init__(
        self,
        token: str,
        orchestrator: "Orchestrator",
        *,
        allowlist: set[int] | None = None,
        backend: "ProcessBackend | None" = None,
        state_path: Path | None = None,
        client_factory: Callable[["DiscordBridge"], Awaitable[None]] | None = None,
        sync_guild_id: int | None = None,
    ) -> None:
        if not is_valid_token_format(token):
            raise ValueError("invalid discord token format")
        self._token = token
        self._orchestrator = orchestrator
        # Copy on construction so the caller's set isn't aliased into
        # mutable bridge state (same pattern as TelegramBridge).
        self._allowlist: set[int] = set(allowlist or ())
        # paired_user_id seeded from a single-entry allowlist so callers
        # that pre-populate from on-disk state end up in the "paired"
        # shape without an extra handshake.
        self._paired_user_id: int | None = (
            next(iter(self._allowlist)) if len(self._allowlist) == 1 else None
        )
        self._backend = backend
        self._state_path = state_path
        self._task: asyncio.Task[None] | None = None
        self._running = False
        # Pairing nonces live in-process here too so the bridge can
        # enforce TTL without a shared store; the REST endpoint keeps its
        # own copy for the issue path (see communication/server.py).
        self._pending_pairs: dict[str, float] = {}
        # Test hook: swap the real gateway connect for a trivial coroutine
        # that awaits a cancel. Default implementation is
        # ``_default_gateway``.
        self._client_factory = client_factory or self._default_gateway
        # discord.Client handle, tracked so ``stop()`` can call its close()
        # even if the gateway coroutine is mid-await on a stop signal.
        self._client: Any | None = None
        # When set, ``tree.sync(guild=...)`` targets that guild for fast
        # propagation — global sync is the default but can take minutes.
        self._sync_guild_id = sync_guild_id
        # Cached bot user info (populated on ready) so /status can surface
        # "who am I" without the operator guessing from the client ID.
        self._bot_user: str | None = None

    # -------- lifecycle --------

    async def start(self) -> None:
        """Launch the gateway task. Idempotent: returns early if running."""
        if self._running:
            return
        self._running = True
        coro = self._client_factory(self)
        self._task = asyncio.create_task(coro, name="discord-bridge-gateway")

    async def stop(self) -> None:
        """Close the client and wait for the gateway task. Idempotent."""
        if not self._running:
            return
        self._running = False
        client = self._client
        self._client = None
        if client is not None:
            try:
                close = getattr(client, "close", None)
                if callable(close):
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception:
                log.warning("discord bridge: client.close failed", exc_info=True)
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
            log.exception("discord bridge gateway task raised on stop")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    @property
    def paired_user_id(self) -> int | None:
        return self._paired_user_id

    @property
    def bot_user(self) -> str | None:
        return self._bot_user

    # -------- pairing --------

    def register_pairing_code(self, code: str, ts: float) -> None:
        """Store a nonce with its creation timestamp (loop-time seconds)."""
        self._pending_pairs[code] = ts

    def accept_pairing(
        self, code: str, user_id: int, now: float, ttl: float = 300.0
    ) -> bool:
        """Consume a nonce and bind ``user_id`` to the allowlist.

        Identical semantics to ``TelegramBridge.accept_pairing``: expired
        nonces are evicted, unknown nonces return False, and on success
        the code is consumed (no replay) and persisted to disk best-effort.
        """
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

        Preserves token/bot_user keys so pairing after configure leaves a
        single coherent file rather than clobbering half of it.
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
            log.warning("failed to persist paired user_id", exc_info=True)

    # -------- inbound dispatch --------

    async def handle_ask(
        self, agent: str, text: str, *, channel_id: int | None = None
    ) -> bool:
        """Ensure ``agent`` is spawned and forward ``text`` to its pane.

        Same shape as ``TelegramBridge.handle_ask`` — the only difference
        is the echo surface (Discord channel vs Telegram chat). ``channel_id``
        is stored for documentation but we don't use it directly here —
        the slash-command handler responds via the interaction object,
        which is the canonical reply path on Discord.
        """
        agent = (agent or "").strip()
        text = text or ""
        if not agent:
            return False
        active = self._orchestrator.active()
        if agent not in active:
            spawned = await self._orchestrator.spawn_role(agent)
            if not spawned:
                log.warning("discord /ask: spawn_role failed for %r", agent)
                return False
        if self._backend is None:
            log.info(
                "discord /ask: no backend wired; skipping pane forward agent=%s",
                agent,
            )
            return False
        target = self._backend.list_targets().get(agent)
        if target is None:
            log.warning("discord /ask: no pane target for agent=%s", agent)
            return False
        ok = await self._backend.send_text(target, text)
        return ok

    def first_line(self, text: str) -> str:
        """Echo helper — extract the first line for a friendly ack."""
        return text.splitlines()[0] if text else ""

    # -------- slash command callbacks --------

    async def _on_pair(self, interaction: Any, code: str) -> None:
        """``/pair code:<string>`` — bind the invoking user_id.

        ``interaction`` is duck-typed so tests can pass a minimal stand-in
        without installing the full discord.py Interaction surface. On
        real traffic it's a ``discord.Interaction`` instance.
        """
        normalised = (code or "").strip().upper()
        user = getattr(interaction, "user", None)
        user_id = getattr(user, "id", None)
        response = getattr(interaction, "response", None)
        send = getattr(response, "send_message", None) if response else None
        if not isinstance(user_id, int):
            return
        if not normalised:
            if callable(send):
                try:
                    await send("Usage: /pair <code>", ephemeral=True)
                except Exception:
                    log.warning(
                        "discord /pair usage reply failed", exc_info=True
                    )
            return
        loop = asyncio.get_running_loop()
        ok = self.accept_pairing(normalised, user_id, now=loop.time())
        reply = "Paired \u2713" if ok else "Invalid/expired code"
        if callable(send):
            try:
                await send(reply, ephemeral=True)
            except Exception:
                log.warning("discord /pair reply failed", exc_info=True)

    async def _on_ask(
        self, interaction: Any, agent: str, text: str
    ) -> None:
        """``/ask agent:<string> text:<string>`` — dispatch to handle_ask.

        Allowlist: only the paired user_id is honored. For strangers we
        silently defer the interaction (Discord requires *some* ack or
        the client shows "The application did not respond") — but the
        defer is ephemeral and empty so the bot's existence isn't leaked.
        """
        user = getattr(interaction, "user", None)
        user_id = getattr(user, "id", None)
        response = getattr(interaction, "response", None)
        channel = getattr(interaction, "channel", None)
        channel_id = getattr(channel, "id", None)
        paired = self._paired_user_id
        if paired is None or user_id != paired:
            log.info(
                "discord /ask: dropping unpaired user_id=%s (paired=%s)",
                user_id,
                paired,
            )
            # Silent ephemeral defer so the client doesn't complain but
            # the stranger gets no meaningful response.
            defer = getattr(response, "defer", None)
            if callable(defer):
                try:
                    await defer(ephemeral=True)
                except Exception:
                    log.debug(
                        "discord /ask silent defer failed", exc_info=True
                    )
            return
        agent_clean = (agent or "").strip()
        text_clean = (text or "").strip()
        send = getattr(response, "send_message", None)
        if not agent_clean or not text_clean:
            if callable(send):
                try:
                    await send(
                        "Usage: /ask <agent> <text>", ephemeral=True
                    )
                except Exception:
                    log.warning(
                        "discord /ask usage reply failed", exc_info=True
                    )
            return
        try:
            ok = await self.handle_ask(
                agent_clean,
                text_clean,
                channel_id=channel_id if isinstance(channel_id, int) else None,
            )
        except Exception:
            log.exception("discord /ask handler crashed agent=%s", agent_clean)
            if callable(send):
                try:
                    await send(
                        f"[{agent_clean}] internal error", ephemeral=True
                    )
                except Exception:
                    log.warning(
                        "discord /ask error reply failed", exc_info=True
                    )
            return
        first_line = self.first_line(text_clean)
        reply = (
            f"[{agent_clean}] sent: {first_line}"
            if ok
            else f"[{agent_clean}] send failed"
        )
        if callable(send):
            try:
                await send(reply, ephemeral=True)
            except Exception:
                log.warning("discord /ask reply failed", exc_info=True)

    # -------- default gateway (real Discord path) --------

    async def _default_gateway(self, bridge: "DiscordBridge") -> None:
        """Real discord.py gateway loop. Lazy-imports discord.

        Kept thin — test suite replaces this via ``client_factory`` so
        discord.py never has to load during unit tests. A missing dep
        collapses to a warning so the orchestrator keeps booting.

        discord.py 2.x pattern: build ``Client`` with default intents,
        attach a ``CommandTree``, register commands, call ``client.start()``.
        The ``on_ready`` handler syncs commands once (they propagate in
        the background) and captures the bot user name for /status.
        """
        try:
            import discord
            from discord import app_commands
        except Exception:
            log.exception("discord.py not importable; bridge idle")
            try:
                while bridge._running:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return
            return

        try:
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)
        except Exception:
            log.exception("discord Client build failed; bridge idle")
            try:
                while bridge._running:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return
            return

        tree = app_commands.CommandTree(client)

        # app_commands decorator-based registration is the ergonomic
        # surface; describe= keyword sets the in-client tooltip.
        @tree.command(name="pair", description="Pair this Discord user with Groft")
        @app_commands.describe(code="Pairing code issued by the Groft UI")
        async def _pair_cmd(interaction: Any, code: str) -> None:
            await bridge._on_pair(interaction, code)

        @tree.command(name="ask", description="Send text to a Groft agent")
        @app_commands.describe(
            agent="Agent role name (e.g. backend-dev)",
            text="Text to forward to the agent's pane",
        )
        async def _ask_cmd(interaction: Any, agent: str, text: str) -> None:
            await bridge._on_ask(interaction, agent, text)

        @client.event
        async def on_ready() -> None:
            try:
                user = getattr(client, "user", None)
                bridge._bot_user = str(user) if user is not None else None
                if bridge._sync_guild_id is not None:
                    guild = discord.Object(id=bridge._sync_guild_id)
                    await tree.sync(guild=guild)
                else:
                    await tree.sync()
            except Exception:
                log.warning(
                    "discord tree.sync failed (commands may not appear)",
                    exc_info=True,
                )

        bridge._client = client

        try:
            await client.start(bridge._token)
        except Exception:
            log.exception("discord client start failed")
            try:
                await client.close()
            except Exception:
                log.debug(
                    "discord close after failed start raised", exc_info=True
                )
            bridge._client = None
            return
