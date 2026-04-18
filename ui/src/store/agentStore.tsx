import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type AgentStatus = "active" | "idle" | "stuck" | "restarting";

export type TaskStatus = "done" | "active" | "pending";

export interface Task {
  id: string;
  title: string;
  stage?: string;
  status: TaskStatus;
  owner?: string;
  priority?: "high" | "med" | "low";
  deps?: string[];
}

export interface AgentState {
  name: string;
  role: string;
  status: AgentStatus;
  currentAction: string;
  currentTask: string;
  model: string;
  terminalOutput: string[];
  avatar?: string;
  mode?: "solo" | "team";
  uptime?: string;
  cycles?: number;
  tokensIn?: number;
  tokensOut?: number;
  spark?: number[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
}

export interface Tasks {
  backlog: Task[];
  current: Task[];
  done: Task[];
}

export interface StoreState {
  agents: AgentState[];
  logs: LogEntry[];
  tasks: Tasks;
}

export type Action =
  | {
      type: "UPSERT_AGENT_STATUS";
      name: string;
      status: AgentStatus;
      currentAction?: string;
      currentTask?: string;
      model?: string;
      mode?: "solo" | "team";
      uptime?: string;
      cycles?: number;
      tokensIn?: number;
      tokensOut?: number;
      spark?: number[];
    }
  | { type: "APPEND_TERMINAL"; name: string; lines: string[] }
  | { type: "SET_TERMINAL"; name: string; lines: string[] }
  | { type: "APPEND_LOG"; entry: Omit<LogEntry, "id"> }
  | { type: "SET_AGENT_ROSTER"; names: string[] }
  | {
      type: "UPSERT_TASKS";
      backlog?: Task[];
      current?: Task[];
      done?: Task[];
    };

/* ------------------------------------------------------------------ */
/* Buffer limits                                                       */
/* ------------------------------------------------------------------ */

const TERMINAL_BUFFER = 100;
const LOG_BUFFER = 200;

/* ------------------------------------------------------------------ */
/* Initial state — empty. Roster comes from server (REST /agents +    */
/* `roster` WS frames); tasks come from future `tasks` WS frames.     */
/* ------------------------------------------------------------------ */

const INITIAL_TASKS: Tasks = {
  backlog: [],
  current: [],
  done: [],
};

const INITIAL_STATE: StoreState = {
  agents: [],
  logs: [],
  tasks: INITIAL_TASKS,
};

/* ------------------------------------------------------------------ */
/* Reducer                                                             */
/* ------------------------------------------------------------------ */

function nextLogId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `log-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function reducer(state: StoreState, action: Action): StoreState {
  switch (action.type) {
    case "UPSERT_AGENT_STATUS": {
      const existingIdx = state.agents.findIndex((a) => a.name === action.name);
      if (existingIdx === -1) {
        const next: AgentState = {
          name: action.name,
          role: action.name,
          status: action.status,
          currentAction: action.currentAction ?? "",
          currentTask: action.currentTask ?? "—",
          model: action.model ?? "",
          terminalOutput: [],
          ...(action.mode !== undefined && { mode: action.mode }),
          ...(action.uptime !== undefined && { uptime: action.uptime }),
          ...(action.cycles !== undefined && { cycles: action.cycles }),
          ...(action.tokensIn !== undefined && { tokensIn: action.tokensIn }),
          ...(action.tokensOut !== undefined && { tokensOut: action.tokensOut }),
          ...(action.spark !== undefined && { spark: action.spark }),
        };
        return { ...state, agents: [...state.agents, next] };
      }
      const nextAgents = state.agents.slice();
      const prev = nextAgents[existingIdx];
      nextAgents[existingIdx] = {
        ...prev,
        status: action.status,
        currentAction:
          action.currentAction !== undefined
            ? action.currentAction
            : prev.currentAction,
        currentTask:
          action.currentTask !== undefined
            ? action.currentTask
            : prev.currentTask,
        ...(action.model !== undefined && { model: action.model }),
        ...(action.mode !== undefined && { mode: action.mode }),
        ...(action.uptime !== undefined && { uptime: action.uptime }),
        ...(action.cycles !== undefined && { cycles: action.cycles }),
        ...(action.tokensIn !== undefined && { tokensIn: action.tokensIn }),
        ...(action.tokensOut !== undefined && { tokensOut: action.tokensOut }),
        ...(action.spark !== undefined && { spark: action.spark }),
      };
      return { ...state, agents: nextAgents };
    }
    case "APPEND_TERMINAL": {
      const idx = state.agents.findIndex((a) => a.name === action.name);
      if (idx === -1) return state;
      const nextAgents = state.agents.slice();
      const prev = nextAgents[idx];
      const merged = prev.terminalOutput.concat(action.lines);
      const trimmed =
        merged.length > TERMINAL_BUFFER
          ? merged.slice(merged.length - TERMINAL_BUFFER)
          : merged;
      nextAgents[idx] = { ...prev, terminalOutput: trimmed };
      return { ...state, agents: nextAgents };
    }
    case "SET_TERMINAL": {
      // snapshots arrive as a full capture-pane dump on every tick, so replace
      // rather than append — appending re-adds the recent history each tick
      // and the buffer-trim hides the duplication only partially.
      const idx = state.agents.findIndex((a) => a.name === action.name);
      // ignore snapshots for agents not yet in the roster — otherwise a stray
      // frame conjures a phantom agent row that never gets real status updates.
      if (idx === -1) return state;
      const trimmed =
        action.lines.length > TERMINAL_BUFFER
          ? action.lines.slice(action.lines.length - TERMINAL_BUFFER)
          : action.lines;
      const nextAgents = state.agents.slice();
      const prev = nextAgents[idx];
      nextAgents[idx] = { ...prev, terminalOutput: trimmed };
      return { ...state, agents: nextAgents };
    }
    case "APPEND_LOG": {
      const entry: LogEntry = { id: nextLogId(), ...action.entry };
      const merged = state.logs.concat(entry);
      const trimmed =
        merged.length > LOG_BUFFER
          ? merged.slice(merged.length - LOG_BUFFER)
          : merged;
      return { ...state, logs: trimmed };
    }
    case "SET_AGENT_ROSTER": {
      // Merge: keep existing agent records for names still present
      // (preserves status / terminal / currentAction / currentTask).
      // Create minimal records for new names. Drop records whose names
      // are no longer in the roster.
      const existingByName = new Map(state.agents.map((a) => [a.name, a]));
      const nextAgents: AgentState[] = action.names.map((name) => {
        const prev = existingByName.get(name);
        if (prev) return prev;
        return {
          name,
          role: name,
          status: "idle",
          currentAction: "",
          currentTask: "",
          model: "",
          terminalOutput: [],
        };
      });
      return { ...state, agents: nextAgents };
    }
    case "UPSERT_TASKS": {
      const nextTasks: Tasks = {
        backlog:
          action.backlog !== undefined ? action.backlog : state.tasks.backlog,
        current:
          action.current !== undefined ? action.current : state.tasks.current,
        done: action.done !== undefined ? action.done : state.tasks.done,
      };
      return { ...state, tasks: nextTasks };
    }
  }
}

/* ------------------------------------------------------------------ */
/* Context + provider                                                  */
/* ------------------------------------------------------------------ */

interface StoreContextValue {
  state: StoreState;
  dispatch: Dispatch<Action>;
}

const StoreContext = createContext<StoreContextValue | null>(null);

export function AgentStoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return (
    <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
  );
}

function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) {
    throw new Error("useStore must be used within <AgentStoreProvider>");
  }
  return ctx;
}

export function useAgents(): AgentState[] {
  return useStore().state.agents;
}

export function useLogs(): LogEntry[] {
  return useStore().state.logs;
}

export function useTasks(): Tasks {
  return useStore().state.tasks;
}

export function useDispatch(): Dispatch<Action> {
  return useStore().dispatch;
}
