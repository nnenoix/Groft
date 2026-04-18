import { useEffect } from "react";
import useWebSocket, { type WSStatus } from "./useWebSocket";
import { useDispatch } from "../store/agentStore";
import type { AgentStatus } from "../components/AgentCard";

const VALID_STATUSES = new Set<AgentStatus>([
  "active",
  "idle",
  "stuck",
  "restarting",
]);

function isAgentStatus(v: unknown): v is AgentStatus {
  return typeof v === "string" && VALID_STATUSES.has(v as AgentStatus);
}

function asString(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function nowHHMMSS(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export interface UseOrchestratorResult {
  connected: boolean;
  status: WSStatus;
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
 *
 * Caveat: the server currently does not forward `status` frames to other
 * clients — it only records them. UI will still react if/when the orchestrator
 * broadcasts status, or if this behaviour changes.
 */
function useOrchestrator(): UseOrchestratorResult {
  const dispatch = useDispatch();
  const { status, connected, sendMessage, lastMessage } = useWebSocket({
    url: "ws://localhost:8765",
    agentName: "ui",
  });

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
        });
        return;
      }
      case "snapshot": {
        const name = asString(msg.agent);
        if (!name) return;
        // server.py ships `terminal` as a single string; accept `lines`/`content` too
        // in case future server versions attach them.
        let lines: string[] | null = null;
        const terminal = msg.terminal;
        if (typeof terminal === "string") {
          lines = terminal.split(/\r?\n/).filter((l) => l.length > 0);
        } else if (Array.isArray(msg.lines)) {
          lines = (msg.lines as unknown[]).filter(
            (x): x is string => typeof x === "string",
          );
        } else if (typeof msg.content === "string") {
          lines = msg.content.split(/\r?\n/).filter((l) => l.length > 0);
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
      default:
        return;
    }
  }, [lastMessage, dispatch]);

  return { connected, status, sendMessage };
}

export default useOrchestrator;
