import AgentCard, { AgentCardProps } from "./components/AgentCard";
import TaskList, { Task } from "./components/TaskList";
import ChatInput from "./components/ChatInput";
import LogFeed, { LogEntry } from "./components/LogFeed";

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
    currentTask: "UI-1: базовая структура",
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
    stage: "backend · done",
    status: "done",
  },
  {
    id: "t2",
    title: "UI-1: базовая структура компонентов",
    stage: "frontend · active",
    status: "active",
  },
  {
    id: "t3",
    title: "WS-1: WebSocket bridge",
    stage: "backend · pending",
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
    action: "Начал работу над UI-1, ставлю TailwindCSS",
  },
];

function handleChatSubmit(text: string) {
  console.log("chat submit:", text);
}

function App() {
  return (
    <div className="h-screen w-screen flex flex-col bg-bg text-white overflow-hidden">
      <div className="flex-1 flex min-h-0">
        <aside className="w-[30%] flex flex-col border-r border-[#222] overflow-y-auto">
          <section className="p-3 border-b border-[#222]">
            <h2 className="text-xs uppercase tracking-wide text-[#666] mb-2">
              Агенты
            </h2>
            <div className="flex flex-col gap-2">
              {AGENTS.map((agent) => (
                <AgentCard key={agent.name} {...agent} />
              ))}
            </div>
          </section>
          <section className="p-3">
            <h2 className="text-xs uppercase tracking-wide text-[#666] mb-2">
              Задачи
            </h2>
            <TaskList tasks={TASKS} />
          </section>
        </aside>

        <main className="flex-1 bg-[#111] text-[#666] flex items-center justify-center">
          Terminals
        </main>
      </div>

      <div className="h-56 border-t border-[#222] flex">
        <div className="w-[40%] border-r border-[#222]">
          <ChatInput onSubmit={handleChatSubmit} />
        </div>
        <div className="flex-1 min-w-0">
          <LogFeed entries={LOGS} />
        </div>
      </div>
    </div>
  );
}

export default App;
