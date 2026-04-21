"""Step-planner: persistent multi-step plan in memory/current-plan.md.

Rule #4 of the Groft charter: progress must be visible. When opus tackles
a multi-step task, it writes the plan up-front via set_plan() and calls
advance_step() as each step lands. The plan file survives between
sessions, so after /compact or a restart opus still knows where it was.

This module is pure I/O on a markdown file. MCP wrappers live in
communication/mcp_server.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PLAN_FILENAME = "current-plan.md"

_STATUS_DONE = "x"
_STATUS_ACTIVE = "~"
_STATUS_PENDING = " "

_STEP_RE = re.compile(r"^\d+\.\s+\[(.)\]\s+(.*)$")


@dataclass
class Step:
    text: str
    status: str  # "done" | "active" | "pending"

    @property
    def mark(self) -> str:
        return {
            "done": _STATUS_DONE,
            "active": _STATUS_ACTIVE,
            "pending": _STATUS_PENDING,
        }[self.status]


@dataclass
class Plan:
    goal: str
    steps: list[Step]
    started: str
    updated: str

    def active_index(self) -> int | None:
        for i, s in enumerate(self.steps):
            if s.status == "active":
                return i
        return None

    def next_pending_index(self) -> int | None:
        for i, s in enumerate(self.steps):
            if s.status == "pending":
                return i
        return None

    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status == "done")
        total = len(self.steps)
        active = self.active_index()
        if active is None:
            if done == total and total > 0:
                return f"all {total} steps done"
            return f"{done}/{total} done (no active step)"
        return f"step {active + 1} of {total}: {self.steps[active].text}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plan_path(memory_root: Path) -> Path:
    return memory_root / PLAN_FILENAME


def _render(plan: Plan) -> str:
    lines = [
        "# Current Plan",
        "",
        f"**Goal:** {plan.goal}",
        f"**Started:** {plan.started}",
        "",
    ]
    for i, step in enumerate(plan.steps, 1):
        lines.append(f"{i}. [{step.mark}] {step.text}")
    lines.extend(["", "---", f"Last updated: {plan.updated}", ""])
    return "\n".join(lines)


def _parse(text: str) -> Plan:
    goal = ""
    started = ""
    updated = ""
    steps: list[Step] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("**Goal:**"):
            goal = line[len("**Goal:**"):].strip()
            continue
        if line.startswith("**Started:**"):
            started = line[len("**Started:**"):].strip()
            continue
        if line.startswith("Last updated:"):
            updated = line[len("Last updated:"):].strip()
            continue
        m = _STEP_RE.match(line)
        if m:
            mark, body = m.group(1), m.group(2).strip()
            status = {
                _STATUS_DONE: "done",
                _STATUS_ACTIVE: "active",
                _STATUS_PENDING: "pending",
            }.get(mark, "pending")
            steps.append(Step(text=body, status=status))
    return Plan(goal=goal, steps=steps, started=started, updated=updated)


def set_plan(goal: str, steps: list[str], *, memory_root: Path) -> Plan:
    """Replace the current plan. First non-empty step starts active."""
    clean = [s.strip() for s in steps if s and s.strip()]
    if not clean:
        raise ValueError("set_plan requires at least one non-empty step")
    now = _iso_now()
    step_objs = [
        Step(text=t, status="active" if i == 0 else "pending")
        for i, t in enumerate(clean)
    ]
    plan = Plan(goal=goal.strip(), steps=step_objs, started=now, updated=now)
    memory_root.mkdir(parents=True, exist_ok=True)
    _plan_path(memory_root).write_text(_render(plan), encoding="utf-8")
    return plan


def load_plan(*, memory_root: Path) -> Plan | None:
    path = _plan_path(memory_root)
    if not path.exists():
        return None
    return _parse(path.read_text(encoding="utf-8"))


def advance_step(*, memory_root: Path) -> Plan:
    """Mark active step done; promote next pending to active.

    Raises FileNotFoundError if no plan exists.
    Raises RuntimeError if there is no active step to advance.
    """
    plan = load_plan(memory_root=memory_root)
    if plan is None:
        raise FileNotFoundError("no current plan; call set_plan first")
    active = plan.active_index()
    if active is None:
        raise RuntimeError("no active step to advance")
    plan.steps[active].status = "done"
    nxt = plan.next_pending_index()
    if nxt is not None:
        plan.steps[nxt].status = "active"
    plan.updated = _iso_now()
    _plan_path(memory_root).write_text(_render(plan), encoding="utf-8")
    return plan
