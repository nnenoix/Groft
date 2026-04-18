from __future__ import annotations

from typing import Any

from core.spawner import AgentSpawner


class Orchestrator:
    """Thin facade that bundles orchestrator-side actions.

    Exists so callers (manual REPL, future WS command) have one object
    to reach into spawner + watchdog + memory without threading globals.
    For now only `spawn_role` is implemented — extend as new commands land.
    """

    def __init__(self, spawner: AgentSpawner) -> None:
        self._spawner = spawner

    def known_roles(self) -> list[str]:
        models = self._spawner.config.get("models") if isinstance(self._spawner.config, dict) else None
        if not isinstance(models, dict):
            return []
        return [name for name in models.keys() if isinstance(name, str)]

    async def spawn_role(self, role_name: str) -> bool:
        """Boot a declared team-role agent in its tmux window.

        Returns False without spawning if role_name is not listed under
        `models:` in config.yml — prevents typos leaking unbounded claude procs.
        """
        roles = self.known_roles()
        if role_name not in roles:
            print(f"[orchestrator] unknown role={role_name!r}; known={roles}")
            return False
        if role_name in self._spawner.active_agents:
            print(f"[orchestrator] role already active role={role_name}")
            return False
        return await self._spawner.spawn(role_name)

    async def despawn_role(self, role_name: str) -> bool:
        return await self._spawner.despawn(role_name)

    def active(self) -> dict[str, Any]:
        return dict(self._spawner.active_agents)
