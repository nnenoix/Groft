"""Rotation for append-only memory logs.

Phase 16: session-log.md grows without bound as every subagent call appends
a block. Without rotation, loading memory into context gets heavier each
session and eventually bloats the start-of-conversation prompt.

Policy: when session-log.md has more than `keep` blocks after the header,
cut the oldest `overflow` blocks into a timestamped archive file under
memory/archive/. The live file stays at exactly `keep` blocks.

Archives are plain markdown (not pruned, not summarized) so ContextStore
can index them via the normal FTS pipeline and get_relevant_context still
reaches old content when relevant.

shared.md is not rotated: notes are small, high-value, and manually curated.
current-plan.md is overwritten, not appended.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_KEEP = 50
ARCHIVE_DIRNAME = "archive"
_BLOCK_SEP = "\n---\n\n"


def _split_header_and_blocks(text: str) -> tuple[str, list[str]]:
    """Session-log layout is: header, then one block per subagent completion
    separated by '\n---\n\n'. Header ends at the first '---' on its own line
    followed by blank — i.e. at the first block separator.

    Returns (header_text_with_trailing_sep, [block_text, ...]).
    Blocks do NOT include the trailing separator.
    """
    marker = "\n---\n\n"
    first = text.find(marker)
    if first == -1:
        return text, []
    header = text[: first + len(marker)]
    rest = text[first + len(marker) :]
    if not rest.strip():
        return header, []
    blocks = [b.strip() for b in rest.split(marker) if b.strip()]
    return header, blocks


def _reassemble(header: str, blocks: list[str]) -> str:
    if not blocks:
        return header
    body = _BLOCK_SEP.join(blocks) + _BLOCK_SEP
    return header + body


def _archive_path(archive_dir: Path, now: datetime | None = None) -> Path:
    """Build a unique archive filename. Microseconds included so back-to-back
    rotations in the same second don't collide and overwrite."""
    ts = now or datetime.now(timezone.utc)
    stamp = ts.strftime("%Y-%m-%dT%H-%M-%S") + f"-{ts.microsecond:06d}Z"
    candidate = archive_dir / f"session-log-{stamp}.md"
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        alt = archive_dir / f"session-log-{stamp}-{i}.md"
        if not alt.exists():
            return alt
        i += 1


def rotate_session_log(
    memory_root: Path,
    *,
    keep: int = DEFAULT_KEEP,
    now: datetime | None = None,
) -> dict:
    """If session-log.md has more than `keep` blocks, move the overflow
    (oldest) blocks into memory/archive/session-log-<timestamp>.md.

    Returns {"rotated": bool, "moved": int, "archive": Optional[str],
             "remaining": int}.
    Idempotent: calling on a file already within threshold is a no-op.
    """
    log_path = memory_root / "session-log.md"
    if not log_path.exists():
        return {"rotated": False, "moved": 0, "archive": None, "remaining": 0}

    text = log_path.read_text(encoding="utf-8")
    header, blocks = _split_header_and_blocks(text)

    if len(blocks) <= keep:
        return {
            "rotated": False,
            "moved": 0,
            "archive": None,
            "remaining": len(blocks),
        }

    overflow = len(blocks) - keep
    old_blocks = blocks[:overflow]
    kept_blocks = blocks[overflow:]

    archive_dir = memory_root / ARCHIVE_DIRNAME
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = _archive_path(archive_dir, now=now)
    archive_header = (
        "# Archived session log blocks\n\n"
        f"Rotated from session-log.md at "
        f"{(now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')}. "
        f"{overflow} block(s).\n\n---\n\n"
    )
    target.write_text(
        _reassemble(archive_header, old_blocks), encoding="utf-8"
    )
    log_path.write_text(_reassemble(header, kept_blocks), encoding="utf-8")

    return {
        "rotated": True,
        "moved": overflow,
        "archive": str(target),
        "remaining": len(kept_blocks),
    }


def count_session_log_blocks(memory_root: Path) -> int:
    """Cheap block count — used by the ingest hook to decide whether to
    even call rotate_session_log."""
    log_path = memory_root / "session-log.md"
    if not log_path.exists():
        return 0
    text = log_path.read_text(encoding="utf-8")
    _, blocks = _split_header_and_blocks(text)
    return len(blocks)
