import { useEffect, useRef } from "react";
import useWebSocket, { type WSStatus } from "./useWebSocket";
import { useDispatch } from "../store/agentStore";
import type { AgentStatus } from "../store/agentStore";
import type { Task, TaskStatus } from "../store/agentStore";

const VALID_STATUSES = new Set<AgentStatus>([
  "active",
  "idle",
  "stuck",
  "restarting",
]);

const VALID_TASK_STATUSES = new Set<TaskStatus>(["done", "active", "pending"]);

function isAgentStatus(v: unknown): v is AgentStatus {
  return typeof v === "string" && VALID_STATUSES.has(v as AgentStatus);
}

function isTaskStatus(v: unknown): v is TaskStatus {
  return typeof v === "string" && VALID_TASK_STATUSES.has(v as TaskStatus);
}

function asString(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function asStringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: string[] = [];
  for (const item of v) {
    if (typeof item !== "string") return undefined;
    out.push(item);
  }
  return out;
}

function asNumberArray(v: unknown): number[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: number[] = [];
  for (const item of v) {
    if (typeof item !== "number") return undefined;
    out.push(item);
  }
  return out;
}

const VALID_PRIORITIES = new Set(["high", "med", "low"]);
function isTaskPriority(v: unknown): v is "high" | "med" | "low" {
  return typeof v === "string" && VALID_PRIORITIES.has(v);
}

function isMode(v: unknown): v is "solo" | "team" {
  return v === "solo" || v === "team";
}

function asTaskArray(v: unknown): Task[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: Task[] = [];
  for (const raw of v) {
    if (!raw || typeof raw !== "object") return undefined;
    const rec = raw as Record<string, unknown>;
    const id = asString(rec.id);
    const title = asString(rec.title);
    const status = rec.status;
    if (!id || !title || !isTaskStatus(status)) return undefined;
    const task: Task = { id, title, status };
    const stage = asString(rec.stage);
    if (stage !== undefined) task.stage = stage;
    const owner = asString(rec.owner);
    if (owner !== undefined) task.owner = owner;
    if (isTaskPriority(rec.priority)) task.priority = rec.priority;
    const deps = asStringArray(rec.deps);
    if (deps !== undefined) task.deps = deps;
    out.push(task);
  }
  return out;
}

