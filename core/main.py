from __future__ import annotations

import sys
from pathlib import Path

# script-mode: ensure project root is importable before `from core.*` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import logging
from typing import Any
from uuid import uuid4

import yaml

from communication.client import CommunicationClient
from communication.server import CommunicationServer
from core.error.error_handler import ErrorHandler
from core.guard.process_guard import ProcessGuard
from core.handoff import scan_and_record_handoff
from core.logging_setup import configure_logging
from core.orchestrator import Orchestrator
from core.recovery.recovery_manager import RecoveryManager
from core.session.checkpoint import Checkpoint, CheckpointManager
from core.spawner import AgentSpawner
from core.watchdog.agent_watchdog import AgentWatchdog
from git_manager.manager import GitManager
from memory.manager import MemoryManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yml"

log = logging.getLogger(__name__)

# defaults used when config.yml is missing or the tmux section is absent
_DEFAULT_LEAD_TMUX_TARGET = "claudeorch:0"
_DEFAULT_AGENT_TMUX_TARGETS: dict[str, str] = {"opus": "claudeorch:0"}


def _load_tmux_config(path: Path) -> tuple[str, dict[str, str]]:
    # best-effort: any parse/read failure falls back to defaults
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _DEFAULT_LEAD_TMUX_TARGET, dict(_DEFAULT_AGENT_TMUX_TARGETS)
    except OSError:
        log.warning("config.yml unreadable, falling back to defaults", exc_info=True)
        return _DEFAULT_LEAD_TMUX_TARGET, dict(_DEFAULT_AGENT_TMUX_TARGETS)
    try:
        data: Any = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        log.warning("config.yml parse failed, falling back to defaults", exc_info=True)
        return _DEFAULT_LEAD_TMUX_TARGET, dict(_DEFAULT_AGENT_TMUX_TARGETS)
    tmux_section = data.get("tmux") if isinstance(data, dict) else None
    if not isinstance(tmux_section, dict):
        return _DEFAULT_LEAD_TMUX_TARGET, dict(_DEFAULT_AGENT_TMUX_TARGETS)
    lead_raw = tmux_section.get("lead_target")
    lead = lead_raw if isinstance(lead_raw, str) and lead_raw else _DEFAULT_LEAD_TMUX_TARGET
    targets_raw = tmux_section.get("agent_targets")
    agent_targets: dict[str, str] = {}
    if isinstance(targets_raw, dict):
        for name, target in targets_raw.items():
            if isinstance(name, str) and isinstance(target, str) and name and target:
                agent_targets[name] = target
    if not agent_targets:
        agent_targets = dict(_DEFAULT_AGENT_TMUX_TARGETS)
    return lead, agent_targets


async def main() -> None:
    configure_logging(log_dir=PROJECT_ROOT / ".claudeorch" / "logs")
    lead_tmux_target, agent_tmux_targets = _load_tmux_config(CONFIG_PATH)

    comm_server = CommunicationServer(
        lead_tmux_target=lead_tmux_target,
        agent_tmux_targets=agent_tmux_targets,
        tasks_dir=PROJECT_ROOT / "tasks",
    )
    await comm_server.start()

    # Opus is the orchestrator — the UI and other agents address it as "opus",
    # so the WS registration name must match that to keep messages routable.
    comm_client = CommunicationClient(agent_name="opus")
    await comm_client.connect()

    checkpoint_manager = CheckpointManager()
    process_guard = ProcessGuard()
    agent_watchdog = AgentWatchdog(comm_client=comm_client)
    error_handler = ErrorHandler()
    git_manager = GitManager()
    memory_manager = MemoryManager()
    spawner = AgentSpawner(str(PROJECT_ROOT), str(CONFIG_PATH))
    orchestrator = Orchestrator(spawner)

    await checkpoint_manager.initialize()
    await error_handler.initialize()
    await git_manager.initialize(PROJECT_ROOT)
    await memory_manager.initialize(PROJECT_ROOT)

    recovery_manager = RecoveryManager(
        checkpoint_manager,
        process_guard,
        agent_watchdog,
        error_handler,
        agent_tmux_targets=agent_tmux_targets,
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
    for name, target in spawner.get_tmux_targets().items():
        agent_watchdog.register_agent(name, target)

    # install must run inside the loop so signal handlers attach to it
    process_guard.install()

    # session_id is stable for the lifetime of this process; checkpoints share it
    session_id = str(uuid4())

    def current_checkpoint() -> Checkpoint:
        # snapshot the live state into a Checkpoint the manager can persist.
        # agent_states are pulled from whatever the watchdog currently tracks
        # (can be empty on first boot — RecoveryManager re-registers on restore).
        agent_states: dict[str, Any] = {}
        for name in list(agent_tmux_targets.keys()):
            state = agent_watchdog.get_state(name)
            if state is None:
                continue
            agent_states[name] = {
                "tmux_target": state.tmux_target,
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
        try:
            await spawner.spawn(agent_name)
        except Exception:
            log.exception("spawn failed during restart agent=%s", agent_name)
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
        await scan_and_record_handoff(PROJECT_ROOT)
    except Exception:
        log.exception("handoff scan failed")

    # stash orchestrator on the client so future inbox-routed commands can reach it
    comm_client.orchestrator = orchestrator  # type: ignore[attr-defined]

    await agent_watchdog.start()

    async def consume_opus_inbox() -> None:
        # Drain frames addressed to opus so UI `message` frames don't pile up
        # on a dead socket. No routing yet — log so the trace is visible.
        try:
            async for frame in comm_client.listen():
                mtype = frame.get("type")
                sender = frame.get("from") or "?"
                content = frame.get("content")
                log.info(
                    "opus-inbox type=%s from=%s content=%r", mtype, sender, content
                )
        except Exception:
            log.exception("opus-inbox listen stopped")

    async def poll_tasks_loop() -> None:
        # UI's Tasks view needs a periodic push; FS watch would be nicer but
        # keeping it trivial until there's a concrete cost signal.
        while True:
            try:
                await comm_server.push_tasks_to_ui(PROJECT_ROOT / "tasks")
            except Exception:
                log.exception("tasks-poll push failed")
            await asyncio.sleep(5.0)

    inbox_task = asyncio.create_task(consume_opus_inbox())
    tasks_task = asyncio.create_task(poll_tasks_loop())

    await process_guard.wait_for_stop()

    log.info("ClaudeOrch stopped")

    # per-step try/except so one teardown failure doesn't leak other resources
    for bg_task in (inbox_task, tasks_task):
        try:
            bg_task.cancel()
        except Exception:
            log.exception("teardown step failed: bg_task.cancel")
    for bg_task in (inbox_task, tasks_task):
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("teardown step failed: await bg_task")
    try:
        await spawner.despawn_all()
    except Exception:
        log.exception("teardown step failed: spawner.despawn_all")
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
