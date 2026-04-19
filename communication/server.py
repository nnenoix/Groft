from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import duckdb
import uvicorn
import websockets
from fastapi import FastAPI
from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol

from communication.task_parser import parse_tasks_dir
from core.paths import claudeorch_dir
from core.process import ProcessBackend

log = logging.getLogger(__name__)
# snapshots forward to this agent name when connected; chosen per spec ("opus" is orchestrator)
SNAPSHOT_SINK_AGENT = "opus"
# UI client (viewer) receives parallel forwards of snapshot+status; silent skip if not connected
UI_SINK_AGENT = "ui"

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
        app = self._build_app()
        config = uvicorn.Config(
            app,
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
