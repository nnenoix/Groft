from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import duckdb
import uvicorn
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol

from communication.task_parser import parse_tasks_dir
from core.paths import claudeorch_dir, memory_archive_dir, memory_dir
from core.process import ProcessBackend

if TYPE_CHECKING:
    # imported lazily to sidestep any future core<->communication cycle
    from core.orchestrator import Orchestrator

log = logging.getLogger(__name__)
# snapshots forward to this agent name when connected; chosen per spec ("opus" is orchestrator)
SNAPSHOT_SINK_AGENT = "opus"
# UI client (viewer) receives parallel forwards of snapshot+status; silent skip if not connected
UI_SINK_AGENT = "ui"

# Telegram pairing nonce lifetime (seconds). 5 minutes matches typical 2FA UX
# and is short enough that a leaked code has limited blast radius.
TELEGRAM_PAIR_TTL = 300.0
# Alphabet for pairing codes — digits + uppercase letters, minus easily
# confused glyphs (0/O, 1/I). 6 chars = ~32 bits of entropy, enough to resist
# accidental guesses over a 5-minute window.
_TELEGRAM_PAIR_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
TELEGRAM_PAIR_CODE_LEN = 6
# Bot token wire format validation — same regex as TelegramBridge uses
# internally so bad input never reaches the Telegram API.
_TELEGRAM_TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")

# Discord pairing constants mirror the Telegram ones — same 5-min TTL and
# 6-char uppercase alnum nonce. Stored in a separate in-memory dict so
# Telegram and Discord codes never cross-leak across messengers.
DISCORD_PAIR_TTL = 300.0
DISCORD_PAIR_CODE_LEN = 6
_DISCORD_PAIR_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
# Discord bot tokens match the same shape as the UI-side DISCORD_TOKEN_RE
# and DiscordBridge.TOKEN_RE: three base64url segments separated by dots.
_DISCORD_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$"
)


def _generate_discord_pair_code() -> str:
    """Cryptographically-strong Discord pairing nonce.

    Same 6-char alphabet as the Telegram flow so the operator's muscle
    memory is identical across channels.
    """
    import secrets

    return "".join(
        secrets.choice(_DISCORD_PAIR_ALPHABET) for _ in range(DISCORD_PAIR_CODE_LEN)
    )


def _discord_state_path() -> Path:
    """On-disk home for persisted Discord config. Parent is auto-created."""
    return claudeorch_dir() / "messenger-discord.json"


