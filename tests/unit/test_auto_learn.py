"""Unit tests for core.auto_learn."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auto_learn import save_feedback_rule  # noqa: E402


def test_save_creates_file_and_indexes(tmp_path: Path) -> None:
    result = save_feedback_rule(
        rule="Always state step N of M in chat between steps",
        why="user said file-based progress isn't visible",
        how_to_apply="announce on each transition",
        memory_root=tmp_path,
    )
    assert result["created"] is True
    assert result["indexed"] is True
    path = Path(result["path"])
    assert path.exists()

    body = path.read_text(encoding="utf-8")
    assert "type: feedback" in body
    assert "Always state step N of M" in body
    assert "**Why:**" in body
    assert "**How to apply:**" in body

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert path.name in index


def test_save_rejects_empty_rule(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_feedback_rule(rule="  ", why="x", how_to_apply="y", memory_root=tmp_path)


def test_save_rejects_empty_why(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_feedback_rule(
            rule="r", why="", how_to_apply="h", memory_root=tmp_path
        )


def test_save_twice_same_filename_does_not_duplicate_index(tmp_path: Path) -> None:
    save_feedback_rule(
        rule="one", why="w", how_to_apply="h",
        filename="rule_one", memory_root=tmp_path,
    )
    result2 = save_feedback_rule(
        rule="one updated", why="w2", how_to_apply="h2",
        filename="rule_one", memory_root=tmp_path,
    )
    assert result2["created"] is False
    assert result2["indexed"] is False

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert index.count("rule_one.md") == 1

    body = (tmp_path / "rule_one.md").read_text(encoding="utf-8")
    assert "one updated" in body


def test_save_appends_multiple_distinct_rules(tmp_path: Path) -> None:
    save_feedback_rule(
        rule="first rule", why="w1", how_to_apply="h1",
        filename="a", memory_root=tmp_path,
    )
    save_feedback_rule(
        rule="second rule", why="w2", how_to_apply="h2",
        filename="b", memory_root=tmp_path,
    )
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "a.md" in index
    assert "b.md" in index
    assert index.count("- [") == 2


def test_save_preserves_existing_index(tmp_path: Path) -> None:
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "MEMORY.md").write_text(
        "- [Existing entry](existing.md) — already here\n",
        encoding="utf-8",
    )
    save_feedback_rule(
        rule="new", why="w", how_to_apply="h",
        filename="new", memory_root=tmp_path,
    )
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "existing.md" in index
    assert "new.md" in index


def test_save_filename_slug_is_filesystem_safe(tmp_path: Path) -> None:
    result = save_feedback_rule(
        rule="Rule with / slashes and \\backslashes and spaces!",
        why="test",
        how_to_apply="test",
        memory_root=tmp_path,
    )
    path = Path(result["path"])
    assert path.exists()
    assert "/" not in path.name
    assert "\\" not in path.name


def test_save_truncates_long_hook_in_index(tmp_path: Path) -> None:
    long_rule = "x" * 300
    save_feedback_rule(
        rule=long_rule, why="w", how_to_apply="h",
        filename="long", memory_root=tmp_path,
    )
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    line = next(line for line in index.splitlines() if "long.md" in line)
    assert len(line) < 300
    assert "..." in line
