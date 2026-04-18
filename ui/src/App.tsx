import { useState } from "react";
import Header from "./components/Header";
import ActivityBar, { type ActivityView } from "./components/ActivityBar";
import AgentCard, { type AgentCardProps } from "./components/AgentCard";
import TaskList, { type Task } from "./components/TaskList";
import ChatInput from "./components/ChatInput";
import LogFeed, { type LogEntry } from "./components/LogFeed";
import TerminalGrid, { type TerminalData } from "./components/TerminalGrid";

const AGENTS: AgentCardProps[] = [
  {
    name: "backend-dev",
    role: "API & бизнес-логика",
    status: "active",
    currentAction: "Пишет express-роуты",
    currentTask: "HEALTH-1: /health endpoint",
    model: "sonnet-4.6",
  },
  {
    name: "frontend-dev",
    role: "React / UI",
    status: "active",
    currentAction: "Создаёт layout",
    currentTask: "UI-3: светлая тема",
    model: "sonnet-4.6",
  },
  {
    name: "tester",
    role: "Автотесты",
    status: "idle",
    currentAction: "Ожидает изменений",
    currentTask: "—",
    model: "haiku-4.5",
  },
  {
    name: "reviewer",
    role: "Code review",
    status: "idle",
    currentAction: "Ожидает PR",
    currentTask: "—",
    model: "sonnet-4.6",
  },
];

const TASKS: Task[] = [
  {
    id: "t1",
    title: "HEALTH-1: /health endpoint",
    stage: "done",
    status: "done",
  },
  {
    id: "t2",
    title: "UI-3: светлая тема",
    stage: "active",
    status: "active",
  },
  {
    id: "t3",
    title: "WS-1: WebSocket bridge",
    stage: "pending",
    status: "pending",
  },
];

const LOGS: LogEntry[] = [
  {
    id: "l1",
    timestamp: "12:04:11",
    agent: "backend-dev",
    action: "Создал server.js, добавил /health",
  },
  {
    id: "l2",
    timestamp: "12:05:47",
    agent: "tester",
    action: "Запустил smoke-тест: GET /health → 200 OK",
  },
  {
    id: "l3",
    timestamp: "12:07:02",
    agent: "frontend-dev",
    action: "Начал работу над UI-3, редизайн в светлую тему",
  },
];

const TERMINALS: TerminalData[] = [
  {
    agent: "backend-dev",
    status: "active",
    lines: [
      "12:04 Writing auth middleware...",
      "12:04 npm install jsonwebtoken",
      "12:05 ✓ Done",
    ],
  },
  {
    agent: "frontend-dev",
    status: "active",
    lines: [
      "12:05 Creating LoginForm.tsx...",
      "12:05 ✓ Component ready",
    ],
  },
  {
    agent: "tester",
    status: "idle",
    lines: [
      "12:06 Running test suite...",
      "12:06 ✓ 6/6 passed",
    ],
  },
  {
    agent: "reviewer",
    status: "idle",
    lines: [
      "12:07 Reviewing auth module...",
      "12:07 ✓ No issues found",
    ],
  },
];

function handleChatSubmit(text: string) {
  console.log("chat submit:", text);
}

function SidebarContent({ view }: { view: ActivityView }) {
  if (view === "agents") {
    return (
      <>
        <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
          Agents
        </h2>
        <div className="px-3 space-y-2">
          {AGENTS.map((agent) => (
            <AgentCard key={agent.name} {...agent} />
          ))}
        </div>
      </>
    );
  }
  if (view === "tasks") {
    return (
      <>
        <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
          Tasks
        </h2>
        <TaskList tasks={TASKS} />
      </>
    );
  }
  if (view === "logs") {
    return (
      <>
        <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
          Logs
        </h2>
        <div className="text-text-muted text-sm px-4">
          Logs в главной панели
        </div>
      </>
    );
  }
  return (
    <>
      <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
        Settings
      </h2>
      <div className="text-text-muted text-sm px-4">Настройки — скоро</div>
    </>
  );
}

function App() {
  const [activeView, setActiveView] = useState<ActivityView>("agents");

  return (
    <div className="h-screen flex flex-col bg-bg-primary text-text-primary overflow-hidden">
      <Header agentCount={AGENTS.length} systemActive={true} />
      <div className="flex-1 flex overflow-hidden">
        <ActivityBar activeView={activeView} onSelect={setActiveView} />
        <aside className="w-64 h-full bg-bg-sidebar border-r border-border overflow-y-auto shrink-0">
          <SidebarContent view={activeView} />
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          <div className="flex-1 overflow-hidden flex flex-col">
            <h2 className="text-text-muted uppercase text-xs tracking-widest px-6 pt-4 pb-2">
              Terminals
            </h2>
            <div className="flex-1 overflow-hidden">
              <TerminalGrid terminals={TERMINALS} />
            </div>
          </div>
          <div className="h-56 border-t border-border flex bg-bg-secondary shrink-0">
            <div className="w-[40%] border-r border-border">
              <ChatInput onSubmit={handleChatSubmit} />
            </div>
            <div className="flex-1 min-w-0">
              <LogFeed entries={LOGS} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
