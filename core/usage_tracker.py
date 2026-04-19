from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class UsageTracker:
    def __init__(self, projects_dir: Path | None = None) -> None:
        self._projects_dir = (
            projects_dir
            if projects_dir is not None
            else Path.home() / ".claude" / "projects"
        )

    def compute(self) -> dict:
        now = datetime.now(timezone.utc)
        cutoff_5h = now - timedelta(hours=5)
        cutoff_7d = now - timedelta(days=7)

        rolling: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        weekly: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        # oldest timestamps per window for reset_at calculation
        oldest_5h: datetime | None = None
        oldest_7d: datetime | None = None

        if not self._projects_dir.exists():
            return self._build_result(rolling, weekly, oldest_5h, oldest_7d, now, cutoff_5h, cutoff_7d)

        for jsonl_file in self._projects_dir.glob("**/*.jsonl"):
            try:
                lines = jsonl_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                log.warning("usage_tracker: cannot read %s", jsonl_file)
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    log.warning("usage_tracker: malformed JSON line in %s", jsonl_file)
                    continue
                try:
                    ts_str: str = obj["timestamp"]
                    usage = obj["message"]["usage"]
                    inp: int = usage["input_tokens"]
                    out: int = usage["output_tokens"]
                    ts = datetime.fromisoformat(ts_str)
                    # ensure timezone-aware
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (KeyError, TypeError, ValueError):
                    continue

                if ts >= cutoff_7d:
                    weekly["input_tokens"] += inp
                    weekly["output_tokens"] += out
                    if oldest_7d is None or ts < oldest_7d:
                        oldest_7d = ts

                if ts >= cutoff_5h:
                    rolling["input_tokens"] += inp
                    rolling["output_tokens"] += out
                    if oldest_5h is None or ts < oldest_5h:
                        oldest_5h = ts

        return self._build_result(rolling, weekly, oldest_5h, oldest_7d, now, cutoff_5h, cutoff_7d)

    @staticmethod
    def _build_result(
        rolling: dict[str, int],
        weekly: dict[str, int],
        oldest_5h: datetime | None,
        oldest_7d: datetime | None,
        now: datetime,
        cutoff_5h: datetime,
        cutoff_7d: datetime,
    ) -> dict:
        if oldest_5h is not None:
            reset_5h = (oldest_5h + timedelta(hours=5)).isoformat()
        else:
            reset_5h = now.isoformat()

        if oldest_7d is not None:
            reset_7d = (oldest_7d + timedelta(days=7)).isoformat()
        else:
            reset_7d = now.isoformat()

        return {
            "rolling_5h": {
                "input_tokens": rolling["input_tokens"],
                "output_tokens": rolling["output_tokens"],
                "total": rolling["input_tokens"] + rolling["output_tokens"],
                "reset_at": reset_5h,
            },
            "weekly": {
                "input_tokens": weekly["input_tokens"],
                "output_tokens": weekly["output_tokens"],
                "total": weekly["input_tokens"] + weekly["output_tokens"],
                "reset_at": reset_7d,
            },
        }
