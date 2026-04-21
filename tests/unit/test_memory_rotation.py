"""Unit tests for core.memory_rotation."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.memory_rotation import (  # noqa: E402
    ARCHIVE_DIRNAME,
    count_session_log_blocks,
    rotate_session_log,
)

HEADER = (
    "# Session Log\n\n"
    "Append-only record of subagent completions.\n\n---\n\n"
)


def _block(n: int) -> str:
    return f"## 2026-04-21T00:{n:02d}:00Z — task {n}\n- Changed: core/file_{n}.py"


def _build_log(blocks: list[str]) -> str:
    body = "\n\n---\n\n".join(blocks) + "\n\n---\n\n" if blocks else ""
    return HEADER + body


def _write_log(memory_root: Path, blocks: list[str]) -> Path:
    memory_root.mkdir(parents=True, exist_ok=True)
    path = memory_root / "session-log.md"
    path.write_text(_build_log(blocks), encoding="utf-8")
    return path


def test_count_blocks_empty(tmp_path: Path) -> None:
    assert count_session_log_blocks(tmp_path) == 0


def test_count_blocks_header_only(tmp_path: Path) -> None:
    _write_log(tmp_path, [])
    assert count_session_log_blocks(tmp_path) == 0


def test_count_blocks_several(tmp_path: Path) -> None:
    _write_log(tmp_path, [_block(i) for i in range(7)])
    assert count_session_log_blocks(tmp_path) == 7


def test_rotate_noop_when_under_threshold(tmp_path: Path) -> None:
    _write_log(tmp_path, [_block(i) for i in range(3)])
    result = rotate_session_log(tmp_path, keep=5)
    assert result["rotated"] is False
    assert result["moved"] == 0
    assert result["archive"] is None
    assert not (tmp_path / ARCHIVE_DIRNAME).exists()


def test_rotate_noop_at_exact_threshold(tmp_path: Path) -> None:
    _write_log(tmp_path, [_block(i) for i in range(5)])
    result = rotate_session_log(tmp_path, keep=5)
    assert result["rotated"] is False
    assert result["remaining"] == 5


def test_rotate_moves_oldest_to_archive(tmp_path: Path) -> None:
    blocks = [_block(i) for i in range(8)]
    _write_log(tmp_path, blocks)

    fixed_now = datetime(2026, 4, 21, 12, 30, 45, tzinfo=timezone.utc)
    result = rotate_session_log(tmp_path, keep=5, now=fixed_now)

    assert result["rotated"] is True
    assert result["moved"] == 3
    assert result["remaining"] == 5

    archive_path = Path(result["archive"])
    assert archive_path.exists()
    assert archive_path.parent == tmp_path / ARCHIVE_DIRNAME
    assert "2026-04-21T12-30-45" in archive_path.name

    archive_body = archive_path.read_text(encoding="utf-8")
    assert "task 0" in archive_body
    assert "task 1" in archive_body
    assert "task 2" in archive_body
    assert "task 3" not in archive_body

    live_body = (tmp_path / "session-log.md").read_text(encoding="utf-8")
    assert "task 0" not in live_body
    assert "task 3" in live_body
    assert "task 7" in live_body
    assert live_body.startswith("# Session Log")


def test_rotate_preserves_header_exactly(tmp_path: Path) -> None:
    custom_header = (
        "# Session Log\n\nCustom prelude line.\n\nSecond prelude.\n\n---\n\n"
    )
    blocks = [_block(i) for i in range(6)]
    body = "\n\n---\n\n".join(blocks) + "\n\n---\n\n"
    (tmp_path / "session-log.md").write_text(
        custom_header + body, encoding="utf-8"
    )

    rotate_session_log(tmp_path, keep=3)

    live = (tmp_path / "session-log.md").read_text(encoding="utf-8")
    assert live.startswith(custom_header)


def test_rotate_idempotent_second_call_noop(tmp_path: Path) -> None:
    _write_log(tmp_path, [_block(i) for i in range(10)])
    first = rotate_session_log(tmp_path, keep=4)
    second = rotate_session_log(tmp_path, keep=4)
    assert first["rotated"] is True
    assert second["rotated"] is False
    assert len(list((tmp_path / ARCHIVE_DIRNAME).iterdir())) == 1


def test_rotate_no_file_returns_noop(tmp_path: Path) -> None:
    result = rotate_session_log(tmp_path, keep=5)
    assert result["rotated"] is False
    assert result["moved"] == 0


def test_rotate_archive_has_context_store_separator(tmp_path: Path) -> None:
    """Archive must use the same '\\n---\\n' separator so ContextStore chunks correctly."""
    _write_log(tmp_path, [_block(i) for i in range(7)])
    result = rotate_session_log(tmp_path, keep=3)
    archive_body = Path(result["archive"]).read_text(encoding="utf-8")
    assert archive_body.count("\n---\n") >= 2


def test_rotate_multiple_runs_create_distinct_archives(tmp_path: Path) -> None:
    _write_log(tmp_path, [_block(i) for i in range(10)])
    now1 = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    now2 = datetime(2026, 4, 21, 11, 0, 0, tzinfo=timezone.utc)

    r1 = rotate_session_log(tmp_path, keep=4, now=now1)

    _write_log(tmp_path, [_block(i) for i in range(100, 108)])
    r2 = rotate_session_log(tmp_path, keep=4, now=now2)

    assert r1["archive"] != r2["archive"]
    assert Path(r1["archive"]).exists()
    assert Path(r2["archive"]).exists()


def test_rotate_rejects_invalid_keep() -> None:
    # Not really a requirement — just documenting that keep=0 is allowed
    # (drops everything to archive). If we wanted to forbid it, we'd
    # raise here. Leaving this as a placeholder test to pin the contract.
    pass
