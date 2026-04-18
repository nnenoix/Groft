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
    role: "backend",
    status: "active",
    currentAction: "Пишет auth middleware",
    currentTask: "AUTH-1: Авторизация",
    model: "sonnet-4-6",
  },
  {
    name: "frontend-dev",
    role: "frontend",
    status: "active",
    currentAction: "Создаёт LoginForm",
    currentTask: "UI-2: Dashboard",
    model: "sonnet-4-6",
  },
  {
    name: "tester",
    role: "test",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "haiku-4-5",
  },
  {
    name: "reviewer",
    role: "review",
    status: "idle",
    currentAction: "Ожидает",
    currentTask: "—",
    model: "sonnet-4-6",
  },
];

const BACKLOG_TASKS: Task[] = [
  {
    id: "b1",
    title: "AUTH-1: Авторизация",
    stage: "",
    status: "pending",
  },
  {
    id: "b2",
    title: "UI-2: Dashboard",
    stage: "",
    status: "pending",
  },
];

const CURRENT_TASKS: Task[] = [
  {
    id: "c1",
    title: "HEALTH-1: /health endpoint",
    stage: "",
    status: "active",
  },
];

const DONE_TASKS: Task[] = [
  {
    id: "d1",
    title: "INIT-1: Структура проекта",
    stage: "",
    status: "done",
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
      "10:23 npm run dev",
      "10:23 Server listening on :3000",
      "10:24 GET /health 200",
      "10:24 POST /api/auth 401",
      "▌",
    ],
  },
  {
    agent: "frontend-dev",
    status: "active",
    lines: [
      "10:22 npm install react-hook-form",
      "10:22 added 3 packages in 2s",
      "10:23 Creating LoginForm.tsx",
      "10:24 vite hmr update /src/LoginForm.tsx",
      "▌",
    ],
  },
  {
    agent: "tester",
    status: "idle",
    lines: [
      "10:20 npm test",
      "10:20 PASS  tests/health.test.js",
      "10:20 Tests: 6 passed, 6 total",
      "10:21 Ожидает изменений...",
      "▌",
    ],
  },
  {
    agent: "reviewer",
    status: "idle",
    lines: [
      "10:18 git fetch origin",
      "10:18 git log --oneline master..HEAD",
      "10:19 No pending PRs",
      "10:19 Ожидает code review...",
      "▌",
    ],
  },
];

function handleChatSubmit(text: string) {
  console.log("chat submit:", text);
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
      {title}
    </h2>
  );
}

function SidebarContent({ view }: { view: ActivityView }) {
  switch (view) {
    case "agents":
      return (
        <>
          <SectionHeader title="Agents" />
          <div className="px-3 space-y-2">
            {AGENTS.map((agent) => (
              <AgentCard key={agent.name} {...agent} />
            ))}
          </div>
        </>
      );
    case "tasks":
      return (
        <>
          <SectionHeader title="Backlog" />
          <TaskList tasks={BACKLOG_TASKS} />
          <SectionHeader title="Current" />
          <TaskList tasks={CURRENT_TASKS} />
          <SectionHeader title="Done" />
          <TaskList tasks={DONE_TASKS} />
        </>
      );
    case "logs":
      return (
        <>
          <SectionHeader title="Logs" />
          <div className="text-text-muted text-sm px-4 leading-relaxed">
            Последние события — в нижней панели под терминалами.
          </div>
        </>
      );
    case "settings":
      return (
        <>
          <SectionHeader title="Settings" />
          <div className="text-text-muted text-sm px-4 space-y-2 leading-relaxed">
            <div>Модели агентов: <span className="text-text-code">config.yml</span></div>
            <div>WebSocket: <span className="text-text-code">localhost:8765</span></div>
            <div className="text-text-dim">Редактирование — скоро</div>
          </div>
        </>
      );
  }
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
