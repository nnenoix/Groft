from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

import duckdb

from core.paths import claudeorch_dir

_MAX_NETWORK_RETRIES = 5
_NETWORK_RETRY_DELAY = 30.0
_RATE_LIMIT_SLEEP = 60.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS errors (
    id BIGINT,
    agent_name TEXT,
    error_type TEXT,
    message TEXT,
    details JSON,
    timestamp TIMESTAMP
);
CREATE SEQUENCE IF NOT EXISTS errors_id_seq;
"""


class ErrorType(str, Enum):
    AGENT_STUCK = "AGENT_STUCK"
    RATE_LIMIT = "RATE_LIMIT"
    NETWORK_ERROR = "NETWORK_ERROR"
    CLAUDE_CODE_CRASH = "CLAUDE_CODE_CRASH"
    BAD_CODE = "BAD_CODE"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"


@dataclass
class ErrorContext:
    agent_name: str
    error_type: ErrorType
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorHandler:
    def __init__(self, duckdb_path: Path | str | None = None) -> None:
        self._db_path = (
            Path(duckdb_path)
            if duckdb_path is not None
            else claudeorch_dir() / "errors.duckdb"
        )
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()
        self._retry_counts: dict[tuple[str, ErrorType], int] = {}
        self._retry_lock = threading.Lock()
        self._callbacks: dict[ErrorType, Callable[..., Awaitable[None]]] = {}
        self._checkpoint_cb: Callable[[], Awaitable[None]] | None = None
        self._restart_cb: Callable[[str], Awaitable[None]] | None = None
        self._bad_code_cb: Callable[[ErrorContext], Awaitable[None]] | None = None
        self._compaction_cb: Callable[[str], Awaitable[None]] | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)

    async def close(self) -> None:
        if self._conn is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None

    def set_callback(
        self, error_type: ErrorType, fn: Callable[..., Awaitable[None]]
    ) -> None:
        self._callbacks[error_type] = fn

    def set_checkpoint_callback(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._checkpoint_cb = fn

    def set_restart_callback(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._restart_cb = fn

    def set_bad_code_callback(
        self, fn: Callable[[ErrorContext], Awaitable[None]]
    ) -> None:
        self._bad_code_cb = fn

    def set_compaction_callback(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._compaction_cb = fn

    def get_retry_count(self, agent_name: str, error_type: ErrorType) -> int:
        with self._retry_lock:
            return self._retry_counts.get((agent_name, error_type), 0)

    def reset_retry_count(self, agent_name: str, error_type: ErrorType) -> None:
        with self._retry_lock:
            self._retry_counts.pop((agent_name, error_type), None)

    def _increment_retry(self, agent_name: str, error_type: ErrorType) -> int:
        with self._retry_lock:
            key = (agent_name, error_type)
            self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
            return self._retry_counts[key]

    async def handle(self, context: ErrorContext) -> None:
        await self._log(context)
        # per-type override short-circuits the default strategy entirely
        override = self._callbacks.get(context.error_type)
        if override is not None:
            await override(context)
            return
        if context.error_type == ErrorType.AGENT_STUCK:
            await self._handle_agent_stuck(context)
        elif context.error_type == ErrorType.RATE_LIMIT:
            await self._handle_rate_limit(context)
        elif context.error_type == ErrorType.NETWORK_ERROR:
            await self._handle_network_error(context)
        elif context.error_type == ErrorType.CLAUDE_CODE_CRASH:
            await self._handle_crash(context)
        elif context.error_type == ErrorType.BAD_CODE:
            await self._handle_bad_code(context)
        elif context.error_type == ErrorType.CONTEXT_OVERFLOW:
            await self._handle_context_overflow(context)

    async def _handle_agent_stuck(self, context: ErrorContext) -> None:
        # watchdog owns recovery; record-only unless consumer wired an override
        self._increment_retry(context.agent_name, context.error_type)

    async def _handle_rate_limit(self, context: ErrorContext) -> None:
        self._increment_retry(context.agent_name, context.error_type)
        await asyncio.sleep(_RATE_LIMIT_SLEEP)

    async def _handle_network_error(self, context: ErrorContext) -> None:
        attempts = self._increment_retry(context.agent_name, context.error_type)
        if attempts >= _MAX_NETWORK_RETRIES:
            exhausted = ErrorContext(
                agent_name=context.agent_name,
                error_type=context.error_type,
                message=context.message,
                details={**context.details, "retries_exhausted": True, "attempts": attempts},
                timestamp=context.timestamp,
            )
            cb = self._callbacks.get(ErrorType.NETWORK_ERROR)
            if cb is not None:
                await cb(exhausted)
            self.reset_retry_count(context.agent_name, context.error_type)
            return
        await asyncio.sleep(_NETWORK_RETRY_DELAY)

    async def _handle_crash(self, context: ErrorContext) -> None:
        self._increment_retry(context.agent_name, context.error_type)
        if self._checkpoint_cb is not None:
            await self._checkpoint_cb()
        if self._restart_cb is not None:
            await self._restart_cb(context.agent_name)

    async def _handle_bad_code(self, context: ErrorContext) -> None:
        self._increment_retry(context.agent_name, context.error_type)
        # correction logic lives in an Agent Team; Python only dispatches
        if self._bad_code_cb is not None:
            await self._bad_code_cb(context)

    async def _handle_context_overflow(self, context: ErrorContext) -> None:
        self._increment_retry(context.agent_name, context.error_type)
        if self._compaction_cb is not None:
            await self._compaction_cb(context.agent_name)

    async def _log(self, context: ErrorContext) -> None:
        if self._conn is None:
            return
        row = (
            context.agent_name,
            context.error_type.value,
            context.message,
            json.dumps(context.details),
            context.timestamp.astimezone(timezone.utc),
        )
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            await loop.run_in_executor(None, self._execute_insert, row)

    def _execute_insert(self, row: tuple[Any, ...]) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO errors (id, agent_name, error_type, message, details, timestamp)"
            " VALUES (nextval('errors_id_seq'), ?, ?, ?, ?, ?)",
            row,
        )
