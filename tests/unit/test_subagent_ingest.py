"""Unit tests for core.subagent_ingest (Phase 17: markdown-only)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.subagent_ingest import ingest_report  # noqa: E402


@pytest.mark.asyncio
async def test_ingest_writes_session_log_block(tmp_path: Path) -> None:
    mem = tmp_path / "memory"

    result = await ingest_report(
        did="fix auth middleware",
        changed_files=["core/auth.py", "tests/test_auth.py"],
        decisions=[
            {
                "category": "security",
                "chosen": "session-cookie",
                "alternatives": ["jwt"],
                "reason": "simpler invalidation",
            }
        ],
        questions=["Should we rotate on login?"],
        memory_notes=["Auth uses httpOnly session cookie by default"],
        memory_root=mem,
    )

    assert len(result["decisions_recorded"]) == 1
    assert "security" in result["decisions_recorded"][0]
    assert "session-cookie" in result["decisions_recorded"][0]

    log_content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "fix auth middleware" in log_content
    assert "core/auth.py" in log_content
    assert "[security] session-cookie" in log_content
    assert "alt: jwt" in log_content
    assert "simpler invalidation" in log_content
    assert "Should we rotate on login?" in log_content
    assert "Auth uses httpOnly session cookie by default" in log_content

    shared = (mem / "shared.md").read_text(encoding="utf-8")
    assert "subagent: fix auth middleware" in shared
    assert "Auth uses httpOnly session cookie by default" in shared


@pytest.mark.asyncio
async def test_ingest_appends_not_overwrites(tmp_path: Path) -> None:
    mem = tmp_path / "memory"

    await ingest_report(did="first task", memory_root=mem)
    await ingest_report(did="second task", memory_root=mem)

    content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "first task" in content
    assert "second task" in content
    assert content.count("## ") >= 2


@pytest.mark.asyncio
async def test_ingest_skips_malformed_decisions(tmp_path: Path) -> None:
    mem = tmp_path / "memory"

    result = await ingest_report(
        did="mixed decisions",
        decisions=[
            {"category": "arch", "chosen": "A", "reason": "good"},
            {"category": "arch"},  # missing chosen — skipped
            "not a dict",  # not a dict — skipped
            {"category": "arch", "chosen": "B", "reason": "also good"},
        ],
        memory_root=mem,
    )

    assert len(result["decisions_recorded"]) == 2
    log_content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "[arch] A" in log_content
    assert "[arch] B" in log_content


@pytest.mark.asyncio
async def test_ingest_appender_is_ignored_for_compat(tmp_path: Path) -> None:
    """decision_appender argument is accepted but has no effect post Phase 17."""
    mem = tmp_path / "memory"

    async def appender(**kwargs):  # pragma: no cover — must not be called
        raise AssertionError("appender should not be called")

    result = await ingest_report(
        did="no appender",
        decisions=[{"category": "x", "chosen": "y", "reason": "z"}],
        decision_appender=appender,
        memory_root=mem,
    )
    assert len(result["decisions_recorded"]) == 1


@pytest.mark.asyncio
async def test_ingest_no_notes_no_shared_write(tmp_path: Path) -> None:
    """memory/shared.md should not appear if no memory_notes."""
    mem = tmp_path / "memory"
    await ingest_report(did="bare task", memory_notes=None, memory_root=mem)
    assert not (mem / "shared.md").exists()


@pytest.mark.asyncio
async def test_ingest_preserves_existing_shared(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir(parents=True)
    (mem / "shared.md").write_text(
        "# Shared Memory\n\nExisting content here.\n", encoding="utf-8"
    )
    await ingest_report(
        did="add note",
        memory_notes=["new observation"],
        memory_root=mem,
    )
    content = (mem / "shared.md").read_text(encoding="utf-8")
    assert "Existing content here." in content
    assert "new observation" in content
