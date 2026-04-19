"""AgentSpawner.reload_config + Orchestrator.spawn_role hot-reload path.

Scenario: a user edits config.yml at runtime to add a new role. Before this
change, Orchestrator.spawn_role would reject the new name because
`self._spawner.config` is frozen at __init__. After Fix C, the rejection path
forces a reload and retries the allowlist check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import Orchestrator  # noqa: E402
from core.spawner import AgentSpawner  # noqa: E402
from tests.support.in_memory_backend import InMemoryBackend  # noqa: E402


def _write_config(path: Path, models: dict[str, str]) -> None:
    lines = ["models:"]
    for name, model in models.items():
        lines.append(f"  {name}: {model}")
    path.write_text("\n".join(lines) + "\n")


def test_reload_picks_up_new_role(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yml"
    _write_config(cfg, {"backend-dev": "claude-sonnet-4-6"})

    spawner = AgentSpawner(str(tmp_path), str(cfg), backend=InMemoryBackend())
    assert "backend-dev" in spawner.config.get("models", {})
    assert "new-role" not in spawner.config.get("models", {})

    _write_config(
        cfg,
        {"backend-dev": "claude-sonnet-4-6", "new-role": "claude-haiku-4-5-20251001"},
    )

    spawner.reload_config()
    assert "new-role" in spawner.config.get("models", {})
    assert spawner.config["models"]["new-role"] == "claude-haiku-4-5-20251001"


def test_reload_preserves_config_when_file_becomes_malformed(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yml"
    _write_config(cfg, {"backend-dev": "claude-sonnet-4-6"})

    spawner = AgentSpawner(str(tmp_path), str(cfg), backend=InMemoryBackend())
    # mangle the file — unterminated map
    cfg.write_text("models: [invalid\n")

    spawner.reload_config()
    # known role survives the bad reload
    assert "backend-dev" in spawner.config.get("models", {})


@pytest.mark.asyncio
async def test_orchestrator_spawn_role_retries_after_reload(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yml"
    _write_config(cfg, {"backend-dev": "claude-sonnet-4-6"})

    backend = InMemoryBackend()
    spawner = AgentSpawner(str(tmp_path), str(cfg), backend=backend)
    orchestrator = Orchestrator(spawner)

    assert await orchestrator.spawn_role("scout") is False

    _write_config(
        cfg,
        {"backend-dev": "claude-sonnet-4-6", "scout": "claude-haiku-4-5-20251001"},
    )

    assert await orchestrator.spawn_role("scout") is True
    assert "scout" in spawner.active_agents
