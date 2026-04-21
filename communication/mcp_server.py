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


@server.tool()
async def ingest_subagent_report(
    did: str,
    changed_files: list[str] | None = None,
    decisions: list[dict] | None = None,
    questions: list[str] | None = None,
    memory_notes: list[str] | None = None,
    task_id: str | None = None,
) -> str:
    """Записать отчёт субагента в session-log.md + DecisionLog + shared.md.

    Контракт: каждый Agent()-вызов завершается структурированным отчётом,
    который opus передаёт сюда. Ничего не теряется после смерти суба.

    - did: одно предложение «что сделал».
    - changed_files: пути изменённых файлов.
    - decisions: [{category, chosen, alternatives?, reason, task_id?}, ...]
      — каждое уходит в DecisionLog, id возвращается в session-log.
    - questions: open questions для opus.
    - memory_notes: заметки уровня «помнить всегда» — идут в shared.md.
    """
    try:
        from core.subagent_ingest import ingest_report
        dl = await _get_decision_log()
        project_root = Path(__file__).resolve().parents[1]
        result = await ingest_report(
            did=did,
            changed_files=changed_files,
            decisions=decisions,
            questions=questions,
            memory_notes=memory_notes,
            agent=AGENT_NAME,
            decision_appender=dl.append,
            memory_root=project_root / "memory",
            task_id=task_id,
        )
        dec_summary = (
            f"{len(result['decision_ids'])} decisions #"
            + ",#".join(str(i) for i in result["decision_ids"])
            if result["decision_ids"]
            else "0 decisions"
        )
        return f"✓ ingested at {result['timestamp']}; {dec_summary}"
    except Exception as exc:
        log.exception("ingest_subagent_report failed")
        return f"✗ ingest failed: {exc}"


@server.tool()
async def save_feedback_rule(
    rule: str,
    why: str,
    how_to_apply: str,
    filename: str | None = None,
) -> str:
    """Записать корректировку юзера как feedback-memory.

    Правило #6 (auto-learn): когда юзер поправил подход — сразу фиксировать
    как правило в per-project auto-memory, чтобы в следующей сессии не
    повторять ошибку. Пишет файл + строку в MEMORY.md индекс.

    - rule: что именно делать / не делать (императив, одно предложение)
    - why: причина — опишет контекст, чтобы в edge case можно было судить
    - how_to_apply: где и когда правило срабатывает
    - filename: опциональный стабильный stem (для идемпотентных апдейтов)
    """
    try:
        from core.auto_learn import save_feedback_rule as _save
        home = Path(os.environ.get("HOME", "/root"))
        memory_root = (
            home / ".claude" / "projects" / "-mnt-d-orchkerstr" / "memory"
        )
        result = _save(
            rule=rule,
            why=why,
            how_to_apply=how_to_apply,
            memory_root=memory_root,
            filename=filename,
        )
        status = "created" if result["created"] else "updated"
        return f"✓ feedback rule {status}: {Path(result['path']).name}"
    except Exception as exc:
        log.exception("save_feedback_rule failed")
        return f"✗ save_feedback_rule failed: {exc}"


@server.tool()
async def set_plan(goal: str, steps: list[str]) -> str:
    """Записать новый многошаговый план в memory/current-plan.md.

    Первый шаг сразу становится активным. Заменяет существующий план целиком.
    Нужен для правила #4: прогресс виден вместо тишины.
    """
    try:
        from core.step_planner import set_plan as _set
        project_root = Path(__file__).resolve().parents[1]
        plan = _set(goal, steps, memory_root=project_root / "memory")
        return f"✓ plan set: {plan.progress()}"
    except Exception as exc:
        log.exception("set_plan failed")
        return f"✗ set_plan failed: {exc}"


@server.tool()
async def advance_step() -> str:
    """Завершить активный шаг и перейти к следующему pending.

    Возвращает строку вида "step 3 of 7: <текст>" или "all N steps done".
    """
    try:
        from core.step_planner import advance_step as _adv
        project_root = Path(__file__).resolve().parents[1]
        plan = _adv(memory_root=project_root / "memory")
        return f"✓ advanced: {plan.progress()}"
    except Exception as exc:
        log.exception("advance_step failed")
        return f"✗ advance_step failed: {exc}"


@server.tool()
async def get_plan() -> str:
    """Показать текущий план и позицию в нём."""
    try:
        from core.step_planner import load_plan
        project_root = Path(__file__).resolve().parents[1]
        plan = load_plan(memory_root=project_root / "memory")
        if plan is None:
            return "(no current plan)"
        lines = [f"Goal: {plan.goal}", f"Progress: {plan.progress()}", ""]
        for i, step in enumerate(plan.steps, 1):
            mark = {"done": "✓", "active": "→", "pending": "·"}[step.status]
            lines.append(f"{i}. {mark} {step.text}")
        return "\n".join(lines)
    except Exception as exc:
        log.exception("get_plan failed")
        return f"✗ get_plan failed: {exc}"


if __name__ == "__main__":
    server.run()
