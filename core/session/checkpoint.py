from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path(".claudeorch/checkpoints.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    task_number INTEGER NOT NULL,
    completed_tasks TEXT NOT NULL,
    agent_states TEXT NOT NULL,
    last_commit TEXT NOT NULL,
    dependency_graph TEXT NOT NULL,
    unfinished_tasks TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_ts ON checkpoints(timestamp);
"""


@dataclass
class Checkpoint:
    session_id: str
    stage: str
    task_number: int
    completed_tasks: list[Any] = field(default_factory=list)
    agent_states: dict[str, Any] = field(default_factory=dict)
    last_commit: str = ""
    dependency_graph: dict[str, Any] = field(default_factory=dict)
    unfinished_tasks: list[Any] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.session_id,
            self.stage,
            self.task_number,
            json.dumps(self.completed_tasks),
            json.dumps(self.agent_states),
            self.last_commit,
            json.dumps(self.dependency_graph),
            json.dumps(self.unfinished_tasks),
            self.timestamp.astimezone(timezone.utc).isoformat(),
        )

    @classmethod
    def from_row(cls, row: aiosqlite.Row | tuple[Any, ...]) -> "Checkpoint":
        return cls(
            session_id=row[1],
            stage=row[2],
            task_number=row[3],
            completed_tasks=json.loads(row[4]),
            agent_states=json.loads(row[5]),
            last_commit=row[6],
            dependency_graph=json.loads(row[7]),
            unfinished_tasks=json.loads(row[8]),
            timestamp=datetime.fromisoformat(row[9]),
        )


class CheckpointManager:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def save(self, checkpoint: Checkpoint) -> None:
        async with self._lock:
            # bind after the lock so a concurrent close() that nulls _conn
            # can't race with our assert/use window
            conn = self._conn
            if conn is None:
                raise RuntimeError("checkpoint manager is closed")
            # append-only history: every save is a new row so we can trace progress
            await conn.execute(
                "INSERT INTO checkpoints (session_id, stage, task_number, completed_tasks,"
                " agent_states, last_commit, dependency_graph, unfinished_tasks, timestamp)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                checkpoint.to_row(),
            )
            await conn.commit()

    async def load_latest(self) -> Checkpoint | None:
        assert self._conn is not None
        async with self._conn.execute(
            "SELECT id, session_id, stage, task_number, completed_tasks, agent_states,"
            " last_commit, dependency_graph, unfinished_tasks, timestamp"
            " FROM checkpoints ORDER BY timestamp DESC, id DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        return Checkpoint.from_row(row) if row is not None else None

    async def has_unfinished_session(self) -> bool:
        assert self._conn is not None
        async with self._conn.execute("SELECT 1 FROM checkpoints LIMIT 1") as cursor:
            return (await cursor.fetchone()) is not None

    async def clear(self, session_id: str | None = None) -> None:
        assert self._conn is not None
        async with self._lock:
            if session_id is None:
                await self._conn.execute("DELETE FROM checkpoints")
            else:
                await self._conn.execute(
                    "DELETE FROM checkpoints WHERE session_id = ?", (session_id,)
                )
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
