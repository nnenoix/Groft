from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml


class AgentSpawner:
    def __init__(self, project_path: str, config_path: str) -> None:
        self.project_path = Path(project_path)
        with open(config_path) as f:
            self.config: dict[str, Any] = yaml.safe_load(f) or {}
        self.active_agents: dict[str, dict[str, Any]] = {}
        self._register_cb: Callable[[str, str], Any] | None = None
        self._unregister_cb: Callable[[str], Any] | None = None

    def set_register_callback(self, fn: Callable[[str, str], Any]) -> None:
        self._register_cb = fn

    def set_unregister_callback(self, fn: Callable[[str], Any]) -> None:
        self._unregister_cb = fn

    async def spawn(self, agent_name: str) -> bool:
        models = self.config.get("models", {}) if isinstance(self.config, dict) else {}
        model = models.get(agent_name, "claude-sonnet-4-6")
        window = f"claudeorch:{agent_name}"

        subprocess.run([
            "tmux", "new-window",
            "-t", "claudeorch",
            "-n", agent_name,
        ])

        cmd = (
            f"AGENT_NAME={agent_name} "
            f"claude --model {model} "
            f"--dangerously-skip-permissions"
        )
        subprocess.run([
            "tmux", "send-keys",
            "-t", window,
            cmd, "Enter",
        ])

        self.active_agents[agent_name] = {
            "tmux_target": window,
            "model": model,
            "status": "starting",
        }
        if self._register_cb is not None:
            result = self._register_cb(agent_name, window)
            if asyncio.iscoroutine(result):
                await result
        return True

    async def despawn(self, agent_name: str) -> bool:
        if agent_name not in self.active_agents:
            return False
        if self._unregister_cb is not None:
            result = self._unregister_cb(agent_name)
            if asyncio.iscoroutine(result):
                await result
        subprocess.run([
            "tmux", "kill-window",
            "-t", f"claudeorch:{agent_name}",
        ])
        del self.active_agents[agent_name]
        return True

    async def despawn_all(self) -> None:
        for name in list(self.active_agents.keys()):
            await self.despawn(name)

    def get_tmux_targets(self) -> dict[str, str]:
        return {
            name: info["tmux_target"]
            for name, info in self.active_agents.items()
        }
