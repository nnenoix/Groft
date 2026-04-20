"""Unit tests for backfill_decisions.py parser."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_MD = """
# Architecture Decision Log

---

## 2026-04-19 — Fix #1: UISettings persistence (localStorage)

**Что:** New hook useUISettings.ts.

**Почему:** Before this fix theme/font lived only in useState.

**Как проверил:** npm run build — no errors.

---

## 2026-04-19 — Phase 8: Decision log DuckDB

**Что:** DuckDB backend for decisions.

**Почему:** Markdown is not searchable programmatically.

**Вывод:** DuckDB chosen over SQLite for columnar analytics.

---

## 2026-04-18 — Architecture: adopt async-first pattern

**Что:** All DB calls go through executor.

**Почему:** Avoid blocking the event loop.
"""


def test_parse_decisions_returns_correct_count() -> None:
    from scripts.backfill_decisions import parse_decisions_md
    entries = parse_decisions_md(SAMPLE_MD)
    assert len(entries) == 3


def test_parse_decisions_category_fix() -> None:
    from scripts.backfill_decisions import parse_decisions_md
    entries = parse_decisions_md(SAMPLE_MD)
    fix_entry = next(e for e in entries if "UISettings" in e["chosen"])
    assert fix_entry["category"] == "fix"


def test_parse_decisions_category_phase() -> None:
    from scripts.backfill_decisions import parse_decisions_md
    entries = parse_decisions_md(SAMPLE_MD)
    phase_entry = next(e for e in entries if "Phase 8" in e["chosen"])
    assert phase_entry["category"] == "phase-8"


def test_parse_decisions_reason_includes_pochemu() -> None:
    from scripts.backfill_decisions import parse_decisions_md
    entries = parse_decisions_md(SAMPLE_MD)
    arch_entry = next(e for e in entries if "async" in e["chosen"])
    assert "event loop" in arch_entry["reason"]


def test_parse_decisions_agent_always_opus() -> None:
    from scripts.backfill_decisions import parse_decisions_md
    entries = parse_decisions_md(SAMPLE_MD)
    assert all(e["agent"] == "opus" for e in entries)


@pytest.mark.asyncio
async def test_backfill_run_inserts_entries(tmp_path: Path) -> None:
    import os
    os.environ["CLAUDEORCH_USER_DATA"] = str(tmp_path)
    import core.paths as paths
    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()

    md_dir = tmp_path / "architecture"
    md_dir.mkdir()
    (md_dir / "decisions.md").write_text(SAMPLE_MD, encoding="utf-8")

    from scripts.backfill_decisions import run_backfill
    count = await run_backfill(tmp_path)
    assert count == 3

    from core.decision_log import DecisionLog
    dl = DecisionLog()
    await dl.initialize()
    rows = await dl.list_recent()
    assert len(rows) == 3
    await dl.close()

    paths.install_root.cache_clear()
    paths.user_data_root.cache_clear()
