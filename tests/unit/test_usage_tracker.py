from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.usage_tracker import UsageTracker


def make_line(input_tokens: int, output_tokens: int, age_hours: float = 1.0) -> str:
    ts = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return json.dumps({
        "timestamp": ts,
        "message": {"usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}},
    })


def test_aggregates_tokens_correctly(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "myproject"
    proj.mkdir()
    lines = [
        make_line(100, 200, age_hours=1.0),
        make_line(50, 75, age_hours=2.0),
        make_line(10, 20, age_hours=72.0),  # within 7d but outside 5h
    ]
    (proj / "session.jsonl").write_text("\n".join(lines))

    tracker = UsageTracker(projects_dir=projects_dir)
    result = tracker.compute()

    # rolling_5h: only first two lines
    assert result["rolling_5h"]["input_tokens"] == 150
    assert result["rolling_5h"]["output_tokens"] == 275
    assert result["rolling_5h"]["total"] == 425

    # weekly: all three lines
    assert result["weekly"]["input_tokens"] == 160
    assert result["weekly"]["output_tokens"] == 295
    assert result["weekly"]["total"] == 455


def test_5h_boundary_excludes_old_messages(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "p"
    proj.mkdir()

    # 5h01m ago — should be excluded from rolling_5h
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=5, minutes=1)).isoformat()
    # 4h59m ago — should be included
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=4, minutes=59)).isoformat()

    lines = [
        json.dumps({"timestamp": old_ts, "message": {"usage": {"input_tokens": 999, "output_tokens": 999}}}),
        json.dumps({"timestamp": recent_ts, "message": {"usage": {"input_tokens": 10, "output_tokens": 20}}}),
    ]
    (proj / "s.jsonl").write_text("\n".join(lines))

    tracker = UsageTracker(projects_dir=projects_dir)
    result = tracker.compute()

    assert result["rolling_5h"]["input_tokens"] == 10
    assert result["rolling_5h"]["output_tokens"] == 20
    # both are within 7d
    assert result["weekly"]["input_tokens"] == 1009
    assert result["weekly"]["output_tokens"] == 1019


def test_empty_windows_return_zeros(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    tracker = UsageTracker(projects_dir=projects_dir)
    before = datetime.now(timezone.utc)
    result = tracker.compute()
    after = datetime.now(timezone.utc)

    assert result["rolling_5h"]["input_tokens"] == 0
    assert result["rolling_5h"]["output_tokens"] == 0
    assert result["rolling_5h"]["total"] == 0
    assert result["weekly"]["input_tokens"] == 0
    assert result["weekly"]["total"] == 0

    # reset_at should be close to now when window is empty
    reset_5h = datetime.fromisoformat(result["rolling_5h"]["reset_at"])
    reset_7d = datetime.fromisoformat(result["weekly"]["reset_at"])
    if reset_5h.tzinfo is None:
        reset_5h = reset_5h.replace(tzinfo=timezone.utc)
    if reset_7d.tzinfo is None:
        reset_7d = reset_7d.replace(tzinfo=timezone.utc)
    assert before <= reset_5h <= after
    assert before <= reset_7d <= after


def test_malformed_lines_ignored(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "p"
    proj.mkdir()

    lines = [
        "not json at all{{{",
        make_line(100, 200, age_hours=1.0),
        '{"timestamp": "2020-01-01T00:00:00+00:00"}',  # missing message.usage
        make_line(50, 50, age_hours=2.0),
        "",  # blank line
        '{"no_timestamp": true, "message": {"usage": {"input_tokens": 1, "output_tokens": 1}}}',
    ]
    (proj / "mixed.jsonl").write_text("\n".join(lines))

    tracker = UsageTracker(projects_dir=projects_dir)
    result = tracker.compute()

    # only the two valid make_line entries should count
    assert result["rolling_5h"]["input_tokens"] == 150
    assert result["rolling_5h"]["output_tokens"] == 250
    assert result["rolling_5h"]["total"] == 400


def test_missing_projects_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "projects" / "does_not_exist"
    tracker = UsageTracker(projects_dir=nonexistent)
    # must not raise
    result = tracker.compute()

    assert result["rolling_5h"]["input_tokens"] == 0
    assert result["rolling_5h"]["output_tokens"] == 0
    assert result["rolling_5h"]["total"] == 0
    assert result["weekly"]["input_tokens"] == 0
    assert result["weekly"]["output_tokens"] == 0
    assert result["weekly"]["total"] == 0
