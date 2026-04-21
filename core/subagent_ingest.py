from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)


DecisionAppender = Callable[..., Awaitable[int]]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_log_block(
    ts: str,
    did: str,
    changed_files: list[str],
    decision_ids: list[int],
    questions: list[str],
    notes: list[str],
) -> str:
    parts = [f"## {ts} — {did.strip() or '(no summary)'}"]
    if changed_files:
        parts.append(f"- Changed: {', '.join(changed_files)}")
    if decision_ids:
        parts.append(f"- Decisions: {', '.join(f'#{i}' for i in decision_ids)}")
    if questions:
        joined = " / ".join(q.strip() for q in questions if q.strip())
        if joined:
            parts.append(f"- Questions: {joined}")
    if notes:
        parts.append("- Notes:")
        for note in notes:
            parts.append(f"  - {note.strip()}")
    return "\n".join(parts) + "\n\n---\n\n"


def _shared_memory_block(ts: str, did: str, notes: list[str]) -> str:
    if not notes:
        return ""
    header = f"## {ts} — subagent: {did.strip() or '(no summary)'}"
    lines = [header] + [f"- {n.strip()}" for n in notes if n.strip()]
    return "\n".join(lines) + "\n\n"


def _ensure_session_log(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Session Log\n\nAppend-only record of subagent completions.\n\n---\n\n",
        encoding="utf-8",
    )


async def ingest_report(
    *,
    did: str,
    changed_files: list[str] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    questions: list[str] | None = None,
    memory_notes: list[str] | None = None,
    agent: str = "opus",
    decision_appender: DecisionAppender | None = None,
    memory_root: Path,
    task_id: str | None = None,
    rotate_keep: int | None = None,
) -> dict[str, Any]:
    """Persist a subagent report. Returns {"session_log": path, "decision_ids": [...]}.

    Pure I/O — no MCP-level wiring, no locks. Caller supplies the decision
    appender (normally `DecisionLog.append`). memory_root is the project's
    memory/ directory; session-log.md and shared.md live inside it.

    If rotate_keep is set and session-log.md now has more blocks than that,
    the oldest overflow is moved into memory/archive/ via
    memory_rotation.rotate_session_log. Pass None to skip rotation (e.g.
    for tests that want a flat log).
    """
    ts = _iso_now()
    changed = list(changed_files or [])
    qs = list(questions or [])
    notes = list(memory_notes or [])
    decision_list = list(decisions or [])

    decision_ids: list[int] = []
    if decision_list and decision_appender is not None:
        for dec in decision_list:
            if not isinstance(dec, dict):
                continue
            category = dec.get("category")
            chosen = dec.get("chosen")
            if not isinstance(category, str) or not isinstance(chosen, str):
                log.warning("skipping malformed decision: %r", dec)
                continue
            alternatives = dec.get("alternatives")
            if alternatives is not None and not isinstance(alternatives, list):
                alternatives = None
            reason = dec.get("reason")
            if not isinstance(reason, str) or not reason:
                reason = "unspecified"
            dec_task_id = dec.get("task_id") if isinstance(dec.get("task_id"), str) else task_id
            try:
                id_ = await decision_appender(
                    agent=agent,
                    category=category,
                    chosen=chosen,
                    alternatives=alternatives,
                    reason=reason,
                    task_id=dec_task_id,
                )
                decision_ids.append(int(id_))
            except Exception:
                log.exception("decision append failed for %r", dec)

    session_log_path = memory_root / "session-log.md"
    _ensure_session_log(session_log_path)
    block = _session_log_block(ts, did, changed, decision_ids, qs, notes)
    with session_log_path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    shared_path = memory_root / "shared.md"
    shared_block = _shared_memory_block(ts, did, notes)
    if shared_block:
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        if not shared_path.exists():
            shared_path.write_text("# Shared Memory\n\n", encoding="utf-8")
        with shared_path.open("a", encoding="utf-8") as fh:
            fh.write(shared_block)

    rotation: dict[str, Any] | None = None
    if rotate_keep is not None:
        from core.memory_rotation import rotate_session_log
        try:
            rotation = rotate_session_log(memory_root, keep=rotate_keep)
        except Exception:
            log.exception("rotate_session_log failed")
            rotation = None

    return {
        "session_log": str(session_log_path),
        "decision_ids": decision_ids,
        "timestamp": ts,
        "rotation": rotation,
    }
