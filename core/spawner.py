from __future__ import annotations

import asyncio
import logging
import warnings
from pathlib import Path
from typing import Any, Callable

import yaml

from core.process import ProcessBackend, TmuxBackend

log = logging.getLogger(__name__)


class AgentSpawner:
    def __init__(
        self,
        project_path: str,
        config_path: str,
        backend: ProcessBackend | None = None,
    ) -> None:
        self.project_path = Path(project_path)
        # config.yml may be missing or malformed during local setups; fall back
        # to an empty model map and let agents use the spawn-time default.
        self.config: dict[str, Any] = {}
        try:
            with open(config_path) as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    self.config = loaded
        except FileNotFoundError:
            log.warning("config.yml missing at %s; using empty models map", config_path)
        except (OSError, yaml.YAMLError):
            log.warning(
                "config.yml read/parse failed at %s; using empty models map",
                config_path,
                exc_info=True,
            )
        # default backend keeps the legacy single-arg constructor working for
        # ad-hoc REPL use; production wiring in core/main.py always injects.
        self._backend: ProcessBackend = backend if backend is not None else TmuxBackend()
        self.active_agents: dict[str, dict[str, Any]] = {}
        self._register_cb: Callable[[str, str], Any] | None = None
        self._unregister_cb: Callable[[str], Any] | None = None

    def set_register_callback(self, fn: Callable[[str, str], Any]) -> None:
        self._register_cb = fn

    def set_unregister_callback(self, fn: Callable[[str], Any]) -> None:
        self._unregister_cb = fn

    @property
    def backend(self) -> ProcessBackend:
        return self._backend

    async def spawn(self, agent_name: str) -> bool:
        models = self.config.get("models", {}) if isinstance(self.config, dict) else {}
        model = models.get(agent_name, "claude-sonnet-4-6")
        cmd = ["claude", "--model", model, "--dangerously-skip-permissions"]
        # Project-scoped MCP config. Claude Code auto-discovers `.mcp.json` from
        # cwd, but tmux window cwd is not guaranteed to match project_path on
        # every host, so we pass the absolute path explicitly.
        mcp_config = self.project_path / ".mcp.json"
        if mcp_config.is_file():
            cmd += ["--mcp-config", str(mcp_config)]
        # CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 enables the agent-teams feature
        # in the spawned process so sub-agents can see each other via the
        # claudeorch-comms MCP bridge and answer WS messages from opus.
        env = {
            "AGENT_NAME": agent_name,
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
        }
        target = await self._backend.spawn(agent_name, cmd, env=env)
        if target is None:
            return False
        self.active_agents[agent_name] = {
            "target": target,
            "model": model,
            "status": "starting",
        }
        if self._register_cb is not None:
            result = self._register_cb(agent_name, target)
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
        target = self.active_agents[agent_name]["target"]
        await self._backend.kill(target)
        del self.active_agents[agent_name]
        return True

    async def despawn_all(self) -> None:
        for name in list(self.active_agents.keys()):
            await self.despawn(name)

    def get_targets(self) -> dict[str, str]:
        return {
            name: info["target"]
            for name, info in self.active_agents.items()
        }

    def get_tmux_targets(self) -> dict[str, str]:
        # legacy alias kept for any out-of-tree caller; in-tree code now uses
        # get_targets(). Removed in a follow-up once the deprecation window passes.
        warnings.warn(
            "AgentSpawner.get_tmux_targets() is deprecated; use get_targets()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_targets()
