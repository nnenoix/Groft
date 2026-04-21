"""Unit tests for core.subagent_ingest."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.subagent_ingest import ingest_report  # noqa: E402


class _FakeAppender:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_id = 100

    async def __call__(self, **kwargs: Any) -> int:
        self.calls.append(kwargs)
        self.next_id += 1
        return self.next_id


@pytest.mark.asyncio
async def test_ingest_writes_session_log_block(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    appender = _FakeAppender()

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
        decision_appender=appender,
        memory_root=mem,
    )

    assert result["decision_ids"] == [101]
    assert len(appender.calls) == 1
    assert appender.calls[0]["category"] == "security"
    assert appender.calls[0]["reason"] == "simpler invalidation"

    log_content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "fix auth middleware" in log_content
    assert "core/auth.py" in log_content
    assert "#101" in log_content
    assert "Should we rotate on login?" in log_content
    assert "Auth uses httpOnly session cookie by default" in log_content

    shared = (mem / "shared.md").read_text(encoding="utf-8")
    assert "subagent: fix auth middleware" in shared
    assert "Auth uses httpOnly session cookie by default" in shared


@pytest.mark.asyncio
async def test_ingest_appends_not_overwrites(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    appender = _FakeAppender()

    await ingest_report(
        did="first task", decision_appender=appender, memory_root=mem
    )
    await ingest_report(
        did="second task", decision_appender=appender, memory_root=mem
    )

    content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "first task" in content
    assert "second task" in content
    assert content.count("## ") >= 2


@pytest.mark.asyncio
async def test_ingest_skips_malformed_decisions(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    appender = _FakeAppender()

    result = await ingest_report(
        did="mixed decisions",
        decisions=[
            {"category": "arch", "chosen": "A", "reason": "good"},
            {"category": "arch"},  # missing chosen — skipped
            "not a dict",  # not a dict — skipped
            {"category": "arch", "chosen": "B", "reason": "also good"},
        ],
        decision_appender=appender,
        memory_root=mem,
    )

    assert len(result["decision_ids"]) == 2
    assert len(appender.calls) == 2


@pytest.mark.asyncio
async def test_ingest_no_decision_appender(tmp_path: Path) -> None:
    """Without appender, decisions are just dropped silently."""
    mem = tmp_path / "memory"
    result = await ingest_report(
        did="no appender",
        decisions=[{"category": "x", "chosen": "y", "reason": "z"}],
        decision_appender=None,
        memory_root=mem,
    )
    assert result["decision_ids"] == []


@pytest.mark.asyncio
async def test_ingest_no_notes_no_shared_write(tmp_path: Path) -> None:
    """memory/shared.md should not appear if no memory_notes."""
    mem = tmp_path / "memory"
    appender = _FakeAppender()
    await ingest_report(
        did="bare task",
        memory_notes=None,
        decision_appender=appender,
        memory_root=mem,
    )
    assert not (mem / "shared.md").exists()


@pytest.mark.asyncio
async def test_ingest_preserves_existing_shared(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir(parents=True)
    (mem / "shared.md").write_text(
        "# Shared Memory\n\nExisting content here.\n", encoding="utf-8"
    )
    appender = _FakeAppender()
    await ingest_report(
        did="add note",
        memory_notes=["new observation"],
        decision_appender=appender,
        memory_root=mem,
    )
    content = (mem / "shared.md").read_text(encoding="utf-8")
    assert "Existing content here." in content
    assert "new observation" in content
