from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP

from core.paths import claudeorch_dir

log = logging.getLogger(__name__)

AGENT_NAME = os.environ.get("AGENT_NAME", "opus")

server = FastMCP("claudeorch-comms")


_decision_log: "DecisionLog | None" = None
_decision_log_lock = asyncio.Lock()


async def _get_decision_log() -> "DecisionLog":
    global _decision_log
    async with _decision_log_lock:
        if _decision_log is not None:
            return _decision_log
        from core.decision_log import DecisionLog
        dl = DecisionLog(claudeorch_dir() / "decisions.duckdb")
        await dl.initialize()
        _decision_log = dl
        return _decision_log


@server.tool()
async def log_decision(
    category: str,
    chosen: str,
    alternatives: list[str] | None = None,
    reason: str = "",
    task_id: str | None = None,
) -> str:
    """Записать архитектурное решение в общий журнал.

    agent берётся из AGENT_NAME env. Возвращает '✓ decision #<id> logged'.
    """
    try:
        dl = await _get_decision_log()
        id_ = await dl.append(
            agent=AGENT_NAME,
            category=category,
            chosen=chosen,
            alternatives=alternatives,
            reason=reason if reason else "unspecified",
            task_id=task_id,
        )
        return f"✓ decision #{id_} logged"
    except Exception as exc:
        log.exception("log_decision failed")
        return f"✗ decision log failed: {exc}"


_context_store: "ContextStore | None" = None
_context_store_lock = asyncio.Lock()


async def _get_context_store() -> "ContextStore":
    global _context_store
    async with _context_store_lock:
        if _context_store is not None:
            return _context_store
        from core.context_store import ContextStore
        loop = asyncio.get_running_loop()
        store = ContextStore(claudeorch_dir() / "context.duckdb")
        await loop.run_in_executor(None, store.initialize)
        _context_store = store
        return _context_store


@server.tool()
async def get_relevant_context(query: str, k: int = 5) -> str:
    """Найти релевантные фрагменты из памяти этого агента.

    Возвращает plain-text dump: [source] text... по одному чанку на блок.
    """
    try:
        store = await _get_context_store()
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, store.search, AGENT_NAME, query, k)
        if not results:
            return "(no relevant context)"
        blocks = [
            f"[{r['source']} score={r['score']:.2f}]\n{r['text']}" for r in results
        ]
        return "\n\n---\n\n".join(blocks)
    except Exception as exc:
        log.exception("get_relevant_context failed")
        return f"(context retrieval failed: {exc})"


@server.tool()
async def reindex_my_context() -> str:
    """Переиндексировать свой memory-файл (вызвать после обновления памяти)."""
    try:
        store = await _get_context_store()
        loop = asyncio.get_running_loop()
        project_root = Path(__file__).resolve().parents[1]
        memory_root = project_root / "memory"
        count = await loop.run_in_executor(
            None, store.reindex_agent, AGENT_NAME, memory_root
        )
        return f"reindexed {AGENT_NAME} ({count} chunks)"
    except Exception as exc:
        log.exception("reindex_my_context failed")
        return f"reindex failed: {exc}"


if __name__ == "__main__":
    server.run()
