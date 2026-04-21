"""End-to-end: ingest 60 subagent reports → rotation kicks in → the old
blocks land in archive/ → ContextStore finds them via search.

This is the Phase 16 durability contract: bloat gets bounded without
losing retrievability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context_store import ContextStore  # noqa: E402
from core.memory_rotation import count_session_log_blocks  # noqa: E402
from core.subagent_ingest import ingest_report  # noqa: E402


@pytest.mark.asyncio
async def test_rotation_preserves_searchability(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    keep = 10
    total = 25
    unique_marker = "stegosaurus_archaeopteryx_marker"

    for i in range(total):
        note = (
            f"fact {i}: ordinary observation" if i != 2
            else f"fact 2 contains {unique_marker}"
        )
        await ingest_report(
            did=f"task number {i}",
            memory_notes=[note],
            memory_root=mem,
            rotate_keep=keep,
        )

    assert count_session_log_blocks(mem) == keep
    archive_dir = mem / "archive"
    assert archive_dir.is_dir()
    archives = list(archive_dir.glob("session-log-*.md"))
    assert archives, "rotation must produce at least one archive"

    archived_content = "\n".join(a.read_text(encoding="utf-8") for a in archives)
    assert unique_marker in archived_content, (
        "marker should have rotated out of live log into archive"
    )

    live_content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert unique_marker not in live_content

    store = ContextStore(tmp_path / "ctx_store_hint", memory_root=mem)
    store.initialize()
    try:
        count = store.reindex_agent("opus", mem)
        assert count > keep, "archive files must contribute chunks"

        results = store.search("opus", unique_marker, k=5)
        assert len(results) >= 1, "marker from archived block must be searchable"
        # Marker lives in two places: shared.md (live, aggregated) and the
        # rotated archive block. The contract we care about is that the
        # archived copy is reachable — not that it wins ranking.
        assert any(
            "archive" in r["source"] and unique_marker in r["text"]
            for r in results
        ), f"no archive hit in results: {[r['source'] for r in results]}"
    finally:
        store.close()
