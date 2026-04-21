"""Unit tests for ContextStore (DuckDB FTS-backed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context_store import ContextStore, _chunk_text  # noqa: E402

SAMPLE_MD = """# Shared Memory

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
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")

    count = store.reindex_agent("opus", mem)
    assert count >= 3  # 3 sections

    results = store.search("opus", "watchdog skip_liveness", k=3)
    assert len(results) >= 1
    top = results[0]
    assert "watchdog" in top["text"].lower() or "skip_liveness" in top["text"].lower()
    assert top["agent"] == "_shared"
    assert top["source"].startswith("memory/shared.md#")
    assert top["score"] is not None


def test_reindex_replaces_old_chunks(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")

    store.reindex_agent("opus", mem)
    first_count = store._conn.execute(
        "SELECT count(*) FROM chunks WHERE agent='_shared'"
    ).fetchone()[0]
    assert first_count >= 3

    # Reindex with only 1 section — count must shrink, not duplicate.
    (mem / "shared.md").write_text(
        "# Short\n\n---\n\nOnly one chunk here.", encoding="utf-8"
    )
    store.reindex_agent("opus", mem)
    second_count = store._conn.execute(
        "SELECT count(*) FROM chunks WHERE agent='_shared'"
    ).fetchone()[0]
    assert second_count < first_count
    assert second_count >= 1


def test_reindex_picks_up_archive_subdir(store: ContextStore, tmp_path: Path) -> None:
    """Phase 16 contract: files under memory/archive/ must be searchable."""
    mem = tmp_path / "memory"
    (mem / "archive").mkdir(parents=True)
    (mem / "shared.md").write_text(
        "# Shared\n\n---\n\nLive note about pandas.", encoding="utf-8"
    )
    (mem / "archive" / "session-log-2026-01-01.md").write_text(
        "# Archived blocks\n\n---\n\n"
        "## 2026-01-01 — ancient task\n"
        "- Notes:\n  - forgotten_keyword_xyz appears only here",
        encoding="utf-8",
    )

    count = store.reindex_agent("opus", mem)
    assert count >= 2

    results = store.search("opus", "forgotten_keyword_xyz", k=5)
    assert len(results) >= 1
    assert any(
        "archive" in r["source"] and "forgotten_keyword_xyz" in r["text"]
        for r in results
    )


def test_reindex_is_deterministic_across_runs(store: ContextStore, tmp_path: Path) -> None:
    """Sorted file collection → same chunk count on repeat reindex."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")
    (mem / "session-log.md").write_text(
        "# Session Log\n\n---\n\n## task one\n- Changed: a.py", encoding="utf-8"
    )

    c1 = store.reindex_agent("opus", mem)
    c2 = store.reindex_agent("opus", mem)
    assert c1 == c2
    assert c1 >= 4


def test_chunk_text_respects_max_chars() -> None:
    long_section = "word " * 400  # ~2000 chars
    chunks = _chunk_text(long_section, max_chars=1500)
    for chunk in chunks:
        assert len(chunk) <= 1500 + 50  # small tolerance for word boundaries
