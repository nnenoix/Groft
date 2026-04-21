from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import duckdb

log = logging.getLogger(__name__)

_SCHEMA = """
INSTALL fts;
LOAD fts;
CREATE TABLE IF NOT EXISTS chunks (
    id BIGINT PRIMARY KEY,
    agent VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    text VARCHAR NOT NULL,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_SEQ = "CREATE SEQUENCE IF NOT EXISTS chunks_id_seq START 1;"


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
            # split by double newline
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
    # Hard-split any chunks that are still over max_chars (e.g. no separators at all)
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


class ContextStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_SEQ)
        self._conn.execute(_SCHEMA)
        # Build FTS index (overwrite=1 makes it idempotent)
        try:
            self._conn.execute(
                "PRAGMA create_fts_index('chunks', 'id', 'text', overwrite=1);"
            )
        except Exception as e:
            log.warning("FTS index creation failed (may already exist): %s", e)

    def reindex_agent(self, agent: str, memory_root: Path) -> int:
        """Reindex an agent's memory corpus.

        All markdown files directly under memory_root and under
        memory_root/archive/ are indexed as `_shared` regardless of agent
        name — there is no per-agent split in the current layout
        (solo-opus model). The `agent` argument is kept for API
        compatibility and to scope the DELETE.
        """
        assert self._conn is not None
        # Delete old chunks. The current layout indexes everything as
        # _shared, so purge that bucket plus the legacy per-agent bucket
        # if it exists.
        self._conn.execute(
            "DELETE FROM chunks WHERE agent IN (?, ?)", [agent, "_shared"]
        )

        files = self._collect_memory_files(memory_root)

        chunks_inserted = 0
        for path in files:
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                log.warning("failed to read memory file %s: %s", path, e)
                continue
            rel = path.relative_to(memory_root)
            chunks = _chunk_text(text)
            for idx, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk:
                    continue
                first_line = chunk.splitlines()[0].lstrip("#").strip()
                slug = _slugify(first_line) if first_line else str(idx)
                source = f"memory/{rel.as_posix()}#{slug}"
                chunk_id = self._conn.execute(
                    "SELECT nextval('chunks_id_seq')"
                ).fetchone()[0]
                self._conn.execute(
                    "INSERT INTO chunks (id, agent, source, text) VALUES (?, ?, ?, ?)",
                    [chunk_id, "_shared", source, chunk],
                )
                chunks_inserted += 1

        try:
            self._conn.execute(
                "PRAGMA create_fts_index('chunks', 'id', 'text', overwrite=1);"
            )
        except Exception as e:
            log.warning("FTS index rebuild failed: %s", e)

        return chunks_inserted

    @staticmethod
    def _collect_memory_files(memory_root: Path) -> list[Path]:
        """All .md files under memory_root (top level + archive/).

        Sorted for deterministic chunk IDs across reindex runs. Skips
        hidden files and anything outside the allowed subtree.
        """
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
        return top_level + archived

    def search(self, agent: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        assert self._conn is not None
        if not query.strip():
            return []
        try:
            rows = self._conn.execute(
                """
                SELECT c.id, c.agent, c.source, c.text,
                       fts_main_chunks.match_bm25(c.id, ?) AS score
                FROM chunks c
                WHERE (c.agent = ? OR c.agent = '_shared')
                  AND fts_main_chunks.match_bm25(c.id, ?) IS NOT NULL
                ORDER BY score DESC
                LIMIT ?
                """,
                [query, agent, query, k],
            ).fetchall()
        except Exception as e:
            log.warning("FTS search failed, falling back to LIKE: %s", e)
            rows = self._fallback_search(agent, query, k)
        return [
            {"id": r[0], "agent": r[1], "source": r[2], "text": r[3], "score": r[4] or 0.0}
            for r in rows
        ]

    def _fallback_search(self, agent: str, query: str, k: int) -> list[tuple]:
        """LIKE-based fallback if FTS fails."""
        assert self._conn is not None
        like = f"%{query}%"
        return self._conn.execute(
            """
            SELECT id, agent, source, text, 1.0 AS score
            FROM chunks
            WHERE (agent = ? OR agent = '_shared')
              AND text LIKE ?
            LIMIT ?
            """,
            [agent, like, k],
        ).fetchall()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                log.warning("ContextStore.close failed", exc_info=True)
            self._conn = None
