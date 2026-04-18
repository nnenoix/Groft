from __future__ import annotations

import sys
from pathlib import Path

# script-mode: ensure project root is importable before `from core.*` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from core.error.error_handler import ErrorHandler
from core.guard.process_guard import ProcessGuard
from core.recovery.recovery_manager import RecoveryManager
from core.session.checkpoint import CheckpointManager
from core.watchdog.agent_watchdog import AgentWatchdog


async def main() -> None:
    checkpoint_manager = CheckpointManager()
    process_guard = ProcessGuard()
    agent_watchdog = AgentWatchdog()
    error_handler = ErrorHandler()

    await checkpoint_manager.initialize()
    await error_handler.initialize()

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

    try:
        # smoke test: bound the wait so the process exits without Ctrl-C
        await asyncio.wait_for(process_guard.wait_for_stop(), timeout=2.0)
    except asyncio.TimeoutError:
        pass

    print("Smoke test завершён.")

    await recovery_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
