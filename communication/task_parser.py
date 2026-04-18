from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PRIORITY_MAP = {"p0": "high", "p1": "med", "p2": "low", "p3": "low"}
_BUCKET_STATUS = {"backlog": "pending", "current": "active", "done": "done"}
_BUCKET_STAGE = {"backlog": "todo", "current": "active", "done": "done"}


def _parse_bucket(text: str, bucket: str) -> list[dict[str, Any]]:
    status = _BUCKET_STATUS.get(bucket, "pending")
    stage = _BUCKET_STAGE.get(bucket, "todo")
    out: list[dict[str, Any]] = []

    for section in re.split(r"\n(?=##\s)", text):
        m = re.match(r"^##\s+(\S+)\s+[—–-]\s+(.+)", section.strip())
        if not m:
            continue
        task_id = m.group(1).strip()
        title = m.group(2).strip()

        priority = "med"
        pm = re.search(r"\*\*Приоритет:\*\*\s*(\S+)", section)
        if pm:
            priority = _PRIORITY_MAP.get(pm.group(1).lower().rstrip(",.:"), "med")

        deps: list[str] = []
        dm = re.search(r"\*\*Зависимости:\*\*\s*(.+)", section)
        if dm:
            raw = dm.group(1).strip().strip("`")
            if raw.lower() not in ("нет", "none", "-", ""):
                raw_clean = re.sub(r"`[^`]*`", "", raw).strip()
                if raw_clean and raw_clean.lower() not in ("нет", "none", "-"):
                    deps = [
                        d.strip()
                        for d in re.split(r"[,\s]+", raw_clean)
                        if d.strip() and not d.startswith("^")
                    ]

        # omit owner when unknown — UI treats missing as undefined (matches the
        # asString() guard), whereas "" would render as a blank column.
        out.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "stage": stage,
                "priority": priority,
                "deps": deps,
            }
        )
    return out


def parse_tasks_dir(tasks_dir: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"backlog": [], "current": [], "done": []}
    for bucket in ("backlog", "current", "done"):
        path = tasks_dir / f"{bucket}.md"
        if path.exists():
            result[bucket] = _parse_bucket(path.read_text(encoding="utf-8"), bucket)
    return result