function nowHHMMSS(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export interface UseOrchestratorResult {
  connected: boolean;
  status: WSStatus;
  /**
   * sendMessage expects an object matching the ClaudeOrch WS protocol:
   *   { type: "message", from: "ui", to: "opus", content: string,
   *     mode?: "solo"|"team"|"review", model?: "opus-4-7"|"sonnet-4-6"|"haiku-4-5" }
   * opus может игнорировать mode/model или учитывать их как подсказку режима.
   */
  sendMessage: (obj: unknown) => boolean;
}

/**
 * Wires the raw WebSocket stream into the AgentStore.
 *
 * Expected payloads (see communication/server.py):
 *   - status    { type:"status",    agent, status, currentAction?, currentTask? }
 *   - snapshot  { type:"snapshot",  agent, terminal }     // `terminal` is a single string
 *   - message   { type:"message",   from, to, content }
 *   - broadcast { type:"broadcast", from, content }
 *   - roster    { type:"roster",    agents: string[] }    // pushed when connection set changes
 *   - tasks     { type:"tasks",     backlog?, current?, done? } // future: server-driven task state
 *
 * On each disconnected → connected transition, also fetches the current
 * roster via REST (GET localhost:8766/agents → {agents: string[]}). One-shot,
 * no polling.
 *
 * Caveat: the server currently does not forward `status` frames to other
 * clients — it only records them. UI will still react if/when the orchestrator
 * broadcasts status, or if this behaviour changes.
 */
const WS_URL =
  (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8765";
const REST_URL =
  (import.meta.env.VITE_REST_URL as string | undefined) ??
  "http://localhost:8766";

// roster filter — "ui" is the viewer itself; opus is kept so the orchestrator
// still appears in the agents view.
const ROSTER_HIDDEN = new Set(["ui"]);
function cleanRoster(names: string[]): string[] {
  return names.filter((n) => !ROSTER_HIDDEN.has(n));
}

function useOrchestrator(): UseOrchestratorResult {
  const dispatch = useDispatch();
  const { status, connected, sendMessage, lastMessage } = useWebSocket({
    url: WS_URL,
    agentName: "ui",
  });

  // Fetch roster exactly once per disconnected→connected transition.
  const prevStatusRef = useRef<WSStatus>("disconnected");
  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (status !== "connected") return;
    if (prev === "connected") return;

    const ctrl = new AbortController();
    (async () => {
      try {
        const resp = await fetch(`${REST_URL}/agents`, {
          signal: ctrl.signal,
        });
        if (!resp.ok) return;
        const body: unknown = await resp.json();
        if (!body || typeof body !== "object") return;
        const names = asStringArray((body as Record<string, unknown>).agents);
        if (!names) return;
        dispatch({ type: "SET_AGENT_ROSTER", names: cleanRoster(names) });
      } catch {
        /* network error / aborted — ignored; WS roster frame may still arrive */
      }
    })();
    return () => ctrl.abort();
  }, [status, dispatch]);

  useEffect(() => {
    if (!lastMessage) return;
    const msg = lastMessage;
    const type = asString(msg.type);
    if (!type) return;

    switch (type) {
      case "status": {
        const name = asString(msg.agent);
        const st = msg.status;
        if (!name || !isAgentStatus(st)) return;
        dispatch({
          type: "UPSERT_AGENT_STATUS",
          name,
          status: st,
          currentAction: asString(msg.currentAction),
          currentTask: asString(msg.currentTask),
          model: asString(msg.model),
          mode: isMode(msg.mode) ? msg.mode : undefined,
          uptime: asString(msg.uptime),
          cycles: typeof msg.cycles === "number" ? msg.cycles : undefined,
          tokensIn: typeof msg.tokensIn === "number" ? msg.tokensIn : undefined,
          tokensOut: typeof msg.tokensOut === "number" ? msg.tokensOut : undefined,
          spark: asNumberArray(msg.spark),
        });
        return;
      }
      case "snapshot": {
        const name = asString(msg.agent);
        if (!name) return;
        // server.py ships `terminal` as a single string; accept `lines`/`content` too
        // in case future server versions attach them. Empty lines are preserved so
        // pane separators don't collapse the vertical structure of the capture.
        let lines: string[] | null = null;
        const terminal = msg.terminal;
        if (typeof terminal === "string") {
          lines = terminal.split(/\r?\n/);
        } else if (Array.isArray(msg.lines)) {
          lines = (msg.lines as unknown[]).filter(
            (x): x is string => typeof x === "string",
          );
        } else if (typeof msg.content === "string") {
          lines = msg.content.split(/\r?\n/);
        }
        if (!lines || lines.length === 0) return;
        dispatch({ type: "APPEND_TERMINAL", name, lines });
        return;
      }
      case "message": {
        const from = asString(msg.from);
        const content = asString(msg.content);
        if (!from || content === undefined) return;
        dispatch({
          type: "APPEND_LOG",
          entry: { timestamp: nowHHMMSS(), agent: from, action: content },
        });
        return;
      }
      case "broadcast": {
        const from = asString(msg.from);
        const content = asString(msg.content);
        if (!from || content === undefined) return;
        dispatch({
          type: "APPEND_LOG",
          entry: { timestamp: nowHHMMSS(), agent: from, action: content },
        });
        return;
      }
      case "roster": {
        const names = asStringArray(msg.agents);
        if (!names) return;
        dispatch({ type: "SET_AGENT_ROSTER", names: cleanRoster(names) });
        return;
      }
      case "tasks": {
        const backlog = asTaskArray(msg.backlog);
        const current = asTaskArray(msg.current);
        const done = asTaskArray(msg.done);
        // Only include fields that were present & validated.
        // If nothing validated, skip (no-op rather than wiping state).
        if (
          backlog === undefined &&
          current === undefined &&
          done === undefined
        ) {
          return;
        }
        dispatch({ type: "UPSERT_TASKS", backlog, current, done });
        return;
      }
      default:
        return;
    }
  }, [lastMessage, dispatch]);

  return { connected, status, sendMessage };
}

export default useOrchestrator;
