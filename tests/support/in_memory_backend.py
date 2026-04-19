"""InMemoryBackend — test double for ProcessBackend.

Records every call as a tuple in `self.calls` so tests can assert on the
exact spawn/send_text/kill/capture_output sequence. Platform-neutral; no
asyncio primitives beyond `async def`. Ships under tests/support so it
isn't shipped with the runtime distribution.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.process.backend import Target


class InMemoryBackend:
    def __init__(self) -> None:
        # Each entry: (op, *args). Read-only contract for assertions — tests
        # may slice/filter but should not mutate.
        self.calls: list[tuple[Any, ...]] = []
        self._targets: dict[str, Target] = {}
        self._alive: set[Target] = set()
        # Optional preset outputs returned by capture_output for a target.
        # Tests assign via `backend.outputs[target] = "..."`.
        self.outputs: dict[Target, str] = {}

    async def spawn(
        self,
        name: str,
        cmd: list[str],
        env: Mapping[str, str] | None = None,
    ) -> Target | None:
        target = f"mem:{name}"
        self.calls.append(("spawn", name, tuple(cmd), dict(env or {})))
        self._targets[name] = target
        self._alive.add(target)
        return target

    async def send_text(
        self,
        target: Target,
        text: str,
        *,
        press_enter: bool = True,
    ) -> bool:
        self.calls.append(("send_text", target, text, press_enter))
        return True

    async def kill(self, target: Target) -> bool:
        self.calls.append(("kill", target))
        existed = target in self._alive
        self._alive.discard(target)
        for name, tgt in list(self._targets.items()):
            if tgt == target:
                del self._targets[name]
        return existed

    async def capture_output(self, target: Target, lines: int = 50) -> str:
        self.calls.append(("capture_output", target, lines))
        return self.outputs.get(target, "")

    async def is_alive(self, target: Target) -> bool:
        self.calls.append(("is_alive", target))
        return target in self._alive

    def list_targets(self) -> dict[str, Target]:
        return dict(self._targets)

    # convenience for the spawner refactor — mirrors TmuxBackend.forget so the
    # despawn path can drop a name from the registry without going through kill().
    def forget(self, name: str) -> None:
        self._targets.pop(name, None)
