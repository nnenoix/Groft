from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from core.paths import claudeorch_dir

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS git_events (
    id BIGINT,
    timestamp TIMESTAMP,
    operation TEXT,
    task_name TEXT,
    success BOOLEAN,
    commit_hash TEXT,
    reason TEXT,
    stdout TEXT,
    stderr TEXT
);
CREATE SEQUENCE IF NOT EXISTS git_events_id_seq;
"""


@dataclass
class GitResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass
class RollbackEvent:
    task_name: str
    timestamp: datetime
    reason: str


class GitManager:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else claudeorch_dir() / "git_history.duckdb"
        )
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_lock = asyncio.Lock()
        self._repo_path: Path | None = None

    async def initialize(self, repo_path: Path | str) -> None:
        self._repo_path = Path(repo_path).resolve()
        # fail fast if caller pointed us at a non-repo — git commands later would be noise
        probe = await self._run(["rev-parse", "--git-dir"], cwd=self._repo_path)
        if not probe.success:
            raise RuntimeError(f"{self._repo_path} is not a git repository: {probe.stderr.strip()}")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await loop.run_in_executor(None, self._conn.execute, _SCHEMA)
        await self._log("init", None, GitResult(True, "", "", 0))

    async def close(self) -> None:
        if self._conn is not None:
            await self._log("shutdown", None, GitResult(True, "", "", 0))
            loop = asyncio.get_running_loop()
            conn = self._conn
            self._conn = None
            await loop.run_in_executor(None, conn.close)

    async def create_worktree(self, task_name: str) -> GitResult:
        assert self._repo_path is not None
        worktree_path = self._worktree_path(task_name)
        branch = f"feature/{task_name}"
        result = await self._run(
            ["worktree", "add", str(worktree_path), "-b", branch],
            cwd=self._repo_path,
        )
        await self._log("create_worktree", task_name, result)
        return result

    async def remove_worktree(self, task_name: str) -> GitResult:
        assert self._repo_path is not None
        worktree_path = self._worktree_path(task_name)
        remove_result = await self._run(
            ["worktree", "remove", str(worktree_path), "--force"],
            cwd=self._repo_path,
        )
        # branch cleanup is best-effort — branch may already be gone or merged
        branch_result = await self._run(
            ["branch", "-D", f"feature/{task_name}"],
            cwd=self._repo_path,
        )
        combined = GitResult(
            success=remove_result.success,
            stdout=remove_result.stdout + branch_result.stdout,
            stderr=remove_result.stderr + branch_result.stderr,
            returncode=remove_result.returncode,
        )
        await self._log("remove_worktree", task_name, combined)
        return combined

    def get_active_worktrees(self) -> list[str]:
        assert self._repo_path is not None
        # sync on purpose — callers want a quick snapshot, not an async hop
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(self._repo_path),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            log.warning(
                "git worktree list failed rc=%s stderr=%s",
                proc.returncode,
                proc.stderr.strip(),
            )
            return []
        prefix = "orchkerstr-"
        names: list[str] = []
        for line in proc.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            path = line[len("worktree "):].strip()
            name = Path(path).name
            if name.startswith(prefix):
                names.append(name[len(prefix):])
        return names

    async def commit(self, task_name: str, message: str) -> GitResult:
        worktree_path = self._worktree_path(task_name)
        add_result = await self._run(["add", "-A"], cwd=worktree_path)
        if not add_result.success:
            await self._log("commit", task_name, add_result)
            return add_result
        commit_result = await self._run(
            ["commit", "-m", message], cwd=worktree_path
        )
        commit_hash: str | None = None
        if commit_result.success:
            hash_result = await self._run(["rev-parse", "HEAD"], cwd=worktree_path)
            if hash_result.success:
                commit_hash = hash_result.stdout.strip()
        await self._log("commit", task_name, commit_result, commit_hash=commit_hash)
        return commit_result

    async def merge_to_main(self, task_name: str) -> GitResult:
        assert self._repo_path is not None
        branch = f"feature/{task_name}"
        merge_result = await self._run(
            ["merge", "--no-ff", branch, "-m", f"Merge feature/{task_name}"],
            cwd=self._repo_path,
        )
        commit_hash: str | None = None
        if merge_result.success:
            hash_result = await self._run(["rev-parse", "HEAD"], cwd=self._repo_path)
            if hash_result.success:
                commit_hash = hash_result.stdout.strip()
        await self._log("merge", task_name, merge_result, commit_hash=commit_hash)
        if merge_result.success:
            # only clean up worktree on success — conflicts must be left for human inspection
            await self.remove_worktree(task_name)
        return merge_result

    async def get_last_commit(self) -> str:
        assert self._repo_path is not None
        result = await self._run(["rev-parse", "HEAD"], cwd=self._repo_path)
        if not result.success:
            return ""
        return result.stdout.strip()

    async def rollback(self, task_name: str, reason: str) -> GitResult:
        assert self._repo_path is not None
        worktree_path = self._worktree_path(task_name)
        remove_result = await self._run(
            ["worktree", "remove", str(worktree_path), "--force"],
            cwd=self._repo_path,
        )
        branch_result = await self._run(
            ["branch", "-D", f"feature/{task_name}"],
            cwd=self._repo_path,
        )
        combined = GitResult(
            success=remove_result.success,
            stdout=remove_result.stdout + branch_result.stdout,
            stderr=remove_result.stderr + branch_result.stderr,
            returncode=remove_result.returncode,
        )
        await self._log("rollback", task_name, combined, reason=reason)
        return combined

    async def get_rollback_history(self) -> list[RollbackEvent]:
        if self._conn is None:
            return []
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            rows = await loop.run_in_executor(None, self._fetch_rollbacks)
        events: list[RollbackEvent] = []
        for task_name, ts, reason in rows:
            events.append(
                RollbackEvent(
                    task_name=task_name or "",
                    timestamp=ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
                    reason=reason or "",
                )
            )
        return events

    def _fetch_rollbacks(self) -> list[tuple[Any, ...]]:
        assert self._conn is not None
        return self._conn.execute(
            "SELECT task_name, timestamp, reason FROM git_events"
            " WHERE operation = 'rollback' ORDER BY timestamp DESC"
        ).fetchall()

    def _worktree_path(self, task_name: str) -> Path:
        assert self._repo_path is not None
        return self._repo_path.parent / f"orchkerstr-{task_name}"

    async def _run(self, args: list[str], cwd: Path | None = None) -> GitResult:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd) if cwd is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        returncode = proc.returncode if proc.returncode is not None else -1
        return GitResult(
            success=returncode == 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            returncode=returncode,
        )

    async def _log(
        self,
        operation: str,
        task_name: str | None,
        result: GitResult,
        commit_hash: str | None = None,
        reason: str | None = None,
    ) -> None:
        if self._conn is None:
            return
        row = (
            datetime.now(timezone.utc),
            operation,
            task_name,
            result.success,
            commit_hash,
            reason,
            result.stdout,
            result.stderr,
        )
        loop = asyncio.get_running_loop()
        async with self._db_lock:
            await loop.run_in_executor(None, self._execute_insert, row)

    def _execute_insert(self, row: tuple[Any, ...]) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO git_events (id, timestamp, operation, task_name, success,"
            " commit_hash, reason, stdout, stderr)"
            " VALUES (nextval('git_events_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
