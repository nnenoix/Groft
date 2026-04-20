#!/usr/bin/env python3
"""Backfill architecture/decisions.md into DuckDB decisions log.

Usage:
    python3 scripts/backfill_decisions.py [--project-root PATH]

Idempotent: clears previous opus/null-task_id rows before re-inserting.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Adjust sys.path so project imports work when run from any directory.
PROJECT_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def _detect_category(title: str) -> str:
    low = title.lower()
    if low.startswith("fix"):
        return "fix"
    m = re.match(r"phase[\s\-]?(\d+)", low)
    if m:
        return f"phase-{m.group(1)}"
    return "architecture"


def parse_decisions_md(text: str) -> list[dict]:
    """Parse decisions.md sections into dicts.

    Each section starts with `## YYYY-MM-DD — <title>`.
    """
    sections = re.split(r"(?m)^(?=## \d{4}-\d{2}-\d{2})", text)
    results = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        header_m = re.match(r"## (\d{4}-\d{2}-\d{2})\s+[—–-]+\s+(.+)", sec)
        if not header_m:
            continue
        date_str = header_m.group(1)
        title = header_m.group(2).strip()
        try:
            ts = datetime(
                *map(int, date_str.split("-")), 12, 0, 0, tzinfo=timezone.utc
            )
        except ValueError:
            log.warning("bad date in header: %s", date_str)
            continue

        # Extract reason from **Почему:** and **Вывод:** sections
        reason_parts = []
        for pattern in (
            r"\*\*Почему:\*\*\s*([\s\S]*?)(?=\n\*\*|\Z)",
            r"\*\*Вывод:\*\*\s*([\s\S]*?)(?=\n\*\*|\Z)",
        ):
            m = re.search(pattern, sec)
            if m:
                part = m.group(1).strip()
                if part:
                    reason_parts.append(part)

        reason = "\n\n".join(reason_parts).strip() or title
        category = _detect_category(title)

        results.append({
            "ts": ts,
            "agent": "opus",
            "category": category,
            "chosen": title,
            "alternatives": None,
            "reason": reason,
            "task_id": None,
        })
    return results


async def run_backfill(project_root: Path) -> int:
    sys.path.insert(0, str(project_root))
    import os
    os.environ.setdefault("CLAUDEORCH_USER_DATA", str(project_root))

    from core.decision_log import DecisionLog

    decisions_md = project_root / "architecture" / "decisions.md"
    if not decisions_md.exists():
        log.warning("decisions.md not found at %s — nothing to backfill", decisions_md)
        return 0

    text = decisions_md.read_text(encoding="utf-8")
    entries = parse_decisions_md(text)
    if not entries:
        log.warning("No parseable entries found in decisions.md")
        return 0

    dl = DecisionLog()
    await dl.initialize()
    try:
        # Idempotent: clear previous manual entries
        import asyncio as _aio
        loop = _aio.get_running_loop()
        async with dl._db_lock:
            await loop.run_in_executor(
                None,
                lambda: dl._conn.execute(
                    "DELETE FROM decisions WHERE agent = 'opus' AND task_id IS NULL"
                ),
            )
        count = 0
        for entry in entries:
            await dl.append(
                agent=entry["agent"],
                category=entry["category"],
                chosen=entry["chosen"],
                alternatives=entry["alternatives"],
                reason=entry["reason"],
                task_id=entry["task_id"],
                ts=entry["ts"],
            )
            count += 1
        log.info("Backfill complete: %d entries written", count)
        return count
    finally:
        await dl.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT_DEFAULT),
        help="Path to project root (default: parent of scripts/)",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    count = asyncio.run(run_backfill(project_root))
    print(f"Backfilled {count} decisions.")


if __name__ == "__main__":
    main()
