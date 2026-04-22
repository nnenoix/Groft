"""Unit tests for core.step_planner."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.step_planner import (  # noqa: E402
    advance_step,
    load_plan,
    set_plan,
)


def test_set_plan_writes_file_first_step_active(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    plan = set_plan(
        "Ship auth flow",
        ["Design schema", "Implement login", "Add logout"],
        memory_root=mem,
    )
    assert plan.steps[0].status == "active"
    assert plan.steps[1].status == "pending"
    assert plan.progress() == "step 1 of 3: Design schema"

    content = (mem / "current-plan.md").read_text(encoding="utf-8")
    assert "Ship auth flow" in content
    assert "1. [~] Design schema" in content
    assert "2. [ ] Implement login" in content


def test_set_plan_rejects_empty_steps(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    with pytest.raises(ValueError):
        set_plan("goal", [], memory_root=mem)
    with pytest.raises(ValueError):
        set_plan("goal", ["", "   "], memory_root=mem)


def test_set_plan_overwrites_existing(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    set_plan("first goal", ["a", "b"], memory_root=mem)
    set_plan("second goal", ["c"], memory_root=mem)
    plan = load_plan(memory_root=mem)
    assert plan is not None
    assert plan.goal == "second goal"
    assert [s.text for s in plan.steps] == ["c"]


def test_load_plan_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_plan(memory_root=tmp_path / "nope") is None


def test_load_plan_roundtrip(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    original = set_plan("G", ["one", "two", "three"], memory_root=mem)
    loaded = load_plan(memory_root=mem)
    assert loaded is not None
    assert loaded.goal == original.goal
    assert [s.text for s in loaded.steps] == ["one", "two", "three"]
    assert loaded.steps[0].status == "active"


def test_advance_step_moves_active_forward(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    set_plan("G", ["a", "b", "c"], memory_root=mem)
    after_first = advance_step(memory_root=mem)
    assert after_first.steps[0].status == "done"
    assert after_first.steps[1].status == "active"
    assert after_first.progress() == "step 2 of 3: b"

    after_second = advance_step(memory_root=mem)
    assert after_second.steps[1].status == "done"
    assert after_second.steps[2].status == "active"


def test_advance_last_step_finishes_plan(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    set_plan("G", ["only"], memory_root=mem)
    final = advance_step(memory_root=mem)
    assert final.steps[0].status == "done"
    assert final.active_index() is None
    assert final.progress() == "all 1 steps done"


def test_advance_without_plan_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        advance_step(memory_root=tmp_path / "memory")


def test_advance_with_no_active_step_raises(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    set_plan("G", ["only"], memory_root=mem)
    advance_step(memory_root=mem)
    with pytest.raises(RuntimeError):
        advance_step(memory_root=mem)


def test_updated_timestamp_changes_on_advance(tmp_path: Path) -> None:
    import time

    mem = tmp_path / "memory"
    plan = set_plan("G", ["a", "b"], memory_root=mem)
    initial_updated = plan.updated
    # updated is second-precision — sleep >2s so we reliably cross a tick
    # even under load (1.1s flaked under parallel-pytest load on WSL).
    time.sleep(2.1)
    after = advance_step(memory_root=mem)
    assert after.updated != initial_updated
