"""Unit tests for ContextStore (markdown grep search)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context_store import (  # noqa: E402
    ContextStore,
    _chunk_text,
    _collect_chunks,
    _tokenize,
)

SAMPLE_MD = """# Shared Memory

---

## Watchdog skip_liveness

The watchdog has a skip_liveness flag for opus. When skip_liveness=True,
the agent is never marked stuck or restarted.

---

## Markdown search

Memory lives in plain markdown. grep is good enough for solo-opus sized
corpora.

---

## Telegram bridge

The telegram bridge hot-boots on configure endpoint.
build_and_start_bridge is the key function.
"""


@pytest.fixture
def store(tmp_path: Path) -> ContextStore:
    s = ContextStore(tmp_path / "unused_db_path")
    s.initialize()
    return s


def test_initialize_is_noop(tmp_path: Path) -> None:
    s = ContextStore(tmp_path / "whatever")
    s.initialize()
    s.initialize()  # second call must not raise
    # with no memory_root, search returns nothing
    assert s.search("opus", "anything", k=5) == []
    s.close()


def test_reindex_returns_chunk_count(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")

    count = store.reindex_agent("opus", mem)
    assert count >= 3  # 3 sections


def test_search_finds_chunk_by_token(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")
    store.reindex_agent("opus", mem)

    results = store.search("opus", "watchdog skip_liveness", k=3)
    assert len(results) >= 1
    top = results[0]
    assert "watchdog" in top["text"].lower() or "skip_liveness" in top["text"].lower()
    assert top["agent"] == "_shared"
    assert top["source"].startswith("memory/shared.md#")
    assert top["score"] > 0


def test_search_empty_query_returns_empty(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")
    store.reindex_agent("opus", mem)

    assert store.search("opus", "", k=3) == []
    assert store.search("opus", "   ", k=3) == []


def test_search_picks_up_archive_subdir(store: ContextStore, tmp_path: Path) -> None:
    """Archive files under memory/archive/ must be searchable."""
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
    store.reindex_agent("opus", mem)

    results = store.search("opus", "forgotten_keyword_xyz", k=5)
    assert len(results) >= 1
    assert any(
        "archive" in r["source"] and "forgotten_keyword_xyz" in r["text"]
        for r in results
    )


def test_search_results_capped_at_k(store: ContextStore, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    blocks = ["---", "## header\nthe_token appears here"]
    for i in range(10):
        blocks.append(f"## block {i}\nthe_token shows up block {i}")
        blocks.append("---")
    (mem / "shared.md").write_text("\n".join(blocks), encoding="utf-8")
    store.reindex_agent("opus", mem)

    results = store.search("opus", "the_token", k=3)
    assert len(results) == 3


def test_tokenize_skips_one_char_and_symbols() -> None:
    toks = _tokenize("the a skip_liveness / 42 !")
    assert "the" in toks
    assert "a" not in toks  # single-char stopword-ish
    assert "skip_liveness" in toks
    assert "42" in toks


def test_collect_chunks_sorted_deterministic(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "shared.md").write_text(SAMPLE_MD, encoding="utf-8")
    (mem / "session-log.md").write_text(
        "# Session Log\n\n---\n\n## task one\n- Changed: a.py", encoding="utf-8"
    )
    first = _collect_chunks(mem)
    second = _collect_chunks(mem)
    assert len(first) == len(second)
    assert [c.source for c in first] == [c.source for c in second]


def test_chunk_text_respects_max_chars() -> None:
    long_section = "word " * 400  # ~2000 chars
    chunks = _chunk_text(long_section, max_chars=1500)
    for chunk in chunks:
        assert len(chunk) <= 1500 + 50  # small tolerance for word boundaries
