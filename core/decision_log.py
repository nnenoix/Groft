from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from core.paths import claudeorch_dir

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS decisions_id_seq START 1;
CREATE TABLE IF NOT EXISTS decisions (
    id BIGINT PRIMARY KEY DEFAULT nextval('decisions_id_seq'),
    ts TIMESTAMP NOT NULL,
    agent VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    chosen VARCHAR NOT NULL,
    alternatives JSON,
    reason VARCHAR NOT NULL,
    task_id VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_agent ON decisions(agent);
"""


class DecisionLog:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else claudeorch_dir() / "decisions.duckdb"
        )
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)

    async def append(
        self,
        agent: str,
        category: str,
        chosen: str,
        alternatives: list[str] | None,
        reason: str,
        task_id: str | None = None,
        ts: datetime | None = None,
    ) -> int:
        agent = (agent or "").strip()
        category = (category or "").strip()
        chosen = (chosen or "").strip()
        reason = (reason or "").strip()
        if not agent:
            raise ValueError("agent must not be empty")
        if not category:
            raise ValueError("category must not be empty")
        if not chosen:
            raise ValueError("chosen must not be empty")
        if not reason:
            raise ValueError("reason must not be empty")
        if ts is None:
            ts = datetime.now(timezone.utc)
        alts_json = json.dumps(alternatives) if alternatives is not None else None
        async with self._db_lock:
            assert self._conn is not None
            loop = asyncio.get_running_loop()
            row = await loop.run_in_executor(
                None,
                lambda: self._conn.execute(
                    """
                    INSERT INTO decisions (ts, agent, category, chosen, alternatives, reason, task_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    [ts, agent, category, chosen, alts_json, reason, task_id],
                ).fetchone(),
            )
        return int(row[0])

    async def list_recent(
        self,
        limit: int = 100,
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        async with self._db_lock:
            assert self._conn is not None
            loop = asyncio.get_running_loop()
            if agent is not None:
                rows = await loop.run_in_executor(
                    None,
                    lambda: self._conn.execute(
                        "SELECT id, ts, agent, category, chosen, alternatives, reason, task_id "
                        "FROM decisions WHERE agent = ? ORDER BY ts DESC LIMIT ?",
                        [agent, limit],
                    ).fetchall(),
                )
            else:
                rows = await loop.run_in_executor(
                    None,
                    lambda: self._conn.execute(
                        "SELECT id, ts, agent, category, chosen, alternatives, reason, task_id "
                        "FROM decisions ORDER BY ts DESC LIMIT ?",
                        [limit],
                    ).fetchall(),
                )
        result = []
        for row in rows:
            id_, ts_raw, ag, cat, cho, alts_raw, reas, tid = row
            if isinstance(ts_raw, datetime):
                ts_str = ts_raw.isoformat()
            else:
                ts_str = str(ts_raw)
            alts: list[str] | None = None
            if alts_raw is not None:
                try:
                    alts = json.loads(alts_raw) if isinstance(alts_raw, str) else alts_raw
                except Exception:
                    alts = None
            result.append({
                "id": id_,
                "ts": ts_str,
                "agent": ag,
                "category": cat,
                "chosen": cho,
                "alternatives": alts if alts is not None else [],
                "reason": reas,
                "task_id": tid,
            })
        return result

    async def close(self) -> None:
        if self._conn is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None
