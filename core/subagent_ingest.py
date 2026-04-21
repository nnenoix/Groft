from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_decision_line(dec: dict[str, Any]) -> str | None:
    category = dec.get("category")
    chosen = dec.get("chosen")
    if not isinstance(category, str) or not isinstance(chosen, str):
        return None
    reason = dec.get("reason")
    if not isinstance(reason, str) or not reason:
        reason = "unspecified"
    alternatives = dec.get("alternatives")
    alt_str = ""
    if isinstance(alternatives, list) and alternatives:
        alt_str = f" (alt: {', '.join(str(a) for a in alternatives)})"
    return f"  - [{category}] {chosen}{alt_str} — {reason}"


def _session_log_block(
    ts: str,
    did: str,
    changed_files: list[str],
    decision_lines: list[str],
    questions: list[str],
    notes: list[str],
) -> str:
    parts = [f"## {ts} — {did.strip() or '(no summary)'}"]
    if changed_files:
        parts.append(f"- Changed: {', '.join(changed_files)}")
    if decision_lines:
        parts.append("- Decisions:")
        parts.extend(decision_lines)
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
    decision_appender: Any = None,
    memory_root: Path,
    task_id: str | None = None,
    rotate_keep: int | None = None,
) -> dict[str, Any]:
    """Persist a subagent report to session-log.md + shared.md.

    Phase 17: DuckDB decision log retired. Decisions are written inline
    into the session-log block as bullet lines — searchable via
    get_relevant_context's markdown grep. The `decision_appender` argument
    is accepted and ignored for backward compatibility with old callers.

    Returns: {"session_log": path, "decisions_recorded": [line, ...],
    "timestamp": iso, "rotation": dict | None}.

    If rotate_keep is set and session-log.md now has more blocks than that,
    the oldest overflow is moved into memory/archive/ via
    memory_rotation.rotate_session_log.
    """
    ts = _iso_now()
    changed = list(changed_files or [])
    qs = list(questions or [])
    notes = list(memory_notes or [])
    decision_list = list(decisions or [])

    decision_lines: list[str] = []
    for dec in decision_list:
        if not isinstance(dec, dict):
            continue
        line = _format_decision_line(dec)
        if line is None:
            log.warning("skipping malformed decision: %r", dec)
            continue
        decision_lines.append(line)

    session_log_path = memory_root / "session-log.md"
    _ensure_session_log(session_log_path)
    block = _session_log_block(ts, did, changed, decision_lines, qs, notes)
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
        "decisions_recorded": decision_lines,
        "timestamp": ts,
        "rotation": rotation,
    }
