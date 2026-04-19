from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from core.error.error_handler import ErrorHandler
from core.guard.process_guard import ProcessGuard
from core.session.checkpoint import Checkpoint, CheckpointManager
from core.watchdog.agent_watchdog import AgentWatchdog

log = logging.getLogger(__name__)

DEFAULT_RECOVERY_LOG_PATH = Path(".claudeorch/recovery.duckdb")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_events (
    id BIGINT,
    event TEXT,
    session_id TEXT,
    stage TEXT,
    task_number INTEGER,
    downtime_seconds DOUBLE,
    details JSON,
    timestamp TIMESTAMP
);
CREATE SEQUENCE IF NOT EXISTS recovery_events_id_seq;
"""


@dataclass
class RecoveryResult:
    has_unfinished: bool
    checkpoint: Checkpoint | None
    message: str


class RecoveryManager:
    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        process_guard: ProcessGuard,
        agent_watchdog: AgentWatchdog,
        error_handler: ErrorHandler,
        agent_targets: dict[str, str] | None = None,
        recovery_log_path: Path | str | None = None,
    ) -> None:
        self._checkpoint_manager = checkpoint_manager
        self._process_guard = process_guard
        self._agent_watchdog = agent_watchdog
        self._error_handler = error_handler
        self._agent_targets: dict[str, str] = dict(agent_targets or {})
        self._log_path = (
            Path(recovery_log_path) if recovery_log_path is not None else DEFAULT_RECOVERY_LOG_PATH
        )
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()

    async def initialize(self) -> RecoveryResult:
        # caller must have already awaited checkpoint_manager.initialize() / error_handler.initialize()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._log_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)
        checkpoint = await self._checkpoint_manager.load_latest()
        if checkpoint is not None:
            message = self._build_opus_context(checkpoint)
            await self._log_event(
                event="detected_unfinished",
                session_id=checkpoint.session_id,
                stage=checkpoint.stage,
                task_number=checkpoint.task_number,
                downtime_seconds=self._downtime(checkpoint),
                details={
                    "completed": len(checkpoint.completed_tasks),
                    "pending": len(checkpoint.unfinished_tasks),
                },
            )
            return RecoveryResult(True, checkpoint, message)
        await self._log_event(event="clean_start")
        return RecoveryResult(False, None, "Чистый старт, незавершённых сессий нет.")

    async def restore_session(self, checkpoint: Checkpoint) -> str:
        missing: list[str] = []
        watchdog_registered = 0
        agents_registered = 0
        for agent_name in checkpoint.agent_states.keys():
            self._process_guard.register_agent(agent_name)
            agents_registered += 1
            target = self._agent_targets.get(agent_name)
            if target is not None:
                self._agent_watchdog.register_agent(agent_name, target)
                watchdog_registered += 1
            else:
                # surface so the operator notices — otherwise the watchdog
                # silently stops monitoring this agent across the restart.
                log.warning(
                    "restore: no target for agent=%s; watchdog not registered",
                    agent_name,
                )
                missing.append(agent_name)
        await self._log_event(
            event="restored",
            session_id=checkpoint.session_id,
            stage=checkpoint.stage,
            task_number=checkpoint.task_number,
            downtime_seconds=self._downtime(checkpoint),
            details={
                "agents_registered": agents_registered,
                "watchdog_registered": watchdog_registered,
                "missing_targets": missing,
            },
        )
        return self._build_opus_context(checkpoint)

    async def start_fresh(self) -> None:
        await self._checkpoint_manager.clear()
        await self._log_event(event="fresh_start")

    async def shutdown(self, final_checkpoint: Checkpoint | None = None) -> None:
        # per-step swallow: one failure must not short-circuit subsequent teardown
        try:
            await self._agent_watchdog.stop()
        except Exception:
            log.exception("recovery teardown failed: watchdog.stop")
        try:
            self._process_guard.uninstall()
        except Exception:
            log.exception("recovery teardown failed: process_guard.uninstall")
        if final_checkpoint is not None:
            try:
                await self._checkpoint_manager.save(final_checkpoint)
            except Exception:
                log.exception("recovery teardown failed: checkpoint.save")
        try:
            await self._error_handler.close()
        except Exception:
            log.exception("recovery teardown failed: error_handler.close")
        try:
            await self.close()
        except Exception:
            log.exception("recovery teardown failed: self.close")
        try:
            await self._checkpoint_manager.close()
        except Exception:
            log.exception("recovery teardown failed: checkpoint_manager.close")

    async def close(self) -> None:
        if self._conn is not None:
            loop = asyncio.get_running_loop()
            conn = self._conn
            self._conn = None
            await loop.run_in_executor(None, conn.close)

    @staticmethod
    def _build_opus_context(checkpoint: Checkpoint) -> str:
        done_count = len(checkpoint.completed_tasks)
        pending = (
            ", ".join(str(t) for t in checkpoint.unfinished_tasks)
            if checkpoint.unfinished_tasks
            else "нет"
        )
        commit = checkpoint.last_commit or "неизвестно"
        return (
            f"Сессия была прервана на этапе {checkpoint.stage}, задача {checkpoint.task_number}.\n"
            f"Выполнено задач: {done_count}.\n"
            f"Незавершённые задачи: {pending}.\n"
            f"Последний коммит: {commit}.\n"
            f"Продолжай с того же места."
        )

    @staticmethod
    def _downtime(checkpoint: Checkpoint) -> float:
        now = datetime.now(timezone.utc)
        return (now - checkpoint.timestamp.astimezone(timezone.utc)).total_seconds()

    async def _log_event(
        self,
        event: str,
        session_id: str | None = None,
        stage: str | None = None,
        task_number: int | None = None,
        downtime_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._conn is None:
            return
        row = (
            event,
            session_id,
            stage,
            task_number,
            downtime_seconds,
            json.dumps(details) if details is not None else None,
            datetime.now(timezone.utc),
        )
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            await loop.run_in_executor(None, self._execute_insert, row)

    def _execute_insert(self, row: tuple[Any, ...]) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO recovery_events (id, event, session_id, stage, task_number,"
            " downtime_seconds, details, timestamp)"
            " VALUES (nextval('recovery_events_id_seq'), ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
