"""Markdown-backed context search.

Historically this module wrapped DuckDB FTS to rank memory chunks by BM25.
After Phase 17 the DuckDB layer was retired — memory is small enough that
a plain file walk + token scoring is indistinguishable from FTS for the
solo-opus usage pattern, and removing the dependency cuts ~200 LOC plus a
multi-megabyte runtime dep.

API is preserved: `ContextStore.initialize` / `reindex_agent` / `search` /
`close`. `initialize` and `close` are now no-ops. `reindex_agent` returns
the would-be chunk count so callers that log "indexed N chunks" still do
something meaningful. `search` walks memory_root on every call; caching
isn't worth it at this corpus size.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip())[:60].strip("-")


def _chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Split by '\\n---\\n' first; if section >max_chars, split by blank lines.
    If still too large, hard-split at max_chars boundaries."""
    sections = re.split(r"\n---\n", text)
    result = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= max_chars:
            result.append(sec)
        else:
            parts = re.split(r"\n\n+", sec)
            current = ""
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if current and len(current) + len(part) + 2 > max_chars:
                    result.append(current)
                    current = part
                else:
                    current = (current + "\n\n" + part).strip() if current else part
            if current:
                result.append(current)
    final: list[str] = []
    for chunk in result:
        if len(chunk) <= max_chars:
            final.append(chunk)
        else:
            pos = 0
            while pos < len(chunk):
                final.append(chunk[pos : pos + max_chars])
                pos += max_chars
    return final or [text[:max_chars]]


_TOKEN_RE = re.compile(r"[a-zа-яё0-9_]+", re.IGNORECASE)


def _tokenize(query: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(query) if len(t) > 1]


def _score_chunk(chunk_lower: str, tokens: list[str]) -> float:
    score = 0.0
    for tok in tokens:
        count = chunk_lower.count(tok)
        if count:
            score += 1.0 + 0.1 * (count - 1)
    return score


@dataclass
class _Chunk:
    source: str
    text: str


def _collect_chunks(memory_root: Path) -> list[_Chunk]:
    if not memory_root.exists():
        return []
    top_level = sorted(
        p for p in memory_root.glob("*.md") if not p.name.startswith(".")
    )
    archive_dir = memory_root / "archive"
    archived = (
        sorted(p for p in archive_dir.glob("*.md") if not p.name.startswith("."))
        if archive_dir.is_dir()
        else []
    )
    chunks: list[_Chunk] = []
    for path in top_level + archived:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("failed to read memory file %s: %s", path, exc)
            continue
        rel = path.relative_to(memory_root)
        for idx, chunk in enumerate(_chunk_text(text)):
            chunk = chunk.strip()
            if not chunk:
                continue
            first_line = chunk.splitlines()[0].lstrip("#").strip()
            slug = _slugify(first_line) if first_line else str(idx)
            source = f"memory/{rel.as_posix()}#{slug}"
            chunks.append(_Chunk(source=source, text=chunk))
    return chunks


class ContextStore:
    """Markdown-only memory searcher.

    Signature accepts `db_path` for backward compatibility — it is
    reinterpreted as a hint for the memory root (parent-of-parent, since
    DuckDB files used to live at `.claudeorch/context.duckdb` next to the
    project). Callers that want to be explicit should set memory_root.
    """

    def __init__(self, db_path: Path, memory_root: Path | None = None) -> None:
        self._memory_root = memory_root
        self._db_path_hint = db_path  # retained for logs/debugging; unused

    def initialize(self) -> None:
        return None

    def reindex_agent(self, agent: str, memory_root: Path) -> int:
        """No index to rebuild — just remember the root and report count.

        Kept to preserve the MCP `reindex_my_context` contract; in
        markdown mode it is effectively a count probe.
        """
        self._memory_root = memory_root
        return len(_collect_chunks(memory_root))

    def search(self, agent: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        if self._memory_root is None:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        chunks = _collect_chunks(self._memory_root)
        scored: list[tuple[float, _Chunk]] = []
        for chunk in chunks:
            score = _score_chunk(chunk.text.lower(), tokens)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results: list[dict[str, Any]] = []
        for idx, (score, chunk) in enumerate(scored[:k]):
            results.append({
                "id": idx,
                "agent": "_shared",
                "source": chunk.source,
                "text": chunk.text,
                "score": score,
            })
        return results

    def close(self) -> None:
        return None
