import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { AgentStatus } from "../components/AgentCard";
import type { Task } from "../components/TaskList";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface AgentState {
  name: string;
  role: string;
  status: AgentStatus;
  currentAction: string;
  currentTask: string;
  model: string;
  terminalOutput: string[];
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
    }
  | { type: "APPEND_TERMINAL"; name: string; lines: string[] }
  | { type: "APPEND_LOG"; entry: Omit<LogEntry, "id"> };

/* ------------------------------------------------------------------ */
/* Buffer limits                                                       */
/* ------------------------------------------------------------------ */

const TERMINAL_BUFFER = 100;
const LOG_BUFFER = 200;

/* ------------------------------------------------------------------ */
/* Initial mock state — agent list / tasks carry over from UI-4.       */
/* Terminal output, action, status are overwritten by WS traffic.      */
/* ------------------------------------------------------------------ */

const INITIAL_AGENTS: AgentState[] = [
  {
    name: "backend-dev",
    role: "backend",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "sonnet-4-6",
    terminalOutput: [],
  },
  {
    name: "frontend-dev",
    role: "frontend",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "sonnet-4-6",
    terminalOutput: [],
  },
  {
    name: "tester",
    role: "test",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "haiku-4-5",
    terminalOutput: [],
  },
  {
    name: "reviewer",
    role: "review",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "sonnet-4-6",
    terminalOutput: [],
  },
];

const INITIAL_TASKS: Tasks = {
  backlog: [
    { id: "b1", title: "AUTH-1: Авторизация", stage: "", status: "pending" },
    { id: "b2", title: "UI-2: Dashboard", stage: "", status: "pending" },
  ],
  current: [
    {
      id: "c1",
      title: "HEALTH-1: /health endpoint",
      stage: "",
      status: "active",
    },
  ],
  done: [
    {
      id: "d1",
      title: "INIT-1: Структура проекта",
      stage: "",
      status: "done",
    },
  ],
};

const INITIAL_STATE: StoreState = {
  agents: INITIAL_AGENTS,
  logs: [],
  tasks: INITIAL_TASKS,
};

/* ------------------------------------------------------------------ */
/* Reducer                                                             */
/* ------------------------------------------------------------------ */

let logIdSeq = 0;
function nextLogId(): string {
  logIdSeq += 1;
  return `log-${logIdSeq}`;
}

function reducer(state: StoreState, action: Action): StoreState {
  switch (action.type) {
    case "UPSERT_AGENT_STATUS": {
      const existingIdx = state.agents.findIndex((a) => a.name === action.name);
      if (existingIdx === -1) {
        // unknown agent: append a minimal record so it renders
        const next: AgentState = {
          name: action.name,
          role: action.name,
          status: action.status,
          currentAction: action.currentAction ?? "",
          currentTask: action.currentTask ?? "—",
          model: "",
          terminalOutput: [],
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
    case "APPEND_LOG": {
      const entry: LogEntry = { id: nextLogId(), ...action.entry };
      const merged = state.logs.concat(entry);
      const trimmed =
        merged.length > LOG_BUFFER
          ? merged.slice(merged.length - LOG_BUFFER)
          : merged;
      return { ...state, logs: trimmed };
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
