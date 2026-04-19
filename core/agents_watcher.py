from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from watchfiles import Change, awatch

from core.paths import agents_dir as default_agents_dir

log = logging.getLogger(__name__)

_DEBOUNCE_MS = 250


async def _run(
    agents_dir: Path,
    on_change: Callable[[], Awaitable[None]],
    stop_event: asyncio.Event,
) -> None:
    log.info("agents_watcher started: dir=%s", agents_dir)
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.warning("agents_watcher could not ensure dir=%s", agents_dir, exc_info=True)
    try:
        # debounce aggregates a burst of FS events into one batch; only .md
        # create/delete/modify trigger the caller callback.
        async for changes in awatch(
            str(agents_dir), stop_event=stop_event, debounce=_DEBOUNCE_MS
        ):
            relevant = any(
                _is_md(path) and change in (Change.added, Change.modified, Change.deleted)
                for change, path in changes
            )
            if not relevant:
                continue
            try:
                await on_change()
            except Exception:
                log.warning("agents_watcher on_change failed", exc_info=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.warning("agents_watcher loop crashed", exc_info=True)


def _is_md(path: str) -> bool:
    return path.endswith(".md")


async def start(
    project_root: Path | None,
    on_change: Callable[[], Awaitable[None]],
) -> asyncio.Task:
    agents_dir = (
        project_root / ".claude" / "agents"
        if project_root is not None
        else default_agents_dir()
    )
    stop_event = asyncio.Event()

    async def _runner() -> None:
        try:
            await _run(agents_dir, on_change, stop_event)
        except asyncio.CancelledError:
            stop_event.set()
            raise

    return asyncio.create_task(_runner())
