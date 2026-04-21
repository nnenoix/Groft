"""Common helpers shared by hook scripts.

Each hook is a Python entrypoint invoked by Claude Code:
  - reads JSON event payload from stdin
  - optionally writes a JSON response to stdout
  - exits 0 (success) or 2 (block)

Keeping the boilerplate here so the per-rule scripts stay tiny.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def read_event() -> dict[str, Any]:
    """Read stdin as JSON. Return empty dict on parse failure — hooks
    should not crash because of malformed input; they should fail open."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def write_response(payload: dict[str, Any]) -> None:
    """Emit a JSON response to stdout."""
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def claudeorch_dir() -> Path:
    """Resolve `.claudeorch/` path for state persistence."""
    from core.paths import claudeorch_dir as _dir
    return _dir()


def project_memory_dir() -> Path:
    return PROJECT_ROOT / "memory"
