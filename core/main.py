from __future__ import annotations

import sys
from pathlib import Path

# script-mode: ensure project root is importable before `from core.*` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from communication.client import CommunicationClient
from communication.server import CommunicationServer
from core.error.error_handler import ErrorHandler
from core.guard.process_guard import ProcessGuard
from core.recovery.recovery_manager import RecoveryManager
from core.session.checkpoint import CheckpointManager
from core.watchdog.agent_watchdog import AgentWatchdog
from git_manager.manager import GitManager
from memory.manager import MemoryManager


async def main() -> None:
    comm_server = CommunicationServer()
    await comm_server.start()

    comm_client = CommunicationClient(agent_name="orchestrator")
    await comm_client.connect()

    checkpoint_manager = CheckpointManager()
    process_guard = ProcessGuard()
    agent_watchdog = AgentWatchdog(comm_client=comm_client)
    error_handler = ErrorHandler()
    git_manager = GitManager()
    memory_manager = MemoryManager()

    await checkpoint_manager.initialize()
    await error_handler.initialize()
    await git_manager.initialize(Path(__file__).resolve().parent.parent)
    await memory_manager.initialize(Path(__file__).resolve().parent.parent)

    recovery_manager = RecoveryManager(
        checkpoint_manager, process_guard, agent_watchdog, error_handler
    )

    # install must run inside the loop so signal handlers attach to it
    process_guard.install()

    result = await recovery_manager.initialize()

    if result.has_unfinished:
        print("Обнаружена незавершённая сессия:")
        print(result.message)
    else:
        print("ClaudeOrch готов к работе")

    await agent_watchdog.start()

    await process_guard.wait_for_stop()

    print("ClaudeOrch остановлен.")

    # per-step try/except so one teardown failure doesn't leak other resources
    try:
        await recovery_manager.shutdown()
    except Exception:
        pass
    try:
        await comm_client.disconnect()
    except Exception:
        pass
    try:
        await comm_server.stop()
    except Exception:
        pass
    try:
        await git_manager.close()
    except Exception:
        pass
    try:
        await memory_manager.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
