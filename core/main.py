from __future__ import annotations

import sys
from pathlib import Path

# script-mode: ensure project root is importable before `from core.*` resolves
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

import yaml

from communication.client import CommunicationClient
from communication.server import CommunicationServer
from core import agents_watcher
from core.error.error_handler import ErrorHandler
from core.guard.process_guard import ProcessGuard
from core.handoff import scan_and_record_handoff
from core.logging_setup import configure_logging
from core.orchestrator import Orchestrator
from core.paths import (
    architecture_dir,
    claudeorch_dir,
    config_path,
    logs_dir,
    tasks_dir,
    user_data_root,
)
from core.process import select_backend
from core.recovery.recovery_manager import RecoveryManager
from core.session.checkpoint import Checkpoint, CheckpointManager
from core.spawner import AgentSpawner
from core.watchdog.agent_watchdog import AgentWatchdog
from git_manager.manager import GitManager
from memory.manager import MemoryManager

log = logging.getLogger(__name__)

# defaults used when config.yml is missing or the section is absent
_DEFAULT_LEAD_TARGET = "claudeorch:0"
_DEFAULT_AGENT_TARGETS: dict[str, str] = {"opus": "claudeorch:0"}


def _load_runtime_config(path: Path) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Return (full_config, lead_target, agent_targets).

    Lead/agent targets keep their legacy `tmux:` location for now — backend
    selection lives under `process:` (PR1) and stays orthogonal.
    """
    # best-effort: any parse/read failure falls back to defaults
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, _DEFAULT_LEAD_TARGET, dict(_DEFAULT_AGENT_TARGETS)
    except OSError:
        log.warning("config.yml unreadable, falling back to defaults", exc_info=True)
        return {}, _DEFAULT_LEAD_TARGET, dict(_DEFAULT_AGENT_TARGETS)
    try:
        data: Any = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        log.warning("config.yml parse failed, falling back to defaults", exc_info=True)
        return {}, _DEFAULT_LEAD_TARGET, dict(_DEFAULT_AGENT_TARGETS)
    if not isinstance(data, dict):
        return {}, _DEFAULT_LEAD_TARGET, dict(_DEFAULT_AGENT_TARGETS)
    section = data.get("tmux")
    if not isinstance(section, dict):
        return data, _DEFAULT_LEAD_TARGET, dict(_DEFAULT_AGENT_TARGETS)
    lead_raw = section.get("lead_target")
    lead = lead_raw if isinstance(lead_raw, str) and lead_raw else _DEFAULT_LEAD_TARGET
    targets_raw = section.get("agent_targets")
    agent_targets: dict[str, str] = {}
    if isinstance(targets_raw, dict):
        for name, target in targets_raw.items():
            if isinstance(name, str) and isinstance(target, str) and name and target:
                agent_targets[name] = target
    if not agent_targets:
        agent_targets = dict(_DEFAULT_AGENT_TARGETS)
    return data, lead, agent_targets


async def _maybe_start_telegram_bridge(
    orchestrator: Orchestrator,
    backend: Any,
) -> Any | None:
    """Construct + start a TelegramBridge if on-disk config is present.

    Returns the live bridge handle on success, or None when no config exists,
    the token is malformed, python-telegram-bot isn't installed, or bridge
    startup itself fails. All failure modes log but never propagate — the
    orchestrator must keep booting.
    """
    state_path = claudeorch_dir() / "messenger-telegram.json"
    try:
        # Lazy import so the messengers package isn't dragged into smoke runs
        # that don't need it. Module-level import would be fine too — this is
        # just defensive in case the package gains heavier deps later.
        from core.messengers.telegram import (
            TelegramBridge,
            is_valid_token_format,
            read_state_file,
        )
    except Exception:
        log.warning("telegram bridge module unavailable", exc_info=True)
        return None
    state = read_state_file(state_path)
    token = state.get("token")
    if not isinstance(token, str) or not is_valid_token_format(token):
        # Silent return — most deployments never configure Telegram.
        return None
    allowlist: set[int] = set()
    paired = state.get("paired_user_id")
    if isinstance(paired, int):
        allowlist.add(paired)
    try:
        bridge = TelegramBridge(
            token,
            orchestrator,
            allowlist=allowlist,
            backend=backend,
            state_path=state_path,
        )
    except ValueError:
        log.warning("telegram bridge rejected on-disk token as malformed")
        return None
    except Exception:
        log.exception("telegram bridge construction failed")
        return None
    try:
        await bridge.start()
    except Exception:
        log.exception("telegram bridge start failed")
        return None
    log.info("telegram bridge started (paired=%s)", paired)
    return bridge


async def _maybe_start_discord_bridge(
    orchestrator: Orchestrator,
    backend: Any,
) -> Any | None:
    """Construct + start a DiscordBridge if on-disk config is present.

    Mirrors ``_maybe_start_telegram_bridge`` — returns the live bridge
    on success, or None when no config exists, the token is malformed,
    discord.py isn't installed, or bridge startup fails. All failure
    modes log but never propagate.
    """
    state_path = claudeorch_dir() / "messenger-discord.json"
    try:
        from core.messengers.discord import (
            DiscordBridge,
            is_valid_token_format,
            read_state_file,
        )
    except Exception:
        log.warning("discord bridge module unavailable", exc_info=True)
        return None
    state = read_state_file(state_path)
    token = state.get("token")
    if not isinstance(token, str) or not is_valid_token_format(token):
        return None
    allowlist: set[int] = set()
    paired = state.get("paired_user_id")
    if isinstance(paired, int):
        allowlist.add(paired)
    try:
        bridge = DiscordBridge(
            token,
            orchestrator,
            allowlist=allowlist,
            backend=backend,
            state_path=state_path,
        )
    except ValueError:
        log.warning("discord bridge rejected on-disk token as malformed")
        return None
    except Exception:
        log.exception("discord bridge construction failed")
        return None
    try:
        await bridge.start()
    except Exception:
        log.exception("discord bridge start failed")
        return None
    log.info("discord bridge started (paired=%s)", paired)
    return bridge


async def main() -> None:
    project_root = user_data_root()
    configure_logging(log_dir=logs_dir())
    if "--smoke" in sys.argv:
        log.info("smoke ok")
        return
    raw_config, lead_target, agent_targets = _load_runtime_config(config_path())

    # install signal handlers before anything binds ports / opens files so a
    # Ctrl-C during boot lands in the guard instead of aborting mid-startup
    # and leaving the WS server or duckdb connections orphaned.
    process_guard = ProcessGuard()
    process_guard.install()

    # one ProcessBackend instance shared by spawner/server/watchdog so they
    # all read the same live target registry. select_backend honours
    # process.backend in config.yml (default auto -> tmux on POSIX).
    backend = select_backend(raw_config)

    # Build spawner/orchestrator up front so CommunicationServer can accept
    # the orchestrator handle for its REST /agents/* endpoints.
    spawner = AgentSpawner(str(project_root), str(config_path()), backend=backend)
    orchestrator = Orchestrator(spawner)

    # Optional Telegram bridge: boots only if the operator has completed the
    # configure-then-pair flow (UI writes .claudeorch/messenger-telegram.json).
    # A missing python-telegram-bot dep degrades to a warning — the rest of
    # the orchestrator runs unchanged.
    telegram_bridge = await _maybe_start_telegram_bridge(orchestrator, backend)

    # Optional Discord bridge — same lazy opt-in as Telegram: boots only if
    # the operator has completed configure-then-pair via the UI. A missing
    # discord.py dep degrades to a warning; the orchestrator keeps going.
    discord_bridge = await _maybe_start_discord_bridge(orchestrator, backend)

    comm_server = CommunicationServer(
        backend=backend,
        lead_target=lead_target,
        tasks_dir=tasks_dir(),
        orchestrator=orchestrator,
    )
    await comm_server.start()
    comm_server.set_shutdown_callback(process_guard.request_shutdown)

    # Opus is the orchestrator — the UI and other agents address it as "opus",
    # so the WS registration name must match that to keep messages routable.
    comm_client = CommunicationClient(agent_name="opus")
    await comm_client.connect()

    checkpoint_manager = CheckpointManager()
    agent_watchdog = AgentWatchdog(comm_client=comm_client, backend=backend)
    error_handler = ErrorHandler()
    git_manager = GitManager()
    memory_manager = MemoryManager()

    await checkpoint_manager.initialize()
    await error_handler.initialize()
    await git_manager.initialize(project_root)
    await memory_manager.initialize(project_root)

    recovery_manager = RecoveryManager(
        checkpoint_manager,
        process_guard,
        agent_watchdog,
        error_handler,
        agent_targets=agent_targets,
    )

    # keep watchdog registry in lock-step with spawner lifecycle — each spawn
    # auto-registers, each despawn auto-unregisters, so no gap at runtime
    spawner.set_register_callback(
        lambda name, target: agent_watchdog.register_agent(name, target)
    )
    spawner.set_unregister_callback(
        lambda name: agent_watchdog.unregister_agent(name)
    )
    # any agents spawner already tracks (empty at boot, non-empty after restore)
    for name, target in spawner.get_targets().items():
        agent_watchdog.register_agent(name, target)

    # session_id is stable for the lifetime of this process; checkpoints share it
    session_id = str(uuid4())

    def current_checkpoint() -> Checkpoint:
        # snapshot the live state into a Checkpoint the manager can persist.
        # agent_states are pulled from whatever the watchdog currently tracks
        # (can be empty on first boot — RecoveryManager re-registers on restore).
        agent_states: dict[str, Any] = {}
        for name in list(agent_targets.keys()):
            state = agent_watchdog.get_state(name)
            if state is None:
                continue
            agent_states[name] = {
                "target": state.target,
                "status": state.status,
                "last_change_time": state.last_change_time.isoformat(),
            }
        return Checkpoint(
            session_id=session_id,
            stage="running",
            task_number=0,
            agent_states=agent_states,
        )

    async def save_current_checkpoint() -> None:
        # wrapping save() keeps the callback signature Callable[[], Awaitable[None]]
        await checkpoint_manager.save(current_checkpoint())

    async def restart_claude_code(agent_name: str = "opus") -> None:
        # self-restart would kill the orchestrator mid-run; skip defensively.
        if agent_name == "opus":
            log.info("restart skipped for self: %s", agent_name)
            return
        log.info("restart requested: %s", agent_name)
        try:
            await spawner.despawn(agent_name)
        except Exception:
            log.exception("despawn failed during restart agent=%s", agent_name)
        spawn_ok = False
        try:
            spawn_ok = await spawner.spawn(agent_name)
        except Exception:
            log.exception("spawn failed during restart agent=%s", agent_name)
        # clear stale watchdog timers before re-register so the next tick
        # treats the respawn as a fresh lifecycle, not an extension of the
        # stuck window that triggered this restart.
        if spawn_ok:
            try:
                agent_watchdog.reset_state(agent_name)
            except Exception:
                log.exception(
                    "watchdog reset_state failed agent=%s", agent_name
                )
        # tell the UI the agent is coming back so the badge flips to restarting
        try:
            await comm_client.status_for(agent_name, "restarting")
        except Exception:
            log.exception(
                "status_for restarting failed agent=%s", agent_name
            )

    async def notify_ui_stuck(agent_name: str) -> None:
        # typed status frame so the UI agent row turns stuck, not just the log feed.
        try:
            await comm_client.status_for(agent_name, "stuck")
        except Exception:
            log.exception("status_for stuck failed agent=%s", agent_name)

    async def emit_watchdog_status(agent_name: str, status: str) -> None:
        try:
            await comm_client.status_for(agent_name, status)
        except Exception:
            log.exception(
                "status_for failed agent=%s status=%s", agent_name, status
            )

    async def wake_up_agent(agent_name: str) -> None:
        await comm_client.send(agent_name, "wake up, are you there?")

    # Провязка callbacks — без этого watchdog/error/guard остаются немыми.
    process_guard.set_checkpoint_callback(save_current_checkpoint)
    error_handler.set_checkpoint_callback(save_current_checkpoint)
    error_handler.set_restart_callback(restart_claude_code)
    agent_watchdog.set_wake_up_callback(wake_up_agent)
    agent_watchdog.set_restart_callback(restart_claude_code)
    agent_watchdog.set_notification_callback(notify_ui_stuck)
    agent_watchdog.set_status_callback(emit_watchdog_status)

    result = await recovery_manager.initialize()

    if result.has_unfinished:
        log.warning("unfinished session detected: %s", result.message)
        checkpoint = result.checkpoint
        if checkpoint is None:
            # defensive: RecoveryResult.has_unfinished implies a checkpoint,
            # but reload here if the contract ever weakens
            checkpoint = await checkpoint_manager.load_latest()
        if checkpoint is not None:
            await recovery_manager.restore_session(checkpoint)
    else:
        log.info("ClaudeOrch ready")

    try:
        await scan_and_record_handoff(project_root)
    except Exception:
        log.exception("handoff scan failed")

    await agent_watchdog.start()

    async def _on_agents_dir_change() -> None:
        await comm_server.broadcast_roster()

    agents_watcher_task = await agents_watcher.start(
        project_root, _on_agents_dir_change
    )

    async def _dispatch_inbox_command(content: str) -> None:
        # slash-command surface for the UI → opus channel. Anything else is
        # logged and ignored so stray chatter doesn't crash the loop.
        stripped = content.strip()
        if not stripped.startswith("/"):
            log.info("opus-inbox non-command skipped: %r", content)
            return
        parts = stripped.split()
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else None
        if cmd == "/spawn":
            if arg is None:
                log.info("opus-inbox /spawn missing role")
                return
            try:
                await orchestrator.spawn_role(arg)
                await comm_client.status_for(arg, "active")
            except Exception:
                log.exception("opus-inbox /spawn failed role=%s", arg)
        elif cmd == "/despawn":
            if arg is None:
                log.info("opus-inbox /despawn missing role")
                return
            try:
                await orchestrator.despawn_role(arg)
                await comm_client.status_for(arg, "idle")
                # Roster re-broadcast happens naturally via _unregister when
                # the despawned agent's ws connection drops.
            except Exception:
                log.exception("opus-inbox /despawn failed role=%s", arg)
        elif cmd == "/decide":
            raw_json = stripped[len(cmd):].strip()
            if not raw_json:
                log.info("opus-inbox /decide missing payload")
                return
            try:
                payload = json.loads(raw_json)
            except Exception:
                log.exception("opus-inbox /decide bad JSON")
                return
            required = ("title", "context", "decision", "rationale")
            if not isinstance(payload, dict) or not all(
                isinstance(payload.get(k), str) for k in required
            ):
                log.info("opus-inbox /decide missing required fields")
                return
            try:
                await memory_manager.append_decision(
                    title=payload["title"],
                    context=payload["context"],
                    decision=payload["decision"],
                    rationale=payload["rationale"],
                )
                log.info(
                    "opus-inbox /decide appended title=%r", payload["title"]
                )
            except Exception:
                log.exception("opus-inbox /decide append failed")
        elif cmd == "/restart":
            if arg is None:
                log.info("opus-inbox /restart missing role")
                return
            try:
                await orchestrator.restart_role(arg)
                await comm_client.status_for(arg, "restarting")
            except Exception:
                log.exception("opus-inbox /restart failed role=%s", arg)
        elif cmd == "/rescan-handoff":
            try:
                new_files = await scan_and_record_handoff(project_root)
                await comm_client.handoff_event(new_files or [])
            except Exception:
                log.exception("opus-inbox /rescan-handoff failed")
        elif cmd == "/runtest":
            try:
                test_path = architecture_dir() / "current-test.md"
                body = ""
                if test_path.exists():
                    body = test_path.read_text(encoding="utf-8")
                if not body.strip():
                    log.info("no current-test.md")
                    return
                await comm_client.send("tester", body)
            except Exception:
                log.exception("opus-inbox /runtest failed")
        else:
            log.info("opus-inbox unknown command: %r", stripped)

    async def consume_opus_inbox() -> None:
        # Drain frames addressed to opus and dispatch slash commands from UI.
        try:
            async for frame in comm_client.listen():
                mtype = frame.get("type")
                sender = frame.get("from") or "?"
                content = frame.get("content")
                log.info(
                    "opus-inbox type=%s from=%s content=%r", mtype, sender, content
                )
                if (
                    mtype == "message"
                    and sender == "tester"
                    and isinstance(content, str)
                    and content.startswith("TEST_RESULT:")
                ):
                    log.info("test result from tester: %s", content)
                if mtype == "message" and isinstance(content, str):
                    try:
                        await _dispatch_inbox_command(content)
                    except Exception:
                        log.exception("opus-inbox dispatch crashed")
        except Exception:
            log.exception("opus-inbox listen stopped")

    async def poll_tasks_loop() -> None:
        # UI's Tasks view needs a periodic push; FS watch would be nicer but
        # keeping it trivial until there's a concrete cost signal.
        # Hash the (id,status) tuples and skip re-push when nothing changed —
        # UI store reconciles by id so redundant frames are pure waste.
        from communication.task_parser import parse_tasks_dir

        last_hash: int | None = None
        first = True
        while True:
            try:
                parsed = await asyncio.get_running_loop().run_in_executor(
                    None, parse_tasks_dir, tasks_dir()
                )
                fingerprint: list[tuple[str, str]] = []
                for bucket in ("backlog", "current", "done"):
                    for item in parsed.get(bucket, []):
                        if (
                            isinstance(item, dict)
                            and isinstance(item.get("id"), str)
                            and isinstance(item.get("status"), str)
                        ):
                            fingerprint.append((item["id"], item["status"]))
                fingerprint.sort()
                current_hash = hash(tuple(fingerprint))
                if first or current_hash != last_hash:
                    await comm_server.push_tasks_to_ui(tasks_dir())
                    last_hash = current_hash
                    first = False
            except Exception:
                log.exception("tasks-poll push failed")
            await asyncio.sleep(5.0)

    async def handoff_poll_loop() -> None:
        # 30s tick — cheap module-level fingerprint dedupe in scan_and_record_handoff
        # ensures we touch design-handoff.md only when the inventory actually shifts.
        while True:
            await asyncio.sleep(30.0)
            try:
                new_files = await scan_and_record_handoff(project_root)
                if new_files:
                    await comm_client.handoff_event(new_files)
            except Exception:
                log.exception("handoff poll loop iteration failed")

    async def memory_compress_loop() -> None:
        # Periodic sweep of per-agent and shared memory. Threshold check lives
        # inside MemoryManager so files under the limit are no-ops.
        while True:
            await asyncio.sleep(600.0)
            try:
                for name in orchestrator.known_roles():
                    try:
                        await memory_manager.compress(name)
                    except Exception:
                        log.exception("memory compress failed agent=%s", name)
                try:
                    await memory_manager.compress_shared()
                except Exception:
                    log.exception("memory compress shared failed")
            except Exception:
                log.exception("memory_compress_loop iteration crashed")

    inbox_task = asyncio.create_task(consume_opus_inbox())
    tasks_task = asyncio.create_task(poll_tasks_loop())
    handoff_task = asyncio.create_task(handoff_poll_loop())
    memory_task = asyncio.create_task(memory_compress_loop())
    watcher_task = agents_watcher_task

    await process_guard.wait_for_stop()

    log.info("ClaudeOrch stopped")

    # per-step try/except so one teardown failure doesn't leak other resources
    for bg_task in (inbox_task, tasks_task, handoff_task, memory_task, watcher_task):
        try:
            bg_task.cancel()
        except Exception:
            log.exception("teardown step failed: bg_task.cancel")
    for bg_task in (inbox_task, tasks_task, handoff_task, memory_task, watcher_task):
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("teardown step failed: await bg_task")
    if telegram_bridge is not None:
        try:
            await telegram_bridge.stop()
        except Exception:
            log.exception("teardown step failed: telegram_bridge.stop")
    if discord_bridge is not None:
        try:
            await discord_bridge.stop()
        except Exception:
            log.exception("teardown step failed: discord_bridge.stop")
    try:
        await spawner.despawn_all()
    except Exception:
        log.exception("teardown step failed: spawner.despawn_all")
    try:
        await backend.shutdown()
    except Exception:
        log.exception("teardown step failed: backend.shutdown")
    try:
        await recovery_manager.shutdown()
    except Exception:
        log.exception("teardown step failed: recovery_manager.shutdown")
    try:
        await comm_client.disconnect()
    except Exception:
        log.exception("teardown step failed: comm_client.disconnect")
    try:
        await comm_server.stop()
    except Exception:
        log.exception("teardown step failed: comm_server.stop")
    try:
        await git_manager.close()
    except Exception:
        log.exception("teardown step failed: git_manager.close")
    try:
        await memory_manager.close()
    except Exception:
        log.exception("teardown step failed: memory_manager.close")


if __name__ == "__main__":
    asyncio.run(main())
