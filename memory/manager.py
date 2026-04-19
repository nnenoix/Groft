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
CREATE TABLE IF NOT EXISTS memory_events (
    id BIGINT,
    timestamp TIMESTAMP,
    operation TEXT,
    agent_name TEXT,
    bytes_before INTEGER,
    bytes_after INTEGER,
    details JSON
);
CREATE SEQUENCE IF NOT EXISTS memory_events_id_seq;
"""

_COMPRESSION_PROMPT = (
    "Сожми следующую память агента до ключевых фактов, решений и конвенций. "
    "Сохрани markdown-структуру, убери длинные отчёты и устаревшую информацию. "
    "Выведи только сжатый текст без преамбулы."
)


class MemoryManager:
    COMPRESSION_THRESHOLD_BYTES: int = 10 * 1024

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else claudeorch_dir() / "memory_log.duckdb"
        )
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()
        self._project_path: Path | None = None

    async def initialize(self, project_path: Path | str) -> None:
        self._project_path = Path(project_path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._archive_dir().mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)

    async def close(self) -> None:
        if self._conn is not None:
            loop = asyncio.get_running_loop()
            conn = self._conn
            self._conn = None
            await loop.run_in_executor(None, conn.close)

    def agent_memory_path(self, name: str) -> Path:
        assert self._project_path is not None
        return self._project_path / "memory" / f"{name}.md"

    def shared_memory_path(self) -> Path:
        assert self._project_path is not None
        return self._project_path / "memory" / "shared.md"

    def current_task_path(self) -> Path:
        assert self._project_path is not None
        return self._project_path / "architecture" / "current-task.md"

    def current_test_path(self) -> Path:
        assert self._project_path is not None
        return self._project_path / "architecture" / "current-test.md"

    def archive_dir(self) -> Path:
        return self._archive_dir()

    def _archive_dir(self) -> Path:
        assert self._project_path is not None
        return self._project_path / "memory" / "archive"

    async def get_context(self, agent_name: str, task: str | None = None) -> str:
        agent_text = await self._read_or_empty(self.agent_memory_path(agent_name))
        shared_text = await self._read_or_empty(self.shared_memory_path())
        current_task_text = await self._read_or_empty(self.current_task_path())
        current_test_text = await self._read_or_empty(self.current_test_path())
        parts = [
            f"# Context for {agent_name}",
            "",
            "## Agent Memory",
            agent_text if agent_text.strip() else "_пусто_",
            "",
            "## Shared Memory",
            shared_text if shared_text.strip() else "_пусто_",
            "",
            "## Current Task",
            current_task_text if current_task_text.strip() else "_пусто_",
            "",
            "## Current Test",
            current_test_text if current_test_text.strip() else "(no current test)",
        ]
        if task is not None:
            parts.extend(["", "## Task", task])
        context = "\n".join(parts) + "\n"
        await self._log(
            operation="get_context",
            agent_name=agent_name,
            bytes_before=None,
            bytes_after=len(context.encode("utf-8")),
            details={"task_provided": task is not None},
        )
        return context

    async def update_agent_memory(self, agent_name: str, content: str) -> None:
        path = self.agent_memory_path(agent_name)
        bytes_before = await self._file_size(path)
        header = self._dated_header()
        # preserve an H1 title when creating a fresh file so downstream readers have a handle
        if bytes_before == 0:
            body = f"# {agent_name}\n{header}{content}\n"
        else:
            body = f"{header}{content}\n"
        await self._append(path, body, create=bytes_before == 0)
        bytes_after = await self._file_size(path)
        await self._log(
            operation="update_agent",
            agent_name=agent_name,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            details={},
        )

    async def update_shared_memory(self, content: str) -> None:
        path = self.shared_memory_path()
        bytes_before = await self._file_size(path)
        header = self._dated_header()
        if bytes_before == 0:
            body = f"# Shared Team Memory\n{header}{content}\n"
        else:
            body = f"{header}{content}\n"
        await self._append(path, body, create=bytes_before == 0)
        bytes_after = await self._file_size(path)
        await self._log(
            operation="update_shared",
            agent_name=None,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            details={},
        )

    async def append_decision(
        self,
        title: str,
        context: str,
        decision: str,
        rationale: str,
    ) -> None:
        assert self._project_path is not None
        path = self._project_path / "architecture" / "decisions.md"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        bytes_before = await self._file_size(path)
        body = (
            f"\n## {timestamp} — {title}\n\n"
            f"### Context\n\n{context}\n\n"
            f"### Decision\n\n{decision}\n\n"
            f"### Rationale\n\n{rationale}\n"
        )
        loop = asyncio.get_running_loop()

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(body)

        await loop.run_in_executor(None, _write)
        bytes_after = await self._file_size(path)
        await self._log(
            operation="append_decision",
            agent_name=None,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            details={"title": title},
        )

    async def compress(self, agent_name: str) -> bool:
        return await self._compress_path(
            path=self.agent_memory_path(agent_name),
            log_agent_name=agent_name,
            archive_prefix=agent_name,
            default_title=f"# {agent_name}",
        )

    async def compress_shared(self) -> bool:
        try:
            return await self._compress_path(
                path=self.shared_memory_path(),
                log_agent_name="shared",
                archive_prefix="shared",
                default_title="# Shared Team Memory",
            )
        except Exception:
            log.exception("compress_shared failed")
            return False

    async def _compress_path(
        self,
        path: Path,
        log_agent_name: str,
        archive_prefix: str,
        default_title: str,
    ) -> bool:
        bytes_before = await self._file_size(path)
        if bytes_before < self.COMPRESSION_THRESHOLD_BYTES:
            return False
        loop = asyncio.get_running_loop()
        original = await loop.run_in_executor(None, path.read_text, "utf-8")
        archive_path = self._archive_dir() / (
            f"{archive_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
        )
        await loop.run_in_executor(None, archive_path.write_text, original, "utf-8")
        # delegate compression to Opus via CLI — Python never inspects the compressed text
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude",
                "-p",
                _COMPRESSION_PROMPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            await self._log(
                operation="compress",
                agent_name=log_agent_name,
                bytes_before=bytes_before,
                bytes_after=bytes_before,
                details={"success": False, "reason": "claude_cli_missing"},
            )
            return False
        stdout_bytes, stderr_bytes = await proc.communicate(original.encode("utf-8"))
        returncode = proc.returncode if proc.returncode is not None else -1
        compressed = stdout_bytes.decode(errors="replace").strip()
        if returncode != 0 or not compressed:
            await self._log(
                operation="compress",
                agent_name=log_agent_name,
                bytes_before=bytes_before,
                bytes_after=bytes_before,
                details={
                    "success": False,
                    "returncode": returncode,
                    "stderr": stderr_bytes.decode(errors="replace")[-512:],
                },
            )
            return False
        title = self._extract_h1(original) or default_title
        new_body = f"{title}\n\n{compressed}\n"
        await loop.run_in_executor(None, path.write_text, new_body, "utf-8")
        bytes_after = await self._file_size(path)
        await self._log(
            operation="compress",
            agent_name=log_agent_name,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            details={"success": True, "archive": str(archive_path)},
        )
        return True

    @staticmethod
    def _dated_header() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"\n### {stamp} — session\n"

    @staticmethod
    def _extract_h1(text: str) -> str | None:
        for line in text.splitlines():
            if line.startswith("# "):
                return line
        return None

    async def _read_or_empty(self, path: Path) -> str:
        loop = asyncio.get_running_loop()

        def _read() -> str:
            if not path.exists():
                return ""
            return path.read_text(encoding="utf-8")

        return await loop.run_in_executor(None, _read)

    async def _file_size(self, path: Path) -> int:
        loop = asyncio.get_running_loop()

        def _size() -> int:
            if not path.exists():
                return 0
            return path.stat().st_size

        return await loop.run_in_executor(None, _size)

    async def _append(self, path: Path, body: str, create: bool) -> None:
        loop = asyncio.get_running_loop()

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "w" if create else "a"
            with path.open(mode, encoding="utf-8") as fh:
                fh.write(body)

        await loop.run_in_executor(None, _write)

    async def _log(
        self,
        operation: str,
        agent_name: str | None,
        bytes_before: int | None,
        bytes_after: int | None,
        details: dict[str, Any],
    ) -> None:
        if self._conn is None:
            return
        row = (
            datetime.now(timezone.utc),
            operation,
            agent_name,
            bytes_before,
            bytes_after,
            json.dumps(details),
        )
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            await loop.run_in_executor(None, self._execute_insert, row)

    def _execute_insert(self, row: tuple[Any, ...]) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO memory_events (id, timestamp, operation, agent_name,"
            " bytes_before, bytes_after, details)"
            " VALUES (nextval('memory_events_id_seq'), ?, ?, ?, ?, ?, ?)",
            row,
        )