def _read_discord_state() -> dict[str, Any]:
    """Load persisted Discord state; empty dict on missing/malformed file."""
    path = _discord_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("messenger-discord.json unreadable", exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _write_discord_state(data: dict[str, Any]) -> None:
    """Persist Discord config. Parent dir via claudeorch_dir."""
    path = _discord_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _monotonic_now() -> float:
    """Default clock source for pairing timestamps. Monotonic so clock skew
    can't expire a freshly created nonce."""
    import time

    return time.monotonic()


def _generate_pair_code() -> str:
    """Cryptographically-strong pairing nonce from a reduced alphabet."""
    import secrets

    return "".join(
        secrets.choice(_TELEGRAM_PAIR_ALPHABET) for _ in range(TELEGRAM_PAIR_CODE_LEN)
    )


def _telegram_state_path() -> Path:
    """On-disk home for persisted Telegram config. Parent is auto-created."""
    return claudeorch_dir() / "messenger-telegram.json"


def _webhook_state_path() -> Path:
    """On-disk home for persisted webhook config. Sibling of telegram state."""
    return claudeorch_dir() / "messenger-webhook.json"


def _read_webhook_state() -> dict[str, Any]:
    """Load persisted webhook state; empty dict on missing/malformed file."""
    path = _webhook_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("messenger-webhook.json unreadable", exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _write_webhook_state(data: dict[str, Any]) -> None:
    """Persist webhook config. Parent dir is auto-created."""
    path = _webhook_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_telegram_state() -> dict[str, Any]:
    """Load persisted Telegram state; empty dict on missing/malformed file."""
    path = _telegram_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("messenger-telegram.json unreadable", exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _write_telegram_state(data: dict[str, Any]) -> None:
    """Atomic-ish write — we tolerate partial writes because the file is
    regenerable (user re-runs configure/pair). Parent dir via claudeorch_dir."""
    path = _telegram_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT,
    timestamp TIMESTAMP,
    msg_from TEXT,
    msg_to TEXT,
    msg_type TEXT,
    content TEXT
);
CREATE SEQUENCE IF NOT EXISTS messages_id_seq;
"""


class CommunicationServer:
    def __init__(
        self,
        ws_host: str = "localhost",
        ws_port: int = 8765,
        rest_host: str = "localhost",
        rest_port: int = 8766,
        db_path: Path | str | None = None,
        backend: ProcessBackend | None = None,
        lead_target: str | None = None,
        tasks_dir: Path | str | None = None,
        orchestrator: "Orchestrator | None" = None,
    ) -> None:
        self._ws_host = ws_host
        self._ws_port = ws_port
        self._rest_host = rest_host
        self._rest_port = rest_port
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else claudeorch_dir() / "messages.duckdb"
        )
        # backend is optional so unit tests can construct a server without
        # process plumbing — message-forward to panes degrades to a no-op.
        self._backend: ProcessBackend | None = backend
        # lead_target is the fallback pane address for messages whose recipient
        # has no dedicated target registered with the backend (e.g. /spawn arrives
        # for opus before any worker exists).
        self._lead_target = lead_target
        self._tasks_dir: Path | None = Path(tasks_dir) if tasks_dir is not None else None
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()
        self._registry: dict[str, WebSocketServerProtocol] = {}
        self._status: dict[str, str] = {}
        # sync lock guards registry for cross-thread reads (get_connected_agents)
        self._lock = threading.Lock()
        self._ws_server: websockets.WebSocketServer | None = None
        self._uvicorn_server: uvicorn.Server | None = None
        self._uvicorn_task: asyncio.Task[None] | None = None
        # strong refs to fire-and-forget tasks so CPython can't GC them mid-run
        self._background_tasks: set[asyncio.Task[Any]] = set()
        # captured at start() so _unregister can trampoline back to the server
        # loop via call_soon_threadsafe when invoked from a non-loop thread.
        self._loop: asyncio.AbstractEventLoop | None = None
        # invoked by POST /shutdown; wired by core/main.py to
        # ProcessGuard.request_shutdown so the Tauri window close path hits
        # the same teardown as SIGTERM.
        self._shutdown_callback: Callable[[], Awaitable[None]] | None = None
        self._usage_task: asyncio.Task[None] | None = None
        self._started = False
        # Telegram pairing nonces live in-process: {code: loop-time-seconds}.
        # TTL is enforced on consume (see TELEGRAM_PAIR_TTL). Lost on restart
        # by design — operator just requests a fresh code from the UI.
        self._telegram_pairs: dict[str, float] = {}
        # monkeypatchable clock source so tests can fast-forward without sleeps.
        self._telegram_clock: Callable[[], float] = _monotonic_now
        # Discord pairing nonces — separate dict so Telegram and Discord
        # codes never cross-leak. Same TTL + clock indirection pattern.
        self._discord_pairs: dict[str, float] = {}
        self._discord_clock: Callable[[], float] = _monotonic_now
        # orchestrator is optional so unit tests (and the shutdown-only path)
        # can construct a server without the full spawner graph. Endpoints
        # that depend on it return 503 when it's None.
        self._orchestrator: "Orchestrator | None" = orchestrator
        # FastAPI app is built eagerly so tests can hit it via ASGI transport
        # without binding ports through uvicorn.
        self._rest_app: FastAPI = self._build_app()

    async def start(self) -> None:
        # idempotent: repeat calls are a no-op so orchestrator can retry safely
        if self._started:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)
        self._ws_server = await websockets.serve(
            self._handle_connection, self._ws_host, self._ws_port
        )
        config = uvicorn.Config(
            self._rest_app,
            host=self._rest_host,
            port=self._rest_port,
            log_level="warning",
            lifespan="off",
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._uvicorn_task = asyncio.create_task(self._uvicorn_server.serve())
        # block start() until uvicorn has bound the socket so callers can hit REST immediately.
        # if the serve task dies during bind (port in use etc.), surface the exception
        # instead of reporting "ready" on a missing REST endpoint.
        for _ in range(100):
            if self._uvicorn_task.done():
                exc = self._uvicorn_task.exception()
                if exc is not None:
                    raise exc
                raise RuntimeError("uvicorn server exited before readiness")
            if getattr(self._uvicorn_server, "started", False):
                break
            await asyncio.sleep(0.05)
        self._started = True
        self._usage_task = asyncio.create_task(self._usage_broadcast_loop())

    async def stop(self) -> None:
        # per-step swallow so one failure doesn't leak other resources
        if self._usage_task is not None:
            self._usage_task.cancel()
            try:
                await self._usage_task
            except asyncio.CancelledError:
                pass
            self._usage_task = None
        if self._ws_server is not None:
            try:
                self._ws_server.close()
                await self._ws_server.wait_closed()
            except Exception:
                log.warning("server stop: ws_server close failed", exc_info=True)
            self._ws_server = None
        if self._uvicorn_server is not None:
            try:
                self._uvicorn_server.should_exit = True
            except Exception:
                log.warning(
                    "server stop: uvicorn should_exit failed", exc_info=True
                )
        if self._uvicorn_task is not None:
            try:
                await asyncio.wait_for(self._uvicorn_task, timeout=5.0)
            except Exception:
                log.warning(
                    "server stop: uvicorn wait_for failed", exc_info=True
                )
                try:
                    self._uvicorn_task.cancel()
                except Exception:
                    log.warning(
                        "server stop: uvicorn task cancel failed", exc_info=True
                    )
            self._uvicorn_task = None
            self._uvicorn_server = None
        if self._conn is not None:
            loop = asyncio.get_running_loop()
            conn = self._conn
            self._conn = None
            try:
                await loop.run_in_executor(None, conn.close)
            except Exception:
                log.warning("server stop: duckdb close failed", exc_info=True)
        with self._lock:
            self._registry.clear()
            self._status.clear()
        self._loop = None
        self._started = False

    def get_connected_agents(self) -> list[str]:
        with self._lock:
            return list(self._registry.keys())

    def set_shutdown_callback(
        self, fn: Callable[[], Awaitable[None]] | None
    ) -> None:
        # callable is dispatched via create_task from POST /shutdown so the
        # endpoint returns 200 immediately and the shutdown work runs in the
        # background — Tauri's 2s http timeout never trips.
        self._shutdown_callback = fn

    async def broadcast(self, sender: str, content: str) -> None:
        payload = {"type": "broadcast", "from": sender, "content": content}
        await self._route_broadcast(sender, payload)
        await self._log_message(sender, None, "broadcast", payload)

    async def broadcast_roster(self) -> None:
        await self._broadcast_roster()

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/agents")
        async def agents() -> dict[str, Any]:
            with self._lock:
                names = list(self._registry.keys())
                statuses = dict(self._status)
            return {"agents": names, "statuses": statuses}

        @app.get("/status")
        async def status_snapshot() -> dict[str, str]:
            with self._lock:
                return dict(self._status)

        @app.get("/agents/models")
        async def agents_models() -> dict[str, list[str]]:
            return {
                "models": [
                    "claude-opus-4-7",
                    "claude-sonnet-4-6",
                    "claude-haiku-4-5-20251001",
                ]
            }

        @app.post("/shutdown")
        async def shutdown() -> dict[str, bool]:
            # fire-and-forget: schedule the callback and respond immediately so
            # the Tauri graceful path doesn't wait on teardown (which can take
            # seconds as uvicorn/WS/DB unwind).
            cb = self._shutdown_callback
            if cb is not None:
                task = asyncio.get_running_loop().create_task(cb())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return {"ok": True}

        @app.get("/usage")
        async def usage() -> dict[str, Any]:
            from core.usage_tracker import UsageTracker
            tracker = UsageTracker()
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, tracker.compute)

        @app.post("/messenger/telegram/configure")
        async def telegram_configure(request: Request) -> JSONResponse:
            # Parse + format-validate before touching the network so a
            # malformed token never leaks into the getMe probe.
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    {"ok": False, "error": "invalid json body"}, status_code=400
                )
            if not isinstance(body, dict):
                return JSONResponse(
                    {"ok": False, "error": "body must be an object"},
                    status_code=400,
                )
            token = body.get("token")
            if not isinstance(token, str) or not _TELEGRAM_TOKEN_RE.match(token):
                return JSONResponse(
                    {"ok": False, "error": "invalid token format"},
                    status_code=400,
                )
            # Live probe — Telegram returns {ok: true, result: {username, ...}}
            # on success. 5s timeout keeps the UI responsive when Telegram is
            # unreachable.
            import httpx

            url = f"https://api.telegram.org/bot{token}/getMe"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
            except Exception as exc:
                log.warning("telegram getMe probe failed: %s", exc)
                return JSONResponse(
                    {"ok": False, "error": f"network error: {exc.__class__.__name__}"},
                    status_code=400,
                )
            if resp.status_code != 200:
                return JSONResponse(
                    {"ok": False, "error": f"telegram http {resp.status_code}"},
                    status_code=400,
                )
            try:
                data = resp.json()
            except Exception:
                return JSONResponse(
                    {"ok": False, "error": "invalid telegram response"},
                    status_code=400,
                )
            if not isinstance(data, dict) or not data.get("ok"):
                return JSONResponse(
                    {"ok": False, "error": "telegram rejected token"},
                    status_code=400,
                )
            result = data.get("result") or {}
            username = (
                result.get("username") if isinstance(result, dict) else None
            )
            # Persist alongside other messenger state files under .claudeorch.
            # Preserve paired_user_id if the user re-configures after pairing.
            loop = asyncio.get_running_loop()
            existing = await loop.run_in_executor(None, _read_telegram_state)
            persisted: dict[str, Any] = {
                "token": token,
                "username": username if isinstance(username, str) else None,
            }
            if isinstance(existing.get("paired_user_id"), int):
                persisted["paired_user_id"] = existing["paired_user_id"]
            try:
                await loop.run_in_executor(
                    None, _write_telegram_state, persisted
                )
            except Exception:
                log.exception("failed to persist telegram config")
                return JSONResponse(
                    {"ok": False, "error": "persist failed"}, status_code=500
                )
            return JSONResponse(
                {"ok": True, "username": persisted["username"]}
            )

        @app.post("/messenger/telegram/start-pairing")
        async def telegram_start_pairing() -> dict[str, str]:
            # New nonce per call. We do NOT evict previous codes here — the
            # spec explicitly allows an old code to remain valid for the rest
            # of its 5-minute window in case the user asked twice.
            code = _generate_pair_code()
            now = self._telegram_clock()
            # Cheap GC: drop expired nonces on every issue so the dict
            # doesn't grow unbounded if the endpoint is spammed.
            ttl = TELEGRAM_PAIR_TTL
            expired = [
                c for c, t in self._telegram_pairs.items() if now - t > ttl
            ]
            for c in expired:
                self._telegram_pairs.pop(c, None)
            self._telegram_pairs[code] = now
            return {"code": code}

        @app.get("/messenger/telegram/status")
        async def telegram_status() -> dict[str, Any]:
            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, _read_telegram_state)
            token = state.get("token") if isinstance(state, dict) else None
            username = state.get("username") if isinstance(state, dict) else None
            paired = state.get("paired_user_id") if isinstance(state, dict) else None
            # The bridge is not booted in this PR, so "connected" isn't yet
            # a runtime state — we report "connected" once we have a token
            # AND a paired user, "connecting" if only the token is set.
            if isinstance(token, str) and token:
                status = "connected" if isinstance(paired, int) else "connecting"
            else:
                status = "not-connected"
            return {
                "status": status,
                "username": username if isinstance(username, str) else None,
                "paired_user_id": paired if isinstance(paired, int) else None,
            }

        @app.post("/messenger/discord/configure")
        async def discord_configure(request: Request) -> JSONResponse:
            # Format-only validation: discord.py can't validate a token
            # without opening a gateway connection (which is too heavy
            # for a REST probe and would fight the bridge's own
            # client.start()). We just assert the token shape and persist;
            # the actual "is this token live?" answer comes from the
            # bridge boot.
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    {"ok": False, "error": "invalid json body"}, status_code=400
                )
            if not isinstance(body, dict):
                return JSONResponse(
                    {"ok": False, "error": "body must be an object"},
                    status_code=400,
                )
            token = body.get("token")
            if not isinstance(token, str) or not _DISCORD_TOKEN_RE.match(token):
                return JSONResponse(
                    {"ok": False, "error": "invalid token format"},
                    status_code=400,
                )
            # Preserve paired_user_id if the user re-configures after pairing,
            # same pattern as the Telegram configure flow.
            loop = asyncio.get_running_loop()
            existing = await loop.run_in_executor(None, _read_discord_state)
            persisted: dict[str, Any] = {
                "token": token,
                # bot_user is populated by the bridge on ready; configure
                # can't know it without a gateway connect, so null for now.
                "bot_user": existing.get("bot_user")
                if isinstance(existing, dict)
                and isinstance(existing.get("bot_user"), str)
                else None,
            }
            if isinstance(existing.get("paired_user_id"), int):
                persisted["paired_user_id"] = existing["paired_user_id"]
            try:
                await loop.run_in_executor(
                    None, _write_discord_state, persisted
                )
            except Exception:
                log.exception("failed to persist discord config")
                return JSONResponse(
                    {"ok": False, "error": "persist failed"}, status_code=500
                )
            return JSONResponse({"ok": True})

        @app.post("/messenger/discord/start-pairing")
        async def discord_start_pairing() -> dict[str, str]:
            # Separate store from Telegram — a Telegram code can't pair
            # a Discord user and vice versa.
            code = _generate_discord_pair_code()
            now = self._discord_clock()
            ttl = DISCORD_PAIR_TTL
            expired = [
                c for c, t in self._discord_pairs.items() if now - t > ttl
            ]
            for c in expired:
                self._discord_pairs.pop(c, None)
            self._discord_pairs[code] = now
            return {"code": code}

        @app.get("/messenger/discord/status")
        async def discord_status() -> dict[str, Any]:
            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, _read_discord_state)
            token = state.get("token") if isinstance(state, dict) else None
            bot_user = (
                state.get("bot_user") if isinstance(state, dict) else None
            )
            paired = (
                state.get("paired_user_id") if isinstance(state, dict) else None
            )
            # Same tri-state as Telegram: not-connected (no token),
            # connecting (token but no paired user), connected (both).
            if isinstance(token, str) and token:
                status = "connected" if isinstance(paired, int) else "connecting"
            else:
                status = "not-connected"
            return {
                "status": status,
                "bot_user": bot_user if isinstance(bot_user, str) else None,
                "paired_user_id": paired if isinstance(paired, int) else None,
            }

        @app.post("/messenger/webhook/configure")
        async def webhook_configure(request: Request) -> JSONResponse:
            # Shape-validate body first — reject anything weird before we
            # touch the constructor (which also validates but raises
            # ValueError that we'd then have to massage into a 400).
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    {"ok": False, "error": "invalid json body"}, status_code=400
                )
            if not isinstance(body, dict):
                return JSONResponse(
                    {"ok": False, "error": "body must be an object"},
                    status_code=400,
                )
            url = body.get("url")
            secret = body.get("secret")
            template = body.get("template")
            if not isinstance(url, str) or not url:
                return JSONResponse(
                    {"ok": False, "error": "url is required"},
                    status_code=400,
                )
            # URL scheme guard — http/https only, never file://, javascript:,
            # etc. Anything else would be a config footgun at best and an
                # SSRF enabler at worst.
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return JSONResponse(
                    {"ok": False, "error": "url must be http(s) with a host"},
                    status_code=400,
                )
            if not isinstance(secret, str):
                return JSONResponse(
                    {"ok": False, "error": "secret must be a string"},
                    status_code=400,
                )
            if not isinstance(template, str) or not template:
                return JSONResponse(
                    {"ok": False, "error": "template is required"},
                    status_code=400,
                )
            # Delegate template validation to the bridge constructor so we
            # only have ONE validation code path. ValueError → 400 with the
            # ctor's message (it's already user-facing).
            from core.messengers.webhook import WebhookBridge

            try:
                WebhookBridge(url=url, secret=secret, template=template)
            except ValueError as exc:
                return JSONResponse(
                    {"ok": False, "error": str(exc)}, status_code=400
                )
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    None,
                    _write_webhook_state,
                    {"url": url, "secret": secret, "template": template},
                )
            except Exception:
                log.exception("failed to persist webhook config")
                return JSONResponse(
                    {"ok": False, "error": "persist failed"}, status_code=500
                )
            return JSONResponse({"ok": True})

        @app.post("/messenger/webhook/test")
        async def webhook_test() -> JSONResponse:
            # Reads config from disk so the live UI "Test" button exercises
            # the same path as ``notify()`` will use in production. If there
            # is no config yet, surface a clear 400 — the UI should have
            # prompted the user to Save first.
            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, _read_webhook_state)
            url = state.get("url") if isinstance(state, dict) else None
            secret = state.get("secret") if isinstance(state, dict) else None
            template = state.get("template") if isinstance(state, dict) else None
            if not (
                isinstance(url, str)
                and url
                and isinstance(secret, str)
                and isinstance(template, str)
                and template
            ):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": None,
                        "error": "webhook not configured",
                    },
                    status_code=400,
                )
            from core.messengers.webhook import WebhookBridge

            try:
                bridge = WebhookBridge(url=url, secret=secret, template=template)
            except ValueError as exc:
                # Saved config somehow became invalid (manual edit, partial
                # write). Don't crash — return a shaped error so the UI can
                # prompt a re-save.
                return JSONResponse(
                    {"ok": False, "status": None, "error": str(exc)},
                    status_code=400,
                )
            try:
                resp = await bridge.notify(
                    "test", "groft", "Webhook test from Groft"
                )
            except Exception as exc:
                # Connection refused, DNS failure, TLS error, timeout — any
                # network-layer failure collapses to a single "not delivered"
                # signal for the UI. Class name is safe to expose; body isn't.
                log.warning("webhook test: network error", exc_info=True)
                return JSONResponse(
                    {
                        "ok": False,
                        "status": None,
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
            return JSONResponse(
                {
                    "ok": bool(resp.is_success),
                    "status": int(resp.status_code),
                    "error": None
                    if resp.is_success
                    else f"HTTP {resp.status_code}",
                }
            )

        @app.get("/messenger/webhook/status")
        async def webhook_status() -> dict[str, Any]:
            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, _read_webhook_state)
            url = state.get("url") if isinstance(state, dict) else None
            if isinstance(url, str) and url:
                return {"status": "connected", "url": url}
            return {"status": "not-connected", "url": None}

        @app.post("/agents/spawn")
        async def agents_spawn(request: Request) -> Any:
            return await self._handle_agent_action(request, "spawn")

        @app.post("/agents/despawn")
        async def agents_despawn(request: Request) -> Any:
            return await self._handle_agent_action(request, "despawn")

        @app.post("/agents/kill")
        async def agents_kill(request: Request) -> Any:
            # TODO: distinguish SIGTERM (despawn) from SIGKILL (kill) once the
            # backend exposes a force-kill path. For now kill is an alias for
            # despawn so the UI button works end-to-end.
            return await self._handle_agent_action(request, "kill")

        @app.post("/agents/clear-history")
        async def agents_clear_history(request: Request) -> Any:
            return await self._handle_clear_history(request)

        @app.get("/tasks")
        async def tasks_snapshot() -> dict[str, Any]:
            if self._tasks_dir is None:
                return {"type": "tasks", "backlog": [], "current": [], "done": []}
            loop = asyncio.get_running_loop()
            # parse_tasks_dir hits disk — offload so the event loop stays responsive
            parsed = await loop.run_in_executor(
                None, parse_tasks_dir, self._tasks_dir
            )
            return {
                "type": "tasks",
                "backlog": parsed.get("backlog", []),
                "current": parsed.get("current", []),
                "done": parsed.get("done", []),
            }

        return app

    async def _parse_role(
        self, request: Request
    ) -> tuple[str | None, JSONResponse | None]:
        # Returns (role, error_response). Either role is non-empty str and
        # error is None, or role is None and error is a 400 JSONResponse.
        try:
            body = await request.json()
        except Exception:
            return None, JSONResponse(
                {"error": "invalid json body"}, status_code=400
            )
        if not isinstance(body, dict):
            return None, JSONResponse(
                {"error": "body must be an object"}, status_code=400
            )
        role = body.get("role")
        if not isinstance(role, str) or not role.strip():
            return None, JSONResponse(
                {"error": "role is required"}, status_code=400
            )
        return role.strip(), None

    async def _handle_agent_action(
        self, request: Request, action: str
    ) -> JSONResponse:
        role, err = await self._parse_role(request)
        if err is not None:
            return err
        assert role is not None
        if self._orchestrator is None:
            return JSONResponse(
                {"error": "orchestrator not attached"}, status_code=503
            )
        try:
            if action == "spawn":
                ok = await self._orchestrator.spawn_role(role)
            else:
                # despawn and kill share the code path until a real force-kill
                # lands on the backend; see TODO in agents_kill endpoint.
                ok = await self._orchestrator.despawn_role(role)
        except Exception:
            log.exception("agent action failed action=%s role=%s", action, role)
            return JSONResponse(
                {"ok": False, "role": role, "error": "internal error"},
                status_code=500,
            )
        if not ok:
            return JSONResponse(
                {"ok": False, "role": role, "reason": "unknown-or-active"},
                status_code=409,
            )
        return JSONResponse({"ok": True, "role": role})

    async def _handle_clear_history(self, request: Request) -> JSONResponse:
        role, err = await self._parse_role(request)
        if err is not None:
            return err
        assert role is not None
        loop = asyncio.get_running_loop()
        try:
            cleared = await loop.run_in_executor(
                None, self._clear_history_sync, role
            )
        except Exception:
            log.exception("clear-history failed role=%s", role)
            return JSONResponse(
                {"ok": False, "role": role, "error": "internal error"},
                status_code=500,
            )
        return JSONResponse({"ok": True, "cleared": cleared})

    def _clear_history_sync(self, role: str) -> list[str]:
        # Wipe {role}.md and any archive/{role}-*.md copies. memory_dir() and
        # memory_archive_dir() auto-mkdir, so a fresh checkout also works.
        cleared: list[str] = []
        archive = memory_archive_dir()
        for item in archive.glob(f"{role}-*.md"):
            try:
                item.unlink()
                cleared.append(str(item))
            except FileNotFoundError:
                continue
            except OSError:
                log.warning(
                    "clear-history: failed to delete %s", item, exc_info=True
                )
        memory_path = memory_dir() / f"{role}.md"
        # truncate-to-empty (preserve inode) if file exists, else create empty.
        # Parent is guaranteed by memory_dir() side-effect.
        memory_path.write_text("", encoding="utf-8")
        cleared.append(str(memory_path))
        return cleared

    async def _usage_broadcast_loop(self) -> None:
        from core.usage_tracker import UsageTracker
        tracker = UsageTracker()
        while True:
            await asyncio.sleep(60)
            try:
                loop = asyncio.get_running_loop()
                windows = await loop.run_in_executor(None, tracker.compute)
                await self._forward_to_ui({"type": "usage", "windows": windows})
            except Exception:
                log.warning("usage broadcast failed", exc_info=True)

    async def _handle_connection(self, ws: WebSocketServerProtocol) -> None:
        agent_name: str | None = None
        try:
            raw = await ws.recv()
            try:
                first = json.loads(raw)
            except Exception:
                # protocol violation on first frame — 1008 policy violation
                log.warning("bad handshake frame", exc_info=True)
                await ws.close(code=1008, reason="invalid register")
                return
            if not isinstance(first, dict) or first.get("type") != "register":
                await ws.close(code=1008, reason="expected register")
                return
            name = first.get("agent")
            if not isinstance(name, str) or not name:
                await ws.close(code=1008, reason="missing agent")
                return
            agent_name = name
            await self._register(agent_name, ws)
            await self._log_message(agent_name, None, "register", first)
            async for raw_msg in ws:
                try:
                    msg = json.loads(raw_msg)
                except Exception:
                    # malformed JSON drops the frame but keeps the socket alive
                    log.warning(
                        "dropped malformed frame from %s", agent_name
                    )
                    continue
                if not isinstance(msg, dict):
                    continue
                await self._dispatch(msg, ws, agent_name)
        except ConnectionClosed:
            pass
        except Exception:
            # never let a single connection take down the server
            log.exception(
                "connection handler crashed for agent=%s", agent_name
            )
        finally:
            if agent_name is not None:
                self._unregister(agent_name, ws)

    async def _register(self, name: str, ws: WebSocketServerProtocol) -> None:
        old: WebSocketServerProtocol | None = None
        with self._lock:
            old = self._registry.get(name)
            self._registry[name] = ws
        if old is not None and old is not ws:
            # reconnect: evict the previous socket so the new one owns the name
            try:
                await old.close(code=1000, reason="reconnect")
            except Exception:
                log.debug("reconnect close failed for %s", name, exc_info=True)
        # push fresh roster to UI so the agent panel reflects the new connection
        await self._broadcast_roster()

    def _unregister(self, name: str, ws: WebSocketServerProtocol) -> None:
        removed = False
        with self._lock:
            current = self._registry.get(name)
            if current is ws:
                self._registry.pop(name, None)
                self._status.pop(name, None)
                removed = True
        if removed:
            # fire-and-forget; sync method can't await, but roster push is best-effort.
            # _unregister may be called from cross-thread paths (REST/MCP use
            # _lock without the event loop), so hop back to the server loop
            # via call_soon_threadsafe when the caller's loop isn't ours.
            server_loop = self._loop
            if server_loop is None:
                return
            try:
                current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is server_loop:
                task = server_loop.create_task(self._broadcast_roster())
                # retain strong ref so CPython doesn't GC the task mid-flight
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                def _schedule() -> None:
                    task = server_loop.create_task(self._broadcast_roster())
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                try:
                    server_loop.call_soon_threadsafe(_schedule)
                except RuntimeError:
                    # loop already closed — best-effort ends here
                    return

    async def _broadcast_roster(self) -> None:
        # silent skip if the UI never connected; _forward_to_ui handles that too
        with self._lock:
            agents = list(self._registry.keys())
        await self._forward_to_ui({"type": "roster", "agents": agents})

    async def _dispatch(
        self, msg: dict[str, Any], ws: WebSocketServerProtocol, sender: str
    ) -> None:
        mtype = msg.get("type")
        if mtype == "message":
            to = msg.get("to")
            content = msg.get("content", "")
            if not isinstance(to, str):
                return
            await self._route_direct(to, msg)
            await self._log_message(sender, to, "message", msg)
            # forward to recipient's pane whenever one is known. Workers
            # don't run a WS consumer, so the pane is the actual inbox.
            # Exception: opus reads its inbox through the claudeorch-comms MCP
            # bridge (get_messages), so a pane forward would double the
            # message in opus's TUI. `_resolve_pane_target` would also fall
            # back to `lead_target` here, which IS opus's pane — so the
            # guard has to be explicit, not "only if target is registered".
            if isinstance(content, str) and to != SNAPSHOT_SINK_AGENT:
                mode = msg.get("mode")
                model = msg.get("model")
                prefix_parts: list[str] = []
                if isinstance(mode, str) and mode:
                    prefix_parts.append(f"mode={mode}")
                if isinstance(model, str) and model:
                    prefix_parts.append(f"model={model}")
                prefix = f"[{', '.join(prefix_parts)}] " if prefix_parts else ""
                await self._forward_to_pane(to, prefix + content)
        elif mtype == "broadcast":
            await self._route_broadcast(sender, msg)
            await self._log_message(sender, None, "broadcast", msg)
        elif mtype == "snapshot":
            # trust the payload's `agent` so an orchestrator can relay snapshots
            # captured from worker panes; fall back to sender for self-sourced frames.
            payload_agent = msg.get("agent")
            agent_for_ui = (
                payload_agent
                if isinstance(payload_agent, str) and payload_agent
                else sender
            )
            await self._log_message(sender, agent_for_ui, "snapshot", msg)
            terminal = msg.get("terminal", msg.get("content", ""))
            await self._forward_to_ui(
                {"type": "snapshot", "agent": agent_for_ui, "terminal": terminal}
            )
        elif mtype == "status":
            payload_agent = msg.get("agent")
            agent_for_ui = (
                payload_agent
                if isinstance(payload_agent, str) and payload_agent
                else sender
            )
            status = msg.get("status")
            if isinstance(status, str):
                with self._lock:
                    self._status[agent_for_ui] = status
            await self._log_message(sender, None, "status", msg)
            if isinstance(status, str):
                forwarded: dict[str, Any] = {
                    "type": "status",
                    "agent": agent_for_ui,
                    "status": status,
                }
                # pass through the optional telemetry fields the UI consumes
                for key in (
                    "currentAction",
                    "currentTask",
                    "model",
                    "mode",
                    "uptime",
                    "cycles",
                    "tokensIn",
                    "tokensOut",
                    "spark",
                ):
                    if key in msg:
                        forwarded[key] = msg[key]
                await self._forward_to_ui(forwarded)
        elif mtype == "decision":
            required = ("title", "context", "decision", "rationale")
            if not all(isinstance(msg.get(k), str) for k in required):
                return
            payload = {k: msg[k] for k in required}
            synthesized = {
                "type": "message",
                "from": sender,
                "to": SNAPSHOT_SINK_AGENT,
                "content": "/decide " + json.dumps(payload),
            }
            await self._route_direct(SNAPSHOT_SINK_AGENT, synthesized)
            await self._log_message(sender, SNAPSHOT_SINK_AGENT, "decision", msg)
        elif mtype == "handoff":
            files = msg.get("files")
            if not isinstance(files, list):
                return
            cleaned = [f for f in files if isinstance(f, str)]
            payload = {"type": "handoff", "files": cleaned}
            await self._forward_to_ui(payload)
            await self._log_message(sender, UI_SINK_AGENT, "handoff", payload)
        elif mtype == "tasks":
            validated: dict[str, Any] = {"type": "tasks"}
            for bucket in ("backlog", "current", "done"):
                v = msg.get(bucket)
                if not isinstance(v, list):
                    continue
                cleaned: list[dict[str, Any]] = []
                for item in v:
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("id"), str)
                        and isinstance(item.get("title"), str)
                        and isinstance(item.get("status"), str)
                    ):
                        cleaned.append(item)
                validated[bucket] = cleaned
            await self._forward_to_ui(validated)
            await self._log_message(sender, UI_SINK_AGENT, "tasks", validated)
        else:
            # unknown type is silently dropped per spec
            return

    async def _route_direct(self, to: str, payload: dict[str, Any]) -> None:
        with self._lock:
            target = self._registry.get(to)
        if target is None:
            return
        try:
            await target.send(json.dumps(payload))
        except ConnectionClosed:
            self._unregister(to, target)
        except Exception:
            log.warning("direct route failed: agent=%s", to, exc_info=True)
            self._unregister(to, target)

    async def _forward_to_ui(self, payload: dict[str, Any]) -> None:
        # best-effort push to the UI viewer; any failure is swallowed (UI may be absent/gone)
        with self._lock:
            target = self._registry.get(UI_SINK_AGENT)
        if target is None:
            return
        try:
            await target.send(json.dumps(payload))
        except ConnectionClosed:
            self._unregister(UI_SINK_AGENT, target)
        except Exception:
            log.warning("ui forward failed", exc_info=True)
            self._unregister(UI_SINK_AGENT, target)

    def _resolve_pane_target(self, to: str) -> str | None:
        # backend.list_targets() reflects live spawns; lead_target is the
        # boot-time fallback (typically the orchestrator's own pane).
        if self._backend is not None:
            target = self._backend.list_targets().get(to)
            if target is not None:
                return target
        return self._lead_target

    async def _forward_to_pane(self, to: str, content: str) -> None:
        if self._backend is None:
            return
        target = self._resolve_pane_target(to)
        if target is None:
            return
        # injection guard lives in the backend's send_text — see TmuxBackend.
        ok = await self._backend.send_text(target, content)
        if not ok:
            log.warning(
                "pane forward failed: to=%s target=%s", to, target
            )

    async def _route_broadcast(self, sender: str, payload: dict[str, Any]) -> None:
        with self._lock:
            recipients = [
                (name, ws) for name, ws in self._registry.items() if name != sender
            ]
        data = json.dumps(payload)
        for name, ws in recipients:
            try:
                await ws.send(data)
            except ConnectionClosed:
                self._unregister(name, ws)
            except Exception:
                log.warning(
                    "broadcast route failed: agent=%s", name, exc_info=True
                )
                self._unregister(name, ws)

    async def _log_message(
        self,
        msg_from: str | None,
        msg_to: str | None,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self._conn is None:
            return
        row = (
            datetime.now(timezone.utc),
            msg_from,
            msg_to,
            msg_type,
            json.dumps(payload),
        )
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            try:
                await loop.run_in_executor(None, self._execute_insert, row)
            except Exception:
                # logging failures never propagate — messaging must keep flowing
                log.debug("message log insert failed", exc_info=True)

    def _execute_insert(self, row: tuple[Any, ...]) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO messages (id, timestamp, msg_from, msg_to, msg_type, content)"
            " VALUES (nextval('messages_id_seq'), ?, ?, ?, ?, ?)",
            row,
        )

    async def push_tasks_to_ui(self, tasks_dir: Path | str) -> None:
        tasks = parse_tasks_dir(Path(tasks_dir))
        payload: dict[str, Any] = {"type": "tasks"}
        if tasks["backlog"]:
            payload["backlog"] = tasks["backlog"]
        if tasks["current"]:
            payload["current"] = tasks["current"]
        if tasks["done"]:
            payload["done"] = tasks["done"]
        await self._forward_to_ui(payload)
        # reserved marker so analytics grouping by sender doesn't conjure a
        # "server" phantom agent next to real WS clients.
        await self._log_message("__server__", UI_SINK_AGENT, "tasks", payload)
