from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from core.paths import logs_dir

DEFAULT_LOG_FILE = "orch.log"

_configured = False


def configure_logging(
    log_dir: Path | str | None = None,
    level: str | None = None,
) -> None:
    # idempotent — re-entry must not stack handlers on the root logger
    global _configured
    if _configured:
        return

    resolved_dir = Path(log_dir) if log_dir is not None else logs_dir()
    resolved_dir.mkdir(parents=True, exist_ok=True)

    resolved_level = (
        level
        if level is not None
        else os.environ.get("CLAUDEORCH_LOG_LEVEL", "INFO")
    ).upper()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        resolved_dir / DEFAULT_LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(resolved_level)
    root.handlers[:] = [file_handler, stream_handler]

    _configured = True
