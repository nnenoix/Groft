from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

import yaml

log = logging.getLogger(__name__)


class AgentSpawner:
    def __init__(self, project_path: str, config_path: str) -> None:
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

        if not await self._run_tmux(["new-window", "-t", "claudeorch", "-n", agent_name]):
            log.warning("tmux new-window failed for agent=%s; aborting spawn", agent_name)
            return False

        cmd = (
            f"AGENT_NAME={agent_name} "
            f"claude --model {model} "
            f"--dangerously-skip-permissions"
        )
        if not await self._run_tmux(["send-keys", "-t", window, cmd, "Enter"]):
            log.warning(
                "tmux send-keys failed for agent=%s window=%s; aborting spawn",
                agent_name,
                window,
            )
            # best-effort teardown of the orphan window so the pane map stays clean
            await self._run_tmux(["kill-window", "-t", window])
            return False

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
        await self._run_tmux(["kill-window", "-t", f"claudeorch:{agent_name}"])
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

    @staticmethod
    async def _run_tmux(args: list[str]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            log.warning("tmux binary not found; cannot run %s", args)
            return False
        except Exception:
            log.warning("tmux spawn failed for args=%s", args, exc_info=True)
            return False
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.warning(
                "tmux exit=%s args=%s stderr=%s",
                proc.returncode,
                args,
                stderr.decode(errors="replace").strip(),
            )
            return False
        return True
