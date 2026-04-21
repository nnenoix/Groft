"""Auto-learn: persist user corrections as feedback memories.

Rule #6 of the Groft charter: opus must learn from user corrections without
the user editing CLAUDE.md by hand. When opus detects a correction (explicit
"don't", "wrong", or an implicit complaint), it calls save_feedback_rule()
which writes a feedback-type memory file and indexes it in MEMORY.md.

The memory format matches Claude Code's built-in auto-memory (frontmatter +
body). Files live under the user's per-project memory dir — NOT project
memory — because corrections are about how to collaborate with *this* user,
not about the codebase.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

MEMORY_INDEX = "MEMORY.md"


def _slugify(text: str, max_len: int = 50) -> str:
    """Turn a rule sentence into a safe filename stem."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9Ѐ-ӿ\s_-]+", "", s)
    s = re.sub(r"\s+", "_", s)
    s = s[:max_len].strip("_-")
    return s or "rule"


def _iso_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _render_memory(
    *,
    name: str,
    description: str,
    rule: str,
    why: str,
    how_to_apply: str,
) -> str:
    parts = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "type: feedback",
        "---",
        "",
        rule.strip(),
        "",
        f"**Why:** {why.strip()}",
        "",
        f"**How to apply:** {how_to_apply.strip()}",
        "",
    ]
    return "\n".join(parts)


def _index_line(title: str, filename: str, hook: str) -> str:
    return f"- [{title}]({filename}) — {hook}"


def _ensure_memory_index(memory_root: Path) -> Path:
    idx = memory_root / MEMORY_INDEX
    if not idx.exists():
        memory_root.mkdir(parents=True, exist_ok=True)
        idx.write_text("", encoding="utf-8")
    return idx


def _append_index_if_missing(idx_path: Path, line: str, filename: str) -> bool:
    """Append `line` to index unless a line already references `filename`.

    Returns True if a new line was appended.
    """
    existing = idx_path.read_text(encoding="utf-8") if idx_path.exists() else ""
    if f"]({filename})" in existing:
        return False
    sep = "" if existing.endswith("\n") or existing == "" else "\n"
    idx_path.write_text(existing + sep + line + "\n", encoding="utf-8")
    return True


def save_feedback_rule(
    *,
    rule: str,
    why: str,
    how_to_apply: str,
    memory_root: Path,
    name: str | None = None,
    description: str | None = None,
    filename: str | None = None,
) -> dict:
    """Persist a correction as a feedback-type memory + index line.

    Returns {"path": str, "indexed": bool, "created": bool}.
    Idempotent on filename: re-calls with same filename overwrite the body
    but do not duplicate the index line.
    """
    if not rule.strip():
        raise ValueError("rule text is required")
    if not why.strip():
        raise ValueError("why is required — without it, future-you can't judge edge cases")

    stem = _slugify(filename) if filename else f"feedback_{_slugify(rule)}"
    fname = f"{stem}.md"
    auto_name = name or rule.strip().rstrip(".")
    auto_desc = description or f"{rule.strip()[:120]} (recorded {_iso_date()})"

    memory_root.mkdir(parents=True, exist_ok=True)
    target = memory_root / fname
    was_new = not target.exists()
    target.write_text(
        _render_memory(
            name=auto_name,
            description=auto_desc,
            rule=rule,
            why=why,
            how_to_apply=how_to_apply,
        ),
        encoding="utf-8",
    )

    idx = _ensure_memory_index(memory_root)
    hook = rule.strip().splitlines()[0]
    if len(hook) > 120:
        hook = hook[:117] + "..."
    indexed = _append_index_if_missing(
        idx,
        _index_line(auto_name[:80], fname, hook),
        fname,
    )

    return {
        "path": str(target),
        "indexed": indexed,
        "created": was_new,
    }
