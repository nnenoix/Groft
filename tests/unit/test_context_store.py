"""Unit tests for ContextStore (DuckDB FTS-backed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context_store import ContextStore, _chunk_text  # noqa: E402

SAMPLE_MD = """# Backend Dev Memory

---

## Watchdog skip_liveness

The watchdog has a skip_liveness flag for opus. When skip_liveness=True,
the agent is never marked stuck or restarted.

---

## DuckDB usage

We use DuckDB for decisions, messages, and context storage.
All writes go through asyncio executor to avoid blocking.

---

## Telegram bridge

The telegram bridge hot-boots on configure endpoint.
build_and_start_bridge is the key function.
"""


@pytest.fixture
def store(tmp_path: Path) -> ContextStore:
    s = ContextStore(tmp_path / "test_ctx.duckdb")
    s.initialize()
    yield s
    s.close()


def test_initialize_idempotent(tmp_path: Path) -> None:
    s = ContextStore(tmp_path / "ctx.duckdb")
    s.initialize()
    s.initialize()  # second call must not raise
    # Table exists
    rows = s._conn.execute("SELECT count(*) FROM chunks").fetchone()
    assert rows[0] == 0
    s.close()


def test_reindex_and_search_roundtrip(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "backend-dev.md").write_text(SAMPLE_MD, encoding="utf-8")

    count = store.reindex_agent("backend-dev", mem)
    assert count >= 3  # 3 sections

    results = store.search("backend-dev", "watchdog skip_liveness", k=3)
    assert len(results) >= 1
    top = results[0]
    assert "watchdog" in top["text"].lower() or "skip_liveness" in top["text"].lower()
    assert top["agent"] == "backend-dev"
    assert top["score"] is not None


def test_reindex_replaces_old_chunks(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "backend-dev.md").write_text(SAMPLE_MD, encoding="utf-8")

    store.reindex_agent("backend-dev", mem)
    first_count = store._conn.execute(
        "SELECT count(*) FROM chunks WHERE agent='backend-dev'"
    ).fetchone()[0]
    assert first_count >= 3

    # Reindex with only 1 section
    (mem / "backend-dev.md").write_text(
        "# Short\n\n---\n\nOnly one chunk here.", encoding="utf-8"
    )
    store.reindex_agent("backend-dev", mem)
    second_count = store._conn.execute(
        "SELECT count(*) FROM chunks WHERE agent='backend-dev'"
    ).fetchone()[0]
    assert second_count < first_count
    assert second_count >= 1


def test_search_respects_agent_and_shared(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "agent-a.md").write_text(
        "# Agent A\n\nThis is agent-a specific content about pandas.", encoding="utf-8"
    )
    (mem / "agent-b.md").write_text(
        "# Agent B\n\nThis is agent-b specific content about numpy.", encoding="utf-8"
    )
    (mem / "shared.md").write_text(
        "# Shared\n\nThis is shared content about common tools.", encoding="utf-8"
    )

    store.reindex_agent("agent-a", mem)
    store.reindex_agent("agent-b", mem)
    store.reindex_agent("_shared", mem)

    results = store.search("agent-a", "pandas", k=10)
    agents_found = {r["agent"] for r in results}
    # Should only see agent-a and _shared, never agent-b
    assert "agent-b" not in agents_found
    assert "agent-a" in agents_found or "_shared" in agents_found


def test_chunk_text_respects_max_chars() -> None:
    long_section = "word " * 400  # ~2000 chars
    chunks = _chunk_text(long_section, max_chars=1500)
    for chunk in chunks:
        assert len(chunk) <= 1500 + 50  # small tolerance for word boundaries
